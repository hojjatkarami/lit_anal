"""Extractions page — browse per-paper extracted content in multiple formats."""
from pathlib import Path

import streamlit as st

from app.db.models import Paper, PaperExtraction
from app.db.session import get_session

st.title("Extractions")

# ── Load data ─────────────────────────────────────────────────────────────────

with get_session() as session:
    papers = session.query(Paper).order_by(Paper.title).all()
    extractions: dict[str, PaperExtraction] = {
        e.paper_id: e
        for e in session.query(PaperExtraction).filter_by(extraction_status="completed").all()
    }
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

col_list, col_viewer = st.columns([1.4, 1], gap="large")

with col_list:
    st.markdown("#### Papers")
    selected_id = st.session_state.get("extractions_selected_paper")

    for row in rows:
        pid = row["paper_id"]
        label = f"**{row['Title']}** ({row['Year']})  `{row['Status']}`"
        is_selected = pid == selected_id
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
            st.warning("This paper has not been extracted yet. Run extraction from the Analysis page.")
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
                        st.code(content, language=_lang)
