"""Zotero API client wrapping pyzotero."""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyzotero import zotero


@dataclass
class ZoteroAttachment:
    item_key: str
    parent_key: str | None
    title: str
    content_type: str
    filename: str


@dataclass
class ZoteroItem:
    key: str
    item_type: str
    title: str | None
    short_title: str | None
    citation_key: str | None
    authors: list[str]
    year: int | None
    doi: str | None
    venue: str | None
    pdf_attachments: list[ZoteroAttachment]


@dataclass
class ZoteroCollection:
    key: str
    name: str
    parent_key: str | None
    path: str


class ZoteroClient:
    def __init__(self, api_key: str, library_id: str, library_type: str = "user"):
        self.api_key = api_key
        self.library_id = library_id
        self.library_type = library_type
        self._zot = zotero.Zotero(
            library_id=library_id,
            library_type=library_type,
            api_key=api_key,
        )

    def clone(self) -> "ZoteroClient":
        """Create an equivalent client for concurrent requests."""
        return type(self)(
            api_key=self.api_key,
            library_id=self.library_id,
            library_type=self.library_type,
        )

    # ── item listing ──────────────────────────────────────────────────────────

    def get_collections(self) -> list[ZoteroCollection]:
        """Return all collections with computed display paths."""
        raw_collections = self._zot.everything(self._zot.collections())

        by_key: dict[str, dict[str, Any]] = {}
        for raw in raw_collections:
            data = raw.get("data", {})
            key = data.get("key")
            name = data.get("name")
            if key and name:
                by_key[key] = data

        path_cache: dict[str, str] = {}

        def _build_path(collection_key: str) -> str:
            if collection_key in path_cache:
                return path_cache[collection_key]

            data = by_key[collection_key]
            parent_key = data.get("parentCollection")
            name = data.get("name", collection_key)
            if parent_key and parent_key in by_key:
                path = f"{_build_path(parent_key)} / {name}"
            else:
                path = name
            path_cache[collection_key] = path
            return path

        collections: list[ZoteroCollection] = []
        for key, data in by_key.items():
            collections.append(
                ZoteroCollection(
                    key=key,
                    name=data.get("name", key),
                    parent_key=data.get("parentCollection"),
                    path=_build_path(key),
                )
            )

        return sorted(collections, key=lambda c: c.path.lower())

    def resolve_collection_scope(self, root_collection_key: str) -> list[str]:
        """Return selected collection key plus all descendant collection keys."""
        collections = self.get_collections()
        children_by_parent: dict[str | None, list[str]] = {}
        valid_keys: set[str] = set()

        for collection in collections:
            valid_keys.add(collection.key)
            children_by_parent.setdefault(collection.parent_key, []).append(collection.key)

        if root_collection_key not in valid_keys:
            raise ValueError(f"Collection key not found: {root_collection_key}")

        ordered: list[str] = []
        stack = [root_collection_key]
        while stack:
            current = stack.pop()
            ordered.append(current)
            children = sorted(children_by_parent.get(current, []), reverse=True)
            stack.extend(children)

        return ordered

    def get_all_top_items(self, collection_key: str | None = None) -> list[dict[str, Any]]:
        """Return all top-level items, optionally scoped to a collection subtree."""
        if collection_key is None:
            return self._zot.everything(self._zot.top())

        scoped_items: list[dict[str, Any]] = []
        seen_item_keys: set[str] = set()
        for key in self.resolve_collection_scope(collection_key):
            items = self._zot.everything(self._zot.collection_items(key))
            for item in items:
                data = item.get("data", {})
                item_key = data.get("key")
                if not item_key or item_key in seen_item_keys:
                    continue
                if not _is_top_level_zotero_item(item):
                    continue
                seen_item_keys.add(item_key)
                scoped_items.append(item)

        return scoped_items

    def get_pdf_attachments(self, item_key: str) -> list[ZoteroAttachment]:
        """Return PDF child attachments for a given parent item key."""
        children = self._zot.children(item_key)
        attachments = []
        for child in children:
            data = child.get("data", {})
            if (
                data.get("itemType") == "attachment"
                and data.get("contentType") == "application/pdf"
            ):
                attachments.append(
                    ZoteroAttachment(
                        item_key=data["key"],
                        parent_key=item_key,
                        title=data.get("title", ""),
                        content_type=data.get("contentType", ""),
                        filename=data.get("filename", f"{data['key']}.pdf"),
                    )
                )
        return attachments

    # ── download ──────────────────────────────────────────────────────────────

    def download_pdf(self, attachment_key: str, dest_dir: Path) -> tuple[Path, str]:
        """Download a PDF attachment and return (local_path, sha256_hex)."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=dest_dir) as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            self._zot.dump(attachment_key, path=str(temp_dir))
            written = sorted(
                (path for path in temp_dir.rglob("*") if path.is_file()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if not written:
                raise RuntimeError(f"Could not locate downloaded file for key {attachment_key}")

            downloaded_path = written[0]
            suffix = downloaded_path.suffix or ".pdf"
            local_path = dest_dir / f"{attachment_key}{suffix.lower()}"
            if local_path.exists():
                local_path.unlink()
            shutil.move(str(downloaded_path), str(local_path))

        file_hash = _sha256(local_path)
        return local_path, file_hash

    # ── metadata mapping ──────────────────────────────────────────────────────

    @staticmethod
    def map_item_to_fields(raw: dict[str, Any]) -> dict[str, Any]:
        """Convert a raw Zotero item dict into Paper model field values."""
        data = raw.get("data", {})
        creators = data.get("creators", [])
        authors = [
            " ".join(filter(None, [c.get("firstName", ""), c.get("lastName", "")])).strip()
            or c.get("name", "")
            for c in creators
        ]
        year = None
        date_str = data.get("date", "")
        if date_str:
            for part in str(date_str).split("-"):
                part = part.strip()
                if part.isdigit() and len(part) == 4:
                    year = int(part)
                    break

        return {
            "zotero_key": data.get("key"),
            "title": data.get("title") or None,
            "short_title": (data.get("shortTitle") or "").strip() or None,
            "citation_key": (data.get("citationKey") or "").strip() or None,
            "authors": [a for a in authors if a] or None,
            "year": year,
            "doi": data.get("DOI") or None,
            "venue": data.get("publicationTitle") or data.get("conferenceName") or None,
        }


# ── helpers ───────────────────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_top_level_zotero_item(raw_item: dict[str, Any]) -> bool:
    """Return True when item is a top-level bibliographic record, not an attachment."""
    data = raw_item.get("data", {})
    item_type = data.get("itemType")
    if item_type in {"attachment", "note", "annotation"}:
        return False
    if data.get("parentItem"):
        return False
    return True
