"""Prompt templates for LLM synthesis."""

SYSTEM_PROMPT = """\
You are a rigorous scientific literature analyst. Your sole task is to answer \
questions about a given academic paper based exclusively on the paper's text. \

Rules you MUST follow:
1. Only use information explicitly present in the paper text provided.
2. Never fabricate quotes, statistics, or citations.
3. If the paper does not contain sufficient information to answer a question, \
   you MUST set status to "insufficient_evidence" and answer "Insufficient evidence."
4. For every answered question, include at least one evidence quote from the paper.
5. Quotes must be verbatim or near-verbatim excerpts from the provided text.
6. Return your response as valid JSON matching the schema exactly.
"""


def build_user_prompt(
    paper_id: str,
    paper_title: str | None,
    text_content: str,
    questions: list[str],
) -> str:
    questions_block = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
    # Truncate very long texts to avoid exceeding context limits (~100k chars)
    max_chars = 100_000
    if len(text_content) > max_chars:
        text_content = text_content[:max_chars] + "\n\n[... text truncated ...]"

    return f"""\
Paper ID: {paper_id}
Paper Title: {paper_title or "Unknown"}

--- PAPER TEXT ---
{text_content}
--- END OF PAPER TEXT ---

Please answer each of the following questions about this paper:
{questions_block}

Respond with a JSON object matching this schema:
{{
  "paper_id": "<paper_id>",
  "paper_title": "<title>",
  "answers": [
    {{
      "question": "<question text>",
      "answer": "<answer or 'Insufficient evidence.'>",
      "evidence": [
        {{"quote": "...", "page": <int or null>, "section": "...", "figure_id": null}}
      ],
      "references": [],
      "status": "answered" | "insufficient_evidence"
    }}
  ]
}}
"""
