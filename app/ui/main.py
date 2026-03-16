"""Streamlit application entry-point — multi-page navigation."""
import streamlit as st

st.set_page_config(
    page_title="Literature Analysis Synthesizer",
    page_icon="📚",
    layout="wide",
)

data_source = st.Page("pages/data_source.py", title="Data Source", icon="🗂️")
analysis = st.Page("pages/analysis.py", title="Analysis", icon="🔬")
results = st.Page("pages/results.py", title="Results", icon="📊")

pg = st.navigation([data_source, analysis, results])
pg.run()
