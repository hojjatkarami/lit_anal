"""Analysis page — configure questions, run extraction + synthesis."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import streamlit as st

from app.config import settings
from app.db.models import AnalysisRun, Paper, PaperExtraction
from app.db.session import check_connection, get_session
from app.extraction.docling_pipeline import ExtractionPipeline
from app.observability.langfuse_client import flush, trace_run
from app.synthesis.schemas import parse_questions
from app.synthesis.workflow import run_synthesis_for_paper

st.title("🔬 Analysis")
st.caption("Enter your research questions and run the synthesis pipeline.")

if not check_connection():
    st.error("Database not reachable. Check your DATABASE_URL and Alembic migration.")
    st.stop()

# ── Prompt input ──────────────────────────────────────────────────────────────

st.subheader("Research Questions")

prompt = st.text_area(
    "Enter your questions (one per line ending with '?', or as a numbered list)",
    height=150,
    placeholder=(
        "1. What methodology was used?\n"
        "2. What are the main findings?\n"
        "3. What limitations are reported?"
    ),
)

if prompt.strip():
    questions = parse_questions(prompt)
    st.info(f"**{len(questions)} question(s) detected:**")
    for i, q in enumerate(questions, 1):
        st.markdown(f"  {i}. {q}")
else:
    questions = []

run_name = st.text_input(
    "Run name (optional)",
    value=f"run_{datetime.now().strftime('%Y%m%d_%H%M')}",
)

st.divider()

# ── Paper selection ───────────────────────────────────────────────────────────

st.subheader("Paper Selection")

with get_session() as _s:
    paper_rows = (
        _s.query(Paper)
        .order_by(Paper.created_at.desc())
        .all()
    )
    all_papers = [
        {
            "id": p.id,
            "title": p.title,
            "year": p.year,
        }
        for p in paper_rows
    ]

if not all_papers:
    st.warning("No papers indexed. Go to the **Data Source** page first.")
    st.stop()

paper_options = {
    f"{p['title'] or p['id'][:8]} ({p['year'] or '?'})": p["id"]
    for p in all_papers
}
selected_labels = st.multiselect(
    "Select papers (leave empty to run on all)",
    options=list(paper_options.keys()),
)
selected_ids = (
    {paper_options[l] for l in selected_labels} if selected_labels else None
)

papers_to_run = (
    [p for p in all_papers if p["id"] in selected_ids]
    if selected_ids
    else all_papers
)

st.caption(f"{len(papers_to_run)} paper(s) will be processed.")

st.divider()

# ── Run ───────────────────────────────────────────────────────────────────────

can_run = bool(prompt.strip() and questions and papers_to_run)
if st.button("▶ Run Analysis", type="primary", disabled=not can_run):
    total = len(papers_to_run)

    with get_session() as session:
        # Create AnalysisRun record
        run = AnalysisRun(
            run_name=run_name,
            prompt_raw=prompt,
            questions=questions,
            llm_name=settings.openrouter_model,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        session.flush()
        run_id = run.id

    st.info(f"Run ID: `{run_id}`")

    pipeline = ExtractionPipeline()
    overall_progress = st.progress(0, text="Starting…")
    status_table_placeholder = st.empty()

    paper_statuses: list[dict] = [
        {"Title": p["title"] or p["id"][:8], "Stage": "pending", "Status": "⏳"}
        for p in papers_to_run
    ]

    def _refresh_table():
        import pandas as pd
        status_table_placeholder.dataframe(
            pd.DataFrame(paper_statuses), use_container_width=True
        )

    _refresh_table()

    errors: list[str] = []

    with trace_run(run_id=run_id, run_name=run_name, prompt=prompt):
        row_by_paper_id = {paper["id"]: paper_statuses[idx] for idx, paper in enumerate(papers_to_run)}
        ready_for_synthesis: list[dict] = []

        for idx, paper in enumerate(papers_to_run, start=1):
            paper_id = paper["id"]
            paper_title = paper["title"] or paper_id[:8]
            pct = int((idx - 1) / total * 100)
            overall_progress.progress(pct, text=f"[{idx}/{total}] {paper_title}")
            row = row_by_paper_id[paper_id]

            # ── Extraction ────────────────────────────────────────────────
            row["Stage"] = "extracting"
            _refresh_table()
            try:
                with get_session() as session:
                    paper_obj = session.get(Paper, paper_id)
                    if paper_obj is None:
                        raise ValueError(f"Paper not found: {paper_id}")
                    ext = pipeline.extract(paper_obj, session)
                if ext.extraction_status == "failed":
                    row["Stage"] = "extraction failed"
                    row["Status"] = "❌"
                    errors.append(f"{paper_title}: extraction failed — {ext.error_message}")
                    _refresh_table()
                    continue
                ready_for_synthesis.append(paper)
            except Exception as exc:
                row["Stage"] = "extraction error"
                row["Status"] = "❌"
                errors.append(f"{paper_title}: {exc}")
                _refresh_table()
                continue

        if ready_for_synthesis:
            for paper in ready_for_synthesis:
                row_by_paper_id[paper["id"]]["Stage"] = "queued for synthesis"
            _refresh_table()

            def _synth_worker(paper_id: str) -> tuple[str, str | None]:
                try:
                    with get_session() as session:
                        run_obj = session.get(AnalysisRun, run_id)
                        paper_obj = session.get(Paper, paper_id)
                        if run_obj is None:
                            raise ValueError(f"Run not found: {run_id}")
                        if paper_obj is None:
                            raise ValueError(f"Paper not found: {paper_id}")
                        run_synthesis_for_paper(
                            paper=paper_obj,
                            run=run_obj,
                            session=session,
                        )
                    return paper_id, None
                except Exception as exc:
                    return paper_id, str(exc)

            configured = max(1, settings.openrouter_max_concurrent_requests)
            max_workers = min(10, configured, len(ready_for_synthesis))

            completed = 0
            for paper in ready_for_synthesis:
                row_by_paper_id[paper["id"]]["Stage"] = "synthesising"
            _refresh_table()

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_paper = {
                    executor.submit(_synth_worker, paper["id"]): paper
                    for paper in ready_for_synthesis
                }
                for future in as_completed(future_to_paper):
                    paper = future_to_paper[future]
                    paper_id, err = future.result()
                    row = row_by_paper_id[paper_id]
                    paper_title = paper["title"] or paper_id[:8]

                    if err:
                        row["Stage"] = "synthesis error"
                        row["Status"] = "❌"
                        errors.append(f"{paper_title}: synthesis — {err}")
                    else:
                        row["Stage"] = "done"
                        row["Status"] = "✅"

                    completed += 1
                    pct = int(completed / max(1, len(ready_for_synthesis)) * 100)
                    overall_progress.progress(
                        pct,
                        text=(
                            f"Synthesis complete: {completed}/{len(ready_for_synthesis)} "
                            f"(parallel={max_workers})"
                        ),
                    )
                    _refresh_table()

    # Finalise run record
    overall_progress.progress(100, text="Complete.")
    with get_session() as session:
        run_final = session.get(AnalysisRun, run_id)
        run_final.status = "failed" if errors else "completed"
        run_final.finished_at = datetime.now(timezone.utc)

    flush()

    if errors:
        st.warning(f"Completed with {len(errors)} error(s):")
        for e in errors:
            st.error(e)
    else:
        st.success(f"Analysis complete! {total} paper(s) processed. View results on the **Results** page.")
