"""LangGraph synthesis workflow — one execution per (paper, run)."""
from __future__ import annotations

import json
import traceback
from typing import Any

from typing_extensions import TypedDict
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import AnalysisRun, Paper, PaperAnswer, PaperExtraction
from app.observability.langfuse_client import generation_span, span_paper
from app.synthesis.prompts import SYSTEM_PROMPT, build_user_prompt
from app.synthesis.schemas import PaperAnswerOutput, QuestionAnswer


# ── LangGraph state ───────────────────────────────────────────────────────────

class PaperState(TypedDict):
    paper_id: str
    run_id: str
    questions: list[str]
    text_content: str | None
    paper_title: str | None
    output: PaperAnswerOutput | None
    error: str | None


# ── LLM client ────────────────────────────────────────────────────────────────

def _get_llm_client():
    from openai import OpenAI
    return OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        default_headers={
            "HTTP-Referer": "https://github.com/lit-anal",
            "X-Title": "Literature Analysis Synthesizer",
        },
    )


# ── Node functions ────────────────────────────────────────────────────────────

def _node_load_text(state: PaperState, *, session: Session) -> dict[str, Any]:
    """Load extracted text for the paper from the database."""
    extraction: PaperExtraction | None = (
        session.query(PaperExtraction)
        .filter_by(paper_id=state["paper_id"], extraction_status="completed")
        .first()
    )
    if extraction is None:
        return {"error": "No completed extraction found for paper.", "text_content": None}
    return {"text_content": extraction.text_content, "error": None}


def _node_answer_questions(state: PaperState) -> dict[str, Any]:
    """Call the LLM to answer all questions; retries up to 2 times on failure."""
    if state.get("error") or not state.get("text_content"):
        return {"output": None}

    client = _get_llm_client()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_user_prompt(
                paper_id=state["paper_id"],
                paper_title=state.get("paper_title"),
                text_content=state["text_content"],
                questions=state["questions"],
            ),
        },
    ]

    max_retries = 2
    last_error: str | None = None

    for attempt in range(max_retries + 1):
        try:
            with generation_span(model=settings.openrouter_model, input_messages=messages) as gen:
                response = client.chat.completions.create(
                    model=settings.openrouter_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )
                raw_content = response.choices[0].message.content or "{}"
                usage = response.usage

                if gen is not None:
                    gen.update(
                        output=raw_content[:500],
                        usage={
                            "input_tokens": usage.prompt_tokens if usage else 0,
                            "output_tokens": usage.completion_tokens if usage else 0,
                        },
                    )

            parsed = PaperAnswerOutput.model_validate_json(raw_content)
            return {"output": parsed, "error": None}

        except Exception as exc:
            last_error = traceback.format_exc()[:2000]

    return {"output": None, "error": f"LLM call failed after {max_retries + 1} attempts: {last_error}"}


def _node_finalize(state: PaperState, *, session: Session, run_id: str) -> dict[str, Any]:
    """Persist the PaperAnswer row to the database."""
    output: PaperAnswerOutput | None = state.get("output")

    existing = (
        session.query(PaperAnswer)
        .filter_by(run_id=run_id, paper_id=state["paper_id"])
        .first()
    ) or PaperAnswer(run_id=run_id, paper_id=state["paper_id"])

    if output:
        existing.answers = [a.model_dump() for a in output.answers]
        existing.references = [
            ref.model_dump()
            for a in output.answers
            for ref in a.references
        ]
        existing.status = "completed"
    else:
        existing.answers = []
        existing.status = "failed"
        existing.references = []

    session.add(existing)
    session.flush()
    return {}


# ── Graph builder ─────────────────────────────────────────────────────────────

def _build_graph(session: Session, run_id: str):
    """Compile and return the LangGraph workflow."""

    def load_text(state: PaperState) -> dict:
        return _node_load_text(state, session=session)

    def answer_questions(state: PaperState) -> dict:
        return _node_answer_questions(state)

    def finalize(state: PaperState) -> dict:
        return _node_finalize(state, session=session, run_id=run_id)

    graph = StateGraph(PaperState)
    graph.add_node("load_text", load_text)
    graph.add_node("answer_questions", answer_questions)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "load_text")
    graph.add_edge("load_text", "answer_questions")
    graph.add_edge("answer_questions", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


# ── Public API ────────────────────────────────────────────────────────────────

def run_synthesis_for_paper(
    paper: Paper,
    run: AnalysisRun,
    session: Session,
) -> PaperAnswer:
    """Run the full synthesis workflow for a single paper and persist results."""
    compiled = _build_graph(session=session, run_id=run.id)

    initial_state: PaperState = {
        "paper_id": paper.id,
        "run_id": run.id,
        "questions": run.questions or [],
        "text_content": None,
        "paper_title": paper.title,
        "output": None,
        "error": None,
    }

    with span_paper(paper_id=paper.id, paper_title=paper.title):
        compiled.invoke(initial_state)

    answer = (
        session.query(PaperAnswer)
        .filter_by(run_id=run.id, paper_id=paper.id)
        .first()
    )
    return answer
