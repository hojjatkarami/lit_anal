"""Extractions page — browse per-paper extracted content in multiple formats."""
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from app.db.models import Paper, PaperExtraction
from app.db.session import get_session
from app.extraction.docling_pipeline import ExtractionPipeline
from app.ui.html_search import inline_images_as_base64

st.title("Extractions")

# ── Load data ─────────────────────────────────────────────────────────────────

with get_session() as session:
    papers = session.query(Paper).order_by(Paper.title).all()
    extraction_rows = session.query(PaperExtraction).all()
    extractions: dict[str, PaperExtraction] = {}
    for ext in extraction_rows:
        previous = extractions.get(ext.paper_id)
        if previous is None:
            extractions[ext.paper_id] = ext
        elif (ext.created_at or 0) > (previous.created_at or 0):
            extractions[ext.paper_id] = ext
    # Detach from session before rendering
    session.expunge_all()

if not papers:
    st.info("No papers indexed yet. Go to Data Source to import papers.")
    st.stop()

# ── Paper selector table ───────────────────────────────────────────────────────

_FORMAT_LABELS = {
    "markdown": ("Markdown", "markdown"),
    "html": ("HTML", "html"),
    "json": ("JSON", "json"),
    "doctags": ("Doctags", "text"),
}

rows = []
for p in papers:
    ext = extractions.get(p.id)
    status = ext.extraction_status if ext else "not extracted"
    rows.append({
        "paper_id": p.id,
        "Title": p.title or p.id,
        "Year": str(p.year) if p.year else "—",
        "Status": status,
    })

viewer_width_pct = st.slider(
    "Content viewer width (%)",
    min_value=30,
    max_value=70,
    value=42,
    step=2,
    key="extractions_viewer_width_pct",
    help="Adjust the width split between the paper list and the content viewer.",
)
list_width = 100 - viewer_width_pct

col_list, col_viewer = st.columns([list_width, viewer_width_pct], gap="large")

with col_list:
    st.markdown("#### Papers")
    selected_id = st.session_state.get("extractions_selected_paper")
    all_paper_ids = [p.id for p in papers]

    # Ensure per-paper checkbox defaults exist in session state
    for pid in all_paper_ids:
        st.session_state.setdefault(f"chk_ext_{pid}", False)

    extract_images = st.checkbox(
        "Extract images",
        value=False,
        help="When enabled, Docling writes extracted image artifacts in addition to text formats.",
    )
    formula_enrichment = st.checkbox(
        "Formula enrichment",
        value=False,
        help="When enabled, Docling runs a formula model to decode math expressions into LaTeX.",
    )

    # Collect currently selected paper IDs
    checked_ids = [pid for pid in all_paper_ids if st.session_state.get(f"chk_ext_{pid}", False)]
    all_checked = len(all_paper_ids) > 0 and len(checked_ids) == len(all_paper_ids)

    ctrl_col1, ctrl_col2 = st.columns([1, 1])
    with ctrl_col1:
        select_all_val = st.checkbox("Select all", value=all_checked)
        if select_all_val != all_checked:
            for pid in all_paper_ids:
                st.session_state[f"chk_ext_{pid}"] = select_all_val
            st.rerun()
    with ctrl_col2:
        run_label = f"Run ({len(checked_ids)})" if checked_ids else "Run"
        run_btn = st.button(run_label, use_container_width=True, disabled=not checked_ids)

    to_run_ids: list[str] = list(checked_ids) if run_btn else []

    if to_run_ids:
        total = len(to_run_ids)
        progress = st.progress(0, text="Starting extraction…")
        pipeline = ExtractionPipeline()
        errors: list[str] = []
        completed = 0
        with get_session() as session:
            for idx, paper_id in enumerate(to_run_ids, start=1):
                paper = session.get(Paper, paper_id)
                if paper is None:
                    errors.append(f"Paper not found: {paper_id}")
                    continue
                title = paper.title or paper.id[:8]
                progress.progress(
                    int((idx - 1) / total * 100),
                    text=f"[{idx}/{total}] extracting {title}",
                )
                extraction = pipeline.extract(
                    paper,
                    session,
                    extract_images=extract_images,
                    formula_enrichment=formula_enrichment,
                )
                if extraction.extraction_status == "failed":
                    errors.append(f"{title}: {extraction.error_message}")
                else:
                    completed += 1

        progress.progress(100, text="Extraction complete.")

        if errors:
            st.warning(
                f"Extraction finished with {len(errors)} error(s). "
                f"Successful: {completed}/{total}."
            )
            for err in errors:
                st.error(err)
        else:
            st.success(f"Extraction completed for {completed} paper(s).")
        st.rerun()

    for row in rows:
        pid = row["paper_id"]
        label = f"**{row['Title']}** ({row['Year']})  `{row['Status']}`"
        is_selected = pid == selected_id
        chk_col, btn_col = st.columns([0.08, 0.92])
        with chk_col:
            st.checkbox("", key=f"chk_ext_{pid}", label_visibility="collapsed")
        with btn_col:
            button_type = "primary" if is_selected else "secondary"
            if st.button(label, key=f"ext_paper_{pid}", use_container_width=True, type=button_type):
                st.session_state["extractions_selected_paper"] = pid
                st.rerun()

with col_viewer:
    st.markdown("#### Content")

    if not selected_id:
        st.info("Select a paper on the left to view its extracted content.")
    else:
        ext = extractions.get(selected_id)

        if ext is None:
            st.warning("This paper has not been extracted yet. Run extraction from this page.")
        else:
            # Build available format tabs
            available = []
            for fmt, (label, _lang) in _FORMAT_LABELS.items():
                path_val = getattr(ext, f"{fmt}_path", None)
                if path_val and Path(path_val).exists():
                    available.append((fmt, label, path_val))

            if not available:
                st.warning("Extraction completed but no output files found on disk.")
            else:
                tab_labels = [label for _, label, _ in available]
                tabs = st.tabs(tab_labels)
                for tab, (fmt, _label, path_val) in zip(tabs, available):
                    with tab:
                        _lang = _FORMAT_LABELS[fmt][1]
                        content = Path(path_val).read_text(encoding="utf-8")
                        if fmt == "html":
                            # Render extracted HTML directly for easier preview.
                            # Inline images as base64 so they display inside
                            # Streamlit's srcdoc iframe (relative paths break there).
                            content = inline_images_as_base64(content, path_val)
                            components.html(content, height=800, scrolling=True)
                        else:
                            st.code(content, language=_lang)
