"""Streamlit application entry-point — multi-page navigation."""
import streamlit as st

from app.db.models import AnalysisRun, Paper, PaperExtraction
from app.db.session import get_session

st.set_page_config(
    page_title="Literature Analysis Synthesizer",
    page_icon="📚",
    layout="wide",
)

# ── Sidebar: Clear all data ───────────────────────────────────────────────────

with st.sidebar:
    st.markdown("---")
    st.markdown("### Danger Zone")
    if st.button("🗑️ Clear All Data", use_container_width=True):
        st.session_state["_confirm_clear"] = True

    if st.session_state.get("_confirm_clear"):
        st.warning(
            "This will permanently delete **all papers, extractions, analysis runs, "
            "and results** from the database. This cannot be undone."
        )
        col_yes, col_no = st.columns(2)
        if col_yes.button("Yes, delete everything", type="primary", use_container_width=True):
            with get_session() as session:
                session.query(AnalysisRun).delete()
                session.query(PaperExtraction).delete()
                session.query(Paper).delete()
            st.session_state["_confirm_clear"] = False
            st.success("All data cleared.")
            st.rerun()
        if col_no.button("Cancel", use_container_width=True):
            st.session_state["_confirm_clear"] = False
            st.rerun()

# ── Navigation ────────────────────────────────────────────────────────────────

data_source = st.Page("pages/data_source.py", title="Data Source", icon="🗂️")
extractions = st.Page("pages/extractions.py", title="Extractions", icon="📄")
analysis = st.Page("pages/analysis.py", title="Analysis", icon="🔬")
results = st.Page("pages/results.py", title="Results", icon="📊")

pg = st.navigation([data_source, extractions, analysis, results])
pg.run()
