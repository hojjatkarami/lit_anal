"""Utilities for locating evidence quotes in DocTags and building PDF annotations."""
from __future__ import annotations

import re
from dataclasses import dataclass

_SEGMENT_PATTERN = re.compile(r"<loc_(\d+)><loc_(\d+)><loc_(\d+)><loc_(\d+)>([^<]+)")
_TOKEN_GAP_PATTERN = r"(?:\s|&nbsp;|<[^>]+>)+"


@dataclass(frozen=True)
class DoctagsMatch:
    """First matched DocTags text segment and its bounding box metadata."""

    page: int
    left: float
    top: float
    right: float
    bottom: float
    text: str
    strategy: str

    def to_pdf_annotation(self, *, annotation_id: str = "evidence_bbox") -> dict[str, object]:
        """Convert to streamlit-pdf-viewer annotation payload."""
        width = max(self.right - self.left, 1.0)
        height = max(self.bottom - self.top, 1.0)
        return {
            "id": annotation_id,
            "page": self.page,
            "x": self.left,
            "y": self.top,
            "width": width,
            "height": height,
            "color": "#ffeb3b",
            "border": 2,
        }


def _normalize_whitespace(value: str) -> str:
    return " ".join((value or "").split())


def _iter_doctags_segments(doctags_content: str) -> list[tuple[int, float, float, float, float, str]]:
    page = 1
    segments: list[tuple[int, float, float, float, float, str]] = []

    cursor = 0
    while cursor < len(doctags_content):
        page_break_index = doctags_content.find("<page_break>", cursor)
        chunk_end = page_break_index if page_break_index != -1 else len(doctags_content)
        chunk = doctags_content[cursor:chunk_end]

        for match in _SEGMENT_PATTERN.finditer(chunk):
            left = float(match.group(1))
            top = float(match.group(2))
            right = float(match.group(3))
            bottom = float(match.group(4))
            text = match.group(5).strip()
            if not text:
                continue
            segments.append((page, left, top, right, bottom, text))

        if page_break_index == -1:
            break

        cursor = page_break_index + len("<page_break>")
        page += 1

    return segments


def find_first_match_in_doctags(doctags_content: str, search_text: str) -> tuple[DoctagsMatch | None, str]:
    """Return the first DocTags bbox match for a quote and the strategy name."""
    query = (search_text or "").strip()
    if not query:
        return None, "none"

    segments = _iter_doctags_segments(doctags_content)
    if not segments:
        return None, "none"

    exact_pattern = re.compile(re.escape(query), flags=re.IGNORECASE)
    for page, left, top, right, bottom, text in segments:
        if exact_pattern.search(text):
            return DoctagsMatch(page, left, top, right, bottom, text, "exact"), "exact"

    query_normalized = _normalize_whitespace(query)
    if query_normalized:
        for page, left, top, right, bottom, text in segments:
            if query_normalized.lower() in _normalize_whitespace(text).lower():
                return DoctagsMatch(page, left, top, right, bottom, text, "fallback_1"), "fallback_1"

    tokens = [re.escape(part) for part in query.split() if part]
    if len(tokens) > 1:
        fallback_2_pattern = re.compile(_TOKEN_GAP_PATTERN.join(tokens), flags=re.IGNORECASE)
        for page, left, top, right, bottom, text in segments:
            if fallback_2_pattern.search(text):
                return DoctagsMatch(page, left, top, right, bottom, text, "fallback_2"), "fallback_2"

    return None, "none"
