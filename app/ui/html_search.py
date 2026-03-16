"""Utilities for evidence text find/highlight inside extracted HTML."""
from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path

_HIGHLIGHT_ID = "evidence-find-match"
_HIGHLIGHT_STYLE = "background-color: #ffeb3b; color: inherit; padding: 0;"

_IMG_SRC_RE = re.compile(r'(<img[^>]+src=["\'])(?!data:|https?://|//)(.*?)(["\'])', re.IGNORECASE)


def inline_images_as_base64(html_content: str, html_file_path: str | Path) -> str:
    """Replace relative <img src> paths with base64 data URIs.

    Streamlit's ``components.html`` renders inside a srcdoc iframe which has no
    filesystem context, so relative image paths resolve against the Streamlit
    server URL instead of the local disk.  This function embeds each image
    directly so the rendered HTML is self-contained.
    """
    html_dir = Path(html_file_path).parent

    def _replace(match: re.Match[str]) -> str:
        prefix, rel_path, quote = match.group(1), match.group(2), match.group(3)
        img_path = (html_dir / rel_path).resolve()
        if not img_path.exists():
            return match.group(0)
        mime, _ = mimetypes.guess_type(str(img_path))
        mime = mime or "image/png"
        data = base64.b64encode(img_path.read_bytes()).decode()
        return f"{prefix}data:{mime};base64,{data}{quote}"

    return _IMG_SRC_RE.sub(_replace, html_content)


def _inject_scroll_script(highlighted_html: str) -> str:
    auto_scroll_script = (
        "<script>"
        "window.addEventListener('load', function() {"
        f"var target = document.getElementById('{_HIGHLIGHT_ID}');"
        "if (target) { target.scrollIntoView({behavior: 'smooth', block: 'center'}); }"
        "});"
        "</script>"
    )

    if re.search(r"</body>", highlighted_html, flags=re.IGNORECASE):
        return re.sub(
            r"</body>",
            auto_scroll_script + "</body>",
            highlighted_html,
            count=1,
            flags=re.IGNORECASE,
        )
    return highlighted_html + auto_scroll_script


def _highlight_with_pattern(
    html_content: str,
    pattern: re.Pattern[str],
) -> tuple[str, bool]:
    def _replace(match: re.Match[str]) -> str:
        text = match.group(0)
        return f'<mark id="{_HIGHLIGHT_ID}" style="{_HIGHLIGHT_STYLE}">{text}</mark>'

    highlighted_html, replacement_count = pattern.subn(_replace, html_content, count=1)
    if replacement_count == 0:
        return html_content, False

    return _inject_scroll_script(highlighted_html), True


def highlight_first_match_in_html(html_content: str, search_text: str) -> tuple[str, bool, str]:
    """Highlight the first case-insensitive exact match in HTML content.

    Returns a tuple of (updated_html, found, strategy). If a match is found, the
    returned HTML includes a yellow <mark> wrapper and an auto-scroll script to
    bring the highlighted match into view when rendered in an iframe.

    Match strategies are attempted in order:
    - "exact": case-insensitive direct text match
    - "fallback_1": whitespace-normalized exact match
    - "fallback_2": whitespace/tag-gap tolerant match
    """
    query = (search_text or "").strip()
    if not query:
        return html_content, False, "none"

    exact_pattern = re.compile(re.escape(query), flags=re.IGNORECASE)
    highlighted_html, found = _highlight_with_pattern(html_content, exact_pattern)
    if found:
        return highlighted_html, True, "exact"

    tokens = [re.escape(part) for part in query.split() if part]
    if len(tokens) <= 1:
        return html_content, False, "none"

    fallback_1_pattern = re.compile(r"\s+".join(tokens), flags=re.IGNORECASE)
    highlighted_html, found = _highlight_with_pattern(html_content, fallback_1_pattern)
    if found:
        return highlighted_html, True, "fallback_1"

    fallback_2_pattern = re.compile(
        r"(?:\s|&nbsp;|<[^>]+>)+".join(tokens),
        flags=re.IGNORECASE,
    )
    highlighted_html, found = _highlight_with_pattern(html_content, fallback_2_pattern)
    if found:
        return highlighted_html, True, "fallback_2"

    return html_content, False, "none"
