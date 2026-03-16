"""Scan Zotero library and upsert Paper records into the database."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

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


@dataclass
class _DownloadedAttachment:
    raw_item: dict[str, Any]
    local_path: Path
    file_hash: str


@dataclass
class _ItemProcessingResult:
    title: str
    downloaded_attachments: list[_DownloadedAttachment]
    pdf_found: int
    errors: int


def scan_and_index(
    client: ZoteroClient,
    session: Session,
    dest_dir: Path,
    selected_collection_key: str | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    max_workers: int = 4,
) -> IndexSummary:
    """
    Fetch Zotero items, download their PDFs, deduplicate by SHA256, and upsert
    Paper rows. If selected_collection_key is provided, only that collection
    and its nested subfolders are scanned.

    progress_callback(current, total, label) is called after each item finishes
    processing (used to drive Streamlit progress bars).
    """
    top_items = client.get_all_top_items(collection_key=selected_collection_key)
    total = len(top_items)
    pdf_found = 0
    new_indexed = 0
    duplicates_skipped = 0
    errors = 0

    item_results = _process_items_in_parallel(
        client=client,
        top_items=top_items,
        dest_dir=dest_dir,
        progress_callback=progress_callback,
        max_workers=max_workers,
    )

    for item_result in item_results:
        pdf_found += item_result.pdf_found
        errors += item_result.errors

        for download in item_result.downloaded_attachments:
            existing = session.query(Paper).filter_by(file_hash=download.file_hash).first()
            fields = client.map_item_to_fields(download.raw_item)

            if existing:
                existing.file_path = str(download.local_path)
                existing.zotero_collection_key = selected_collection_key
                for field_name, value in fields.items():
                    setattr(existing, field_name, value)
                duplicates_skipped += 1
                continue

            paper = Paper(
                file_hash=download.file_hash,
                file_path=str(download.local_path),
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


def _process_items_in_parallel(
    client: ZoteroClient,
    top_items: list[dict[str, Any]],
    dest_dir: Path,
    progress_callback: Callable[[int, int, str], None] | None,
    max_workers: int,
) -> list[_ItemProcessingResult]:
    total = len(top_items)
    if total == 0:
        return []

    bounded_workers = max(1, min(max_workers, total))
    if bounded_workers == 1:
        results: list[_ItemProcessingResult] = []
        for idx, raw_item in enumerate(top_items, start=1):
            result = _process_single_item(client=client, raw_item=raw_item, dest_dir=dest_dir)
            if progress_callback:
                progress_callback(idx, total, result.title)
            results.append(result)
        return results

    results = []
    completed = 0
    with ThreadPoolExecutor(max_workers=bounded_workers) as executor:
        futures = [
            executor.submit(_process_single_item, client, raw_item, dest_dir)
            for raw_item in top_items
        ]
        for future in as_completed(futures):
            result = future.result()
            completed += 1
            if progress_callback:
                progress_callback(completed, total, result.title)
            results.append(result)

    return results


def _process_single_item(
    client: ZoteroClient,
    raw_item: dict[str, Any],
    dest_dir: Path,
) -> _ItemProcessingResult:
    item_key = raw_item.get("data", {}).get("key", "")
    item_title = raw_item.get("data", {}).get("title", item_key)
    worker_client = client.clone() if hasattr(client, "clone") else client

    try:
        attachments = worker_client.get_pdf_attachments(item_key)
    except Exception:
        return _ItemProcessingResult(
            title=item_title,
            downloaded_attachments=[],
            pdf_found=0,
            errors=1,
        )

    downloaded_attachments: list[_DownloadedAttachment] = []
    errors = 0
    for attachment in attachments:
        try:
            local_path, file_hash = worker_client.download_pdf(attachment.item_key, dest_dir)
        except Exception:
            errors += 1
            continue
        downloaded_attachments.append(
            _DownloadedAttachment(
                raw_item=raw_item,
                local_path=local_path,
                file_hash=file_hash,
            )
        )

    return _ItemProcessingResult(
        title=item_title,
        downloaded_attachments=downloaded_attachments,
        pdf_found=len(attachments),
        errors=errors,
    )
