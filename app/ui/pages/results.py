"""Results page — view, filter, and export synthesis outputs."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from app.db.models import AnalysisRun, Paper, PaperAnswer, PaperExtraction
from app.db.session import check_connection, get_session
from app.ui.paper_preview import render_paper_table_with_preview

st.title("📊 Results")
st.caption("View per-paper synthesis answers and export to CSV or JSON.")

if not check_connection():
    st.error("Database not reachable. Check your DATABASE_URL and Alembic migration.")
    st.stop()

# ── Run selector ──────────────────────────────────────────────────────────────

with get_session() as session:
    runs: list[AnalysisRun] = (
        session.query(AnalysisRun)
        .order_by(AnalysisRun.created_at.desc())
        .all()
    )
    runs_data = [
        {
            "id": r.id,
            "run_name": r.run_name or r.id[:8],
            "llm_name": r.llm_name or "—",
            "label": f"{r.run_name or r.id[:8]} — {r.status} — {(r.started_at or r.created_at).strftime('%Y-%m-%d %H:%M') if (r.started_at or r.created_at) else '?'}",
            "questions": r.questions or [],
        }
        for r in runs
    ]

if not runs_data:
    st.info("No analysis runs yet. Go to the **Analysis** page to run a synthesis.")
    st.stop()

run_labels = [r["label"] for r in runs_data]
selected_labels = st.multiselect(
    "Select analysis run(s)",
    options=run_labels,
    default=run_labels[:1],
)

if not selected_labels:
    st.info("Select at least one run to view results.")
    st.stop()

selected_runs = [runs_data[run_labels.index(lbl)] for lbl in selected_labels]

st.divider()

# ── Build combined column names across runs ───────────────────────────────────
#
# Each run may have a different set of questions.  We collect them all,
# detecting duplicates across runs.  When the same question text appears in
# more than one run's question list we append " [<run_name>]" to distinguish
# the column names.

# step 1 – gather (run_id, q_idx, q_text) tuples
all_question_entries: list[tuple[str, int, str]] = []
for run in selected_runs:
    for q_idx, q in enumerate(run["questions"]):
        all_question_entries.append((run["id"], q_idx, q))

# step 2 – count how many (different) runs each question text appears in
from collections import Counter
q_text_run_count: Counter[str] = Counter()
for run in selected_runs:
    seen_in_run: set[str] = set()
    for q in run["questions"]:
        if q not in seen_in_run:
            q_text_run_count[q] += 1
            seen_in_run.add(q)

# step 3 – build column name: duplicate questions get " [run_name]" suffix
# track per-run, per-question the final column label
run_q_col: dict[tuple[str, int], str] = {}
for run in selected_runs:
    for q_idx, q in enumerate(run["questions"]):
        q_short = q[:40] + ("…" if len(q) > 40 else "")
        if q_text_run_count[q] > 1:
            col_label = f"Q{q_idx+1}: {q_short} [{run['run_name']}]"
        else:
            col_label = f"Q{q_idx+1}: {q_short}"
        run_q_col[(run["id"], q_idx)] = col_label

# ── Load results for all selected runs ───────────────────────────────────────

selected_run_ids = [r["id"] for r in selected_runs]
run_by_id = {r["id"]: r for r in selected_runs}

with get_session() as session:
    answers: list[PaperAnswer] = (
        session.query(PaperAnswer)
        .filter(PaperAnswer.run_id.in_(selected_run_ids))
        .all()
    )
    paper_ids = list({a.paper_id for a in answers})
    papers: dict[str, Paper] = {
        p.id: p
        for p in session.query(Paper).filter(Paper.id.in_(paper_ids)).all()
    }
    answers_data = [
        {
            "id": a.id,
            "run_id": a.run_id,
            "paper_id": a.paper_id,
            "status": a.status,
            "answers": a.answers or [],
            "references": a.references or [],
        }
        for a in answers
    ]
    extraction_rows: list[PaperExtraction] = (
        session.query(PaperExtraction)
        .filter(
            PaperExtraction.paper_id.in_(paper_ids),
            PaperExtraction.extraction_status == "completed",
        )
        .all()
    )
    extraction_by_paper = {e.paper_id: e for e in extraction_rows}

if not answers_data:
    st.info("No results for the selected run(s) yet.")
    st.stop()

# ── Build flat table ──────────────────────────────────────────────────────────

show_short_title = any((paper.short_title or "").strip() for paper in papers.values())
show_citation_key = any((paper.citation_key or "").strip() for paper in papers.values())

rows = []
for a in answers_data:
    paper = papers.get(a["paper_id"])
    run = run_by_id[a["run_id"]]
    row: dict = {
        "Title": (paper.title if paper else None) or a["paper_id"][:8],
    }
    if show_short_title:
        row["Short Title"] = (paper.short_title if paper else None) or "—"
    if show_citation_key:
        row["Citation Key"] = (paper.citation_key if paper else None) or "—"
    row["Authors"] = ", ".join(paper.authors or [])[:60] if paper else "—"
    row["Year"] = paper.year if paper else "—"
    row["Run"] = run["run_name"]
    row["LLM"] = run["llm_name"]
    row["Status"] = a["status"]

    run_questions = run["questions"]
    for q_idx, q in enumerate(run_questions):
        col_label = run_q_col[(run["id"], q_idx)]
        ans_obj = a["answers"][q_idx] if q_idx < len(a["answers"]) else {}
        row[col_label] = ans_obj.get("answer", "—")

    rows.append(row)

df = pd.DataFrame(rows)

# ── Filter / search ───────────────────────────────────────────────────────────

search = st.text_input("🔍 Search titles", placeholder="Filter by title…")
if search:
    df = df[df["Title"].str.contains(search, case=False, na=False)]

status_filter = st.multiselect(
    "Filter by status",
    options=["completed", "failed", "pending"],
    default=["completed", "failed", "pending"],
)
if status_filter:
    df = df[df["Status"].isin(status_filter)]

visible_answers_data = []
for a in answers_data:
    paper = papers.get(a["paper_id"])
    title = (paper.title if paper else None) or a["paper_id"][:8]
    if search and search.lower() not in title.lower():
        continue
    if status_filter and a["status"] not in status_filter:
        continue
    visible_answers_data.append(a)

preview_rows = []
for a in visible_answers_data:
    paper = papers.get(a["paper_id"])
    run = run_by_id[a["run_id"]]
    preview_row = {
        "paper_id": a["paper_id"],
        "row_key": a["id"],
        "file_path": paper.file_path if paper else None,
        "Title": (paper.title if paper else None) or a["paper_id"][:8],
        "Year": paper.year if paper else "—",
        "Run": run["run_name"],
        "LLM": run["llm_name"],
        "Status": a["status"],
    }
    if show_short_title:
        preview_row["Short Title"] = (paper.short_title if paper else None) or "—"
    if show_citation_key:
        preview_row["Citation Key"] = (paper.citation_key if paper else None) or "—"
    preview_rows.append(preview_row)

st.subheader(f"Results ({len(df)} rows)")
preview_columns = ["Title"]
if show_short_title:
    preview_columns.append("Short Title")
if show_citation_key:
    preview_columns.append("Citation Key")
preview_columns.extend(["Year", "Run", "LLM", "Status"])
render_paper_table_with_preview(
    preview_rows,
    state_key="results_selected_paper",
    display_columns=preview_columns,
    viewer_title="Paper PDF",
    viewer_height=950,
    empty_message="No papers match the current filters.",
)
st.caption("The full results matrix remains available below for scanning answers across runs.")
st.dataframe(df, use_container_width=True, height=400)

# ── Expandable evidence details ───────────────────────────────────────────────

st.subheader("Evidence Details")
for a in answers_data:
    paper = papers.get(a["paper_id"])
    run = run_by_id[a["run_id"]]
    title = (paper.title if paper else None) or a["paper_id"][:8]
    if search and search.lower() not in title.lower():
        continue

    expander_label = f"📄 {title}" if len(selected_runs) == 1 else f"📄 {title} [{run['run_name']}]"
    with st.expander(expander_label, expanded=False):
        extraction = extraction_by_paper.get(a["paper_id"])
        if extraction and extraction.markdown_path:
            md_path = Path(extraction.markdown_path)
            exists = "exists" if md_path.exists() else "missing"
            st.caption(f"Extraction markdown: {md_path} ({exists})")

        if not a["answers"]:
            st.warning("No answers recorded.")
            continue
        for qa in a["answers"]:
            st.markdown(f"**Q: {qa.get('question', '—')}**")
            st.markdown(f"> **A:** {qa.get('answer', '—')}")
            status_badge = "✅" if qa.get("status") == "answered" else "⚠️"
            st.caption(f"Status: {status_badge} {qa.get('status', '—')}")
            evidence = qa.get("evidence", [])
            if evidence:
                st.markdown("*Evidence:*")
                for ev in evidence:
                    loc = []
                    if ev.get("page"):
                        loc.append(f"p.{ev['page']}")
                    if ev.get("section"):
                        loc.append(ev["section"])
                    loc_str = " · ".join(loc)
                    st.markdown(f"  - *\"{ev.get('quote', '')}\"* {f'({loc_str})' if loc_str else ''}")
            st.divider()

# ── Export ────────────────────────────────────────────────────────────────────

export_label = "_".join(r["id"][:8] for r in selected_runs)

st.subheader("Export")
col_csv, col_json = st.columns(2)

# CSV export uses the flat DataFrame
csv_buf = io.StringIO()
df.to_csv(csv_buf, index=False)
col_csv.download_button(
    label="⬇ Download CSV",
    data=csv_buf.getvalue().encode(),
    file_name=f"synthesis_{export_label}.csv",
    mime="text/csv",
)

# JSON export includes full evidence + reference payload
full_export = []
for a in answers_data:
    paper = papers.get(a["paper_id"])
    run = run_by_id[a["run_id"]]
    full_export.append(
        {
            "run_id": a["run_id"],
            "run_name": run["run_name"],
            "llm_name": run["llm_name"],
            "paper_id": a["paper_id"],
            "paper_title": paper.title if paper else None,
            "year": paper.year if paper else None,
            "status": a["status"],
            "answers": a["answers"],
            "references": a["references"],
        }
    )
col_json.download_button(
    label="⬇ Download JSON",
    data=json.dumps(full_export, indent=2, default=str).encode(),
    file_name=f"synthesis_{export_label}.json",
    mime="application/json",
)
