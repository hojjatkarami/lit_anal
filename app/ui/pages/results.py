"""Results page — view, filter, and export synthesis outputs."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:
    from streamlit_pdf_viewer import pdf_viewer
except ImportError:  # pragma: no cover - optional dependency at runtime
    pdf_viewer = None

from app.db.models import AnalysisRun, Paper, PaperAnswer, PaperExtraction
from app.db.session import check_connection, get_session
from app.ui.doctags_search import find_first_match_in_doctags
from app.ui.html_search import highlight_first_match_in_html, inline_images_as_base64
from app.ui.paper_preview import render_paper_table_with_preview

EVIDENCE_FIND_STATE_KEY = "results_evidence_find"

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
top_viewer_width_pct = st.slider(
    "Top viewer width (%)",
    min_value=30,
    max_value=70,
    value=42,
    step=2,
    key="results_top_viewer_width_pct",
    help="Adjust the width split between the results table and the top PDF preview.",
)
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
    viewer_pane_ratio=top_viewer_width_pct / 100,
    empty_message="No papers match the current filters.",
)
st.caption("The full results matrix remains available below for scanning answers across runs.")
st.dataframe(df, use_container_width=True, height=400)

# ── Expandable evidence details ───────────────────────────────────────────────

st.subheader("Evidence Details")
evidence_viewer_width_pct = st.slider(
    "Evidence viewer width (%)",
    min_value=30,
    max_value=70,
    value=42,
    step=2,
    key="results_evidence_viewer_width_pct",
    help="Adjust the width split between Q/A details and the evidence viewer.",
)
evidence_details_width = 100 - evidence_viewer_width_pct
active_find_state = st.session_state.get(EVIDENCE_FIND_STATE_KEY)
if active_find_state is not None and not isinstance(active_find_state, dict):
    st.session_state.pop(EVIDENCE_FIND_STATE_KEY, None)

for a in answers_data:
    paper = papers.get(a["paper_id"])
    run = run_by_id[a["run_id"]]
    title = (paper.title if paper else None) or a["paper_id"][:8]
    if search and search.lower() not in title.lower():
        continue

    expander_label = f"📄 {title}" if len(selected_runs) == 1 else f"📄 {title} [{run['run_name']}]"
    with st.expander(expander_label, expanded=False):
        extraction = extraction_by_paper.get(a["paper_id"])
        html_path = extraction.html_path if extraction else None

        col_details, col_html = st.columns([evidence_details_width, evidence_viewer_width_pct], gap="large")

        with col_details:
            if extraction and extraction.markdown_path:
                md_path = Path(extraction.markdown_path)
                exists = "exists" if md_path.exists() else "missing"
                st.caption(f"Extraction markdown: {md_path} ({exists})")

            if not a["answers"]:
                st.warning("No answers recorded.")
            else:
                for qa_idx, qa in enumerate(a["answers"]):
                    st.markdown(f"**Q: {qa.get('question', '—')}**")
                    st.markdown(f"> **A:** {qa.get('answer', '—')}")
                    status_badge = "✅" if qa.get("status") == "answered" else "⚠️"
                    st.caption(f"Status: {status_badge} {qa.get('status', '—')}")
                    evidence = qa.get("evidence", [])
                    if evidence:
                        st.markdown("*Evidence:*")
                        for ev_idx, ev in enumerate(evidence):
                            loc = []
                            if ev.get("page"):
                                loc.append(f"p.{ev['page']}")
                            if ev.get("section"):
                                loc.append(ev["section"])
                            loc_str = " · ".join(loc)
                            quote = ev.get("quote", "")

                            row_col_text, row_col_action = st.columns([0.82, 0.18])
                            row_col_text.markdown(
                                f"- *\"{quote}\"* {f'({loc_str})' if loc_str else ''}"
                            )
                            if row_col_action.button(
                                "Find",
                                key=f"results_find_{a['id']}_{qa_idx}_{ev_idx}",
                                use_container_width=True,
                            ):
                                st.session_state[EVIDENCE_FIND_STATE_KEY] = {
                                    "paper_id": a["paper_id"],
                                    "qa_idx": qa_idx,
                                    "ev_idx": ev_idx,
                                    "quote": quote,
                                    "html_path": html_path,
                                    "doctags_path": extraction.doctags_path if extraction else None,
                                    "pdf_path": paper.file_path if paper else None,
                                }
                                st.rerun()
                    st.divider()

        with col_html:
            st.markdown("#### Evidence View")
            active_find_state = st.session_state.get(EVIDENCE_FIND_STATE_KEY)
            selected_here = (
                isinstance(active_find_state, dict)
                and active_find_state.get("paper_id") == a["paper_id"]
            )

            if not selected_here:
                st.info("Click Find next to an evidence quote to search and highlight it in HTML or PDF.")
            else:
                selected_quote = str(active_find_state.get("quote", ""))
                quote_preview = selected_quote if len(selected_quote) <= 140 else f"{selected_quote[:140]}..."
                st.caption(f"Searching for: \"{quote_preview}\"")

                if st.button("Close", key=f"results_find_close_{a['id']}", use_container_width=True):
                    st.session_state.pop(EVIDENCE_FIND_STATE_KEY, None)
                    st.rerun()

                html_tab, pdf_tab = st.tabs(["HTML", "PDF"])

                with html_tab:
                    selected_html_path = active_find_state.get("html_path")
                    if not selected_html_path:
                        st.warning("No extracted HTML path is available for this paper.")
                    else:
                        html_file = Path(selected_html_path)
                        if not html_file.exists():
                            st.warning(f"Extracted HTML file not found: {html_file}")
                        else:
                            html_content = html_file.read_text(encoding="utf-8")
                            html_content = inline_images_as_base64(html_content, html_file)
                            highlighted_html, found, strategy = highlight_first_match_in_html(
                                html_content,
                                selected_quote,
                            )
                            if found:
                                if strategy == "exact":
                                    st.success("First exact match highlighted in yellow.")
                                elif strategy == "fallback_1":
                                    st.success("Exact match not found; fallback 1 matched and highlighted in yellow.")
                                elif strategy == "fallback_2":
                                    st.success("Exact match and fallback 1 not found; fallback 2 matched and highlighted in yellow.")
                                else:
                                    st.success("First match highlighted in yellow.")
                            else:
                                st.info("No match found after exact search, fallback 1, and fallback 2.")
                            components.html(highlighted_html, height=900, scrolling=True)

                with pdf_tab:
                    selected_pdf_path = active_find_state.get("pdf_path")
                    selected_doctags_path = active_find_state.get("doctags_path")

                    if not selected_pdf_path:
                        st.warning("No PDF path is stored for this paper.")
                    elif pdf_viewer is None:
                        st.warning("Install streamlit-pdf-viewer to enable in-app PDF previews.")
                    else:
                        pdf_file = Path(selected_pdf_path).expanduser()
                        if not pdf_file.is_absolute():
                            pdf_file = (Path.cwd() / pdf_file).resolve()

                        if not pdf_file.exists():
                            st.warning(f"PDF file not found: {pdf_file}")
                        elif not selected_doctags_path:
                            st.warning("No extracted DocTags path is available for this paper.")
                        else:
                            doctags_file = Path(selected_doctags_path)
                            if not doctags_file.exists():
                                st.warning(f"Extracted DocTags file not found: {doctags_file}")
                            else:
                                doctags_content = doctags_file.read_text(encoding="utf-8")
                                doctags_match, strategy = find_first_match_in_doctags(
                                    doctags_content,
                                    selected_quote,
                                )
                                if doctags_match is None:
                                    st.info("No DocTags match found after exact search, fallback 1, and fallback 2.")
                                    pdf_viewer(
                                        str(pdf_file),
                                        width="100%",
                                        height=900,
                                        viewer_align="left",
                                        zoom_level="auto",
                                        show_page_separator=True,
                                        render_text=True,
                                    )
                                else:
                                    if strategy == "exact":
                                        st.success(f"First DocTags exact match highlighted on page {doctags_match.page}.")
                                    elif strategy == "fallback_1":
                                        st.success(
                                            f"DocTags exact match not found; fallback 1 highlighted first match on page {doctags_match.page}."
                                        )
                                    else:
                                        st.success(
                                            f"DocTags exact match and fallback 1 not found; fallback 2 highlighted first match on page {doctags_match.page}."
                                        )

                                    pdf_viewer(
                                        str(pdf_file),
                                        width="100%",
                                        height=900,
                                        viewer_align="left",
                                        zoom_level="auto",
                                        show_page_separator=True,
                                        render_text=True,
                                        scroll_to_page=doctags_match.page,
                                        annotations=[
                                            doctags_match.to_pdf_annotation(
                                                annotation_id=f"results_bbox_{a['id']}_{active_find_state.get('qa_idx')}_{active_find_state.get('ev_idx')}"
                                            )
                                        ],
                                    )

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
