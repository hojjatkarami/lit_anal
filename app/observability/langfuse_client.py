"""Langfuse observability helpers."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator

from app.config import settings


# ── singleton client ──────────────────────────────────────────────────────────

_client = None


def get_langfuse():
    """Return the Langfuse client singleton (or None if tracing is disabled)."""
    global _client
    if not settings.langfuse_enabled:
        return None
    if _client is None:
        import os
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
        os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
        from langfuse import get_client
        _client = get_client()
    return _client


# ── trace / span helpers ──────────────────────────────────────────────────────

@contextmanager
def trace_run(run_id: str, run_name: str, prompt: str) -> Generator[Any, None, None]:
    """Context manager that wraps an analysis run in a Langfuse trace."""
    lf = get_langfuse()
    if lf is None:
        yield None
        return
    with lf.start_as_current_observation(
        as_type="trace",
        name=run_name,
        metadata={"run_id": run_id, "prompt": prompt[:500]},
    ) as trace:
        yield trace


@contextmanager
def span_paper(paper_id: str, paper_title: str | None) -> Generator[Any, None, None]:
    """Context manager for a per-paper processing span."""
    lf = get_langfuse()
    if lf is None:
        yield None
        return
    with lf.start_as_current_observation(
        as_type="span",
        name=f"paper:{paper_title or paper_id}",
        metadata={"paper_id": paper_id},
    ) as span:
        yield span


@contextmanager
def generation_span(
    model: str,
    input_messages: list[dict],
) -> Generator[Any, None, None]:
    """Context manager for one LLM call; yields the span for updating with usage."""
    lf = get_langfuse()
    if lf is None:
        yield None
        return
    with lf.start_as_current_observation(
        as_type="generation",
        name="llm_call",
        model=model,
        input=input_messages,
    ) as gen:
        yield gen


def flush() -> None:
    """Flush pending Langfuse events (call at app shutdown)."""
    lf = get_langfuse()
    if lf is not None:
        lf.flush()
