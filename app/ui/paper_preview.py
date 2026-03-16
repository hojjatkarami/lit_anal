from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import streamlit as st

try:
    from streamlit_pdf_viewer import pdf_viewer
except ImportError:  # pragma: no cover - optional dependency at runtime
    pdf_viewer = None


def _resolve_pdf_path(file_path: str | None) -> Path | None:
    if not file_path:
        return None
    path = Path(file_path).expanduser()
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def _format_cell(value: Any) -> str:
    if value in (None, ""):
        return "—"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "—"
    return str(value)


def render_paper_table_with_preview(
    rows: Sequence[dict[str, Any]],
    *,
    state_key: str,
    display_columns: Sequence[str],
    title_column: str = "Title",
    viewer_title: str = "PDF Preview",
    viewer_height: int = 900,
    viewer_pane_ratio: float = 1 / 2.4,
    empty_message: str = "No papers to display.",
) -> None:
    if not rows:
        st.info(empty_message)
        return

    selected_row_key = st.session_state.get(state_key)
    available_row_keys = {row.get("row_key", row.get("paper_id")) for row in rows}
    if selected_row_key not in available_row_keys:
        selected_row_key = None
        st.session_state.pop(state_key, None)

    viewer_ratio = min(0.7, max(0.3, viewer_pane_ratio))
    table_ratio = 1.0 - viewer_ratio
    table_col, viewer_col = st.columns([table_ratio, viewer_ratio], gap="large")

    with table_col:
        st.caption("Click a paper title to preview its PDF.")

        column_headers = [title_column, *[c for c in display_columns if c != title_column]]
        column_widths = [3, *([1.2] * (len(column_headers) - 1))]

        header_cols = st.columns(column_widths)
        for idx, column_name in enumerate(column_headers):
            header_cols[idx].markdown(f"**{column_name}**")

        for row in rows:
            row_key = row.get("row_key", row.get("paper_id"))
            row_cols = st.columns(column_widths)
            is_selected = selected_row_key == row_key
            if row_cols[0].button(
                _format_cell(row.get(title_column)),
                key=f"{state_key}_{row_key}",
                type="secondary" if is_selected else "tertiary",
                use_container_width=True,
            ):
                st.session_state[state_key] = row_key

            for idx, column_name in enumerate(column_headers[1:], start=1):
                row_cols[idx].write(_format_cell(row.get(column_name)))

    selected_row = next(
        (
            row
            for row in rows
            if row.get("row_key", row.get("paper_id")) == st.session_state.get(state_key)
        ),
        None,
    )

    with viewer_col:
        st.subheader(viewer_title)

        if selected_row is None:
            st.info("Select a paper title to open its PDF.")
            return

        st.caption(_format_cell(selected_row.get(title_column)))

        pdf_path = _resolve_pdf_path(selected_row.get("file_path"))
        if pdf_path is None:
            st.warning("No PDF path is stored for this paper.")
            return
        if not pdf_path.exists():
            st.warning(f"PDF file not found: {pdf_path}")
            return
        if pdf_viewer is None:
            st.warning("Install streamlit-pdf-viewer to enable in-app PDF previews.")
            return

        st.caption(str(pdf_path))
        pdf_viewer(
            str(pdf_path),
            width="100%",
            height=viewer_height,
            viewer_align="left",
            zoom_level="auto",
            show_page_separator=True,
            render_text=True,
        )