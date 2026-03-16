"""Data Source page — connect to Zotero, scan and index papers."""
from pathlib import Path

import streamlit as st

from app.config import settings
from app.db.session import check_connection, get_session
from app.ingestion.indexer import get_all_papers, scan_and_index
from app.ingestion.zotero_client import ZoteroClient
from app.ui.paper_preview import render_paper_table_with_preview

st.title("🗂️ Data Source")
st.caption("Connect to Zotero, download PDFs, and index papers into the database.")

# ── DB status ─────────────────────────────────────────────────────────────────

with st.expander("Database status", expanded=False):
    if check_connection():
        st.success("SQLite connected.")
    else:
        st.error(
            "Cannot connect to SQLite database. "
            "Check DATABASE_URL in your .env and run `alembic upgrade head`."
        )

st.divider()

# ── Zotero credentials ────────────────────────────────────────────────────────

st.subheader("Zotero Credentials")

col1, col2, col3 = st.columns([2, 2, 1])
api_key = col1.text_input(
    "API Key",
    value=settings.zotero_api_key,
    type="password",
    help="Generate at zotero.org/settings/keys",
)
library_id = col2.text_input(
    "Library ID",
    value=settings.zotero_library_id,
    help="Numeric ID visible under your Zotero account settings.",
)
library_type = col3.selectbox(
    "Library Type",
    options=["user", "group"],
    index=0 if settings.zotero_library_type == "user" else 1,
)

pdf_dir_input = st.text_input(
    "PDF Download Directory",
    value=str(settings.pdf_download_dir),
    help="Local path where PDFs will be saved.",
)

st.divider()

# ── Scan & Index ──────────────────────────────────────────────────────────────

st.subheader("Scan & Index Library")

selected_collection_key: str | None = None
scope_mode = st.radio(
    "Scan Scope",
    options=["Entire library", "Selected folder (include subfolders)"],
    horizontal=True,
)

if scope_mode == "Selected folder (include subfolders)":
    if not (api_key and library_id):
        st.info("Enter Zotero credentials to load available folders.")
    else:
        try:
            browse_client = ZoteroClient(
                api_key=api_key,
                library_id=library_id,
                library_type=library_type,
            )
            collections = browse_client.get_collections()
            if not collections:
                st.warning("No folders were found in this Zotero library.")
            else:
                collection_labels = {
                    f"{collection.path} ({collection.key})": collection.key
                    for collection in collections
                }
                selected_label = st.selectbox(
                    "Folder",
                    options=list(collection_labels.keys()),
                    help="Only this folder and all nested subfolders will be scanned.",
                )
                selected_collection_key = collection_labels[selected_label]
        except Exception as exc:
            st.warning(f"Could not load Zotero folders: {exc}")

if st.button("🔄 Scan & Index", type="primary", disabled=not (api_key and library_id)):
    if not check_connection():
        st.error("Database not reachable. Cannot index papers.")
    else:
        client = ZoteroClient(
            api_key=api_key,
            library_id=library_id,
            library_type=library_type,
        )
        dest_dir = Path(pdf_dir_input)
        max_workers = max(1, int(getattr(settings, "zotero_max_concurrent_requests", 4)))

        progress_bar = st.progress(0, text="Connecting to Zotero…")
        status_placeholder = st.empty()

        def _progress(current: int, total: int, label: str) -> None:
            pct = int(current / max(total, 1) * 100)
            progress_bar.progress(pct, text=f"[{current}/{total}] {label[:80]}")
            status_placeholder.caption(f"Processing: {label}")

        try:
            with get_session() as session:
                summary = scan_and_index(
                    client=client,
                    session=session,
                    dest_dir=dest_dir,
                    selected_collection_key=selected_collection_key,
                    progress_callback=_progress,
                    max_workers=max_workers,
                )
            progress_bar.progress(100, text="Done.")
            st.success(
                f"Scan complete — "
                f"**{summary.total_items}** top-level items found, "
                f"**{summary.pdf_found}** PDFs, "
                f"**{summary.new_indexed}** new papers indexed, "
                f"**{summary.duplicates_skipped}** duplicates skipped, "
                f"**{summary.errors}** errors."
            )
        except Exception as exc:
            st.error(f"Scan failed: {exc}")

st.divider()

# ── Indexed papers table ──────────────────────────────────────────────────────

st.subheader("Indexed Papers")

if check_connection():
    try:
        with get_session() as session:
            papers = get_all_papers(session)

        if papers:
            show_short_title = any((p.short_title or "").strip() for p in papers)
            show_citation_key = any((p.citation_key or "").strip() for p in papers)
            rows = [
                {
                    "paper_id": p.id,
                    "row_key": p.id,
                    "file_path": p.file_path,
                    **{
                        "ID": p.id[:8] + "…",
                        "Title": p.title or "(no title)",
                    },
                    **(
                        {"Short Title": p.short_title or "—"}
                        if show_short_title
                        else {}
                    ),
                    **(
                        {"Citation Key": p.citation_key or "—"}
                        if show_citation_key
                        else {}
                    ),
                    **{
                        "Authors": ", ".join(p.authors or [])[:60] or "—",
                        "Year": p.year or "—",
                        "DOI": p.doi or "—",
                        "File": Path(p.file_path).name if p.file_path else "—",
                    },
                }
                for p in papers
            ]
            display_columns = ["Title"]
            if show_short_title:
                display_columns.append("Short Title")
            if show_citation_key:
                display_columns.append("Citation Key")
            display_columns.extend(["Authors", "Year", "DOI", "File"])
            render_paper_table_with_preview(
                rows,
                state_key="data_source_selected_paper",
                display_columns=display_columns,
                viewer_title="Paper PDF",
                viewer_height=950,
            )
            st.caption(f"Total: {len(papers)} papers")
        else:
            st.info("No papers indexed yet. Run a scan above.")
    except Exception as exc:
        st.warning(f"Could not load papers: {exc}")
