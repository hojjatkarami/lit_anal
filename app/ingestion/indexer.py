"""Scan Zotero library and upsert Paper records into the database."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from app.db.models import Paper
from app.ingestion.zotero_client import ZoteroClient


@dataclass
class IndexSummary:
    total_items: int
    pdf_found: int
    new_indexed: int
    duplicates_skipped: int
    errors: int


def scan_and_index(
    client: ZoteroClient,
    session: Session,
    dest_dir: Path,
    selected_collection_key: str | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> IndexSummary:
    """
    Fetch Zotero items, download their PDFs, deduplicate by SHA256, and upsert
    Paper rows. If selected_collection_key is provided, only that collection
    and its nested subfolders are scanned.

    progress_callback(current, total, label) is called after each item is
    processed (used to drive Streamlit progress bars).
    """
    top_items = client.get_all_top_items(collection_key=selected_collection_key)
    total = len(top_items)
    pdf_found = 0
    new_indexed = 0
    duplicates_skipped = 0
    errors = 0

    for idx, raw_item in enumerate(top_items, start=1):
        item_key = raw_item.get("data", {}).get("key", "")
        item_title = raw_item.get("data", {}).get("title", item_key)

        if progress_callback:
            progress_callback(idx, total, item_title)

        try:
            attachments = client.get_pdf_attachments(item_key)
        except Exception:
            errors += 1
            continue

        for attachment in attachments:
            pdf_found += 1
            try:
                local_path, file_hash = client.download_pdf(attachment.item_key, dest_dir)
            except Exception:
                errors += 1
                continue

            existing = session.query(Paper).filter_by(file_hash=file_hash).first()
            if existing:
                fields = client.map_item_to_fields(raw_item)
                existing.file_path = str(local_path)
                existing.zotero_collection_key = selected_collection_key
                for field_name, value in fields.items():
                    setattr(existing, field_name, value)
                duplicates_skipped += 1
                continue

            fields = client.map_item_to_fields(raw_item)
            paper = Paper(
                file_hash=file_hash,
                file_path=str(local_path),
                zotero_collection_key=selected_collection_key,
                **fields,
            )
            session.add(paper)
            new_indexed += 1

    session.flush()

    return IndexSummary(
        total_items=total,
        pdf_found=pdf_found,
        new_indexed=new_indexed,
        duplicates_skipped=duplicates_skipped,
        errors=errors,
    )


def get_all_papers(session: Session) -> list[Paper]:
    return session.query(Paper).order_by(Paper.created_at.desc()).all()
