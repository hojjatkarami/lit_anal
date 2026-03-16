"""PDF text extraction using Docling."""
from __future__ import annotations

import json
import traceback
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Paper, PaperExtraction


class ExtractionPipeline:
    def __init__(self) -> None:
        # Lazy-import Docling so import errors are surfaced at extraction time,
        # not at app startup.
        from docling.document_converter import DocumentConverter
        self._converter = DocumentConverter()

    def _write_extraction_files(
        self, paper: Paper, result
    ) -> dict[str, str | None]:
        """Write each enabled format to its own subdirectory under extraction_dir.

        Returns a mapping of format name → absolute file path (or None if disabled).
        """
        base = Path(settings.extraction_dir)
        paths: dict[str, str | None] = {
            "markdown": None,
            "html": None,
            "json": None,
            "doctags": None,
        }

        formats = [
            ("markdown", settings.extraction_write_markdown, ".md",
             lambda: result.document.export_to_markdown()),
            ("html", settings.extraction_write_html, ".html",
             lambda: result.document.export_to_html()),
            ("json", settings.extraction_write_json, ".json",
             lambda: json.dumps(result.document.export_to_dict(), ensure_ascii=False, indent=2)),
            ("doctags", settings.extraction_write_doctags, ".doctags",
             lambda: result.document.export_to_doctags()),
        ]

        for fmt, enabled, ext, exporter in formats:
            if not enabled:
                continue
            out_dir = base / fmt
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{paper.id}{ext}"
            out_path.write_text(exporter(), encoding="utf-8")
            paths[fmt] = str(out_path)

        return paths

    def extract(self, paper: Paper, session: Session) -> PaperExtraction:
        """
        Extract text from the PDF attached to *paper* and persist a
        PaperExtraction record.  Idempotent: if a 'completed' extraction
        already exists it is returned unchanged.
        """
        existing = (
            session.query(PaperExtraction)
            .filter_by(paper_id=paper.id, extraction_status="completed")
            .first()
        )
        if existing:
            return existing

        extraction = (
            session.query(PaperExtraction)
            .filter_by(paper_id=paper.id)
            .first()
        ) or PaperExtraction(paper_id=paper.id)

        if not paper.file_path or not Path(paper.file_path).exists():
            extraction.extraction_status = "failed"
            extraction.error_message = f"File not found: {paper.file_path}"
            extraction.markdown_path = None
            extraction.html_path = None
            extraction.json_path = None
            extraction.doctags_path = None
            session.add(extraction)
            session.flush()
            return extraction

        try:
            result = self._converter.convert(paper.file_path)
            text_content = result.document.export_to_markdown()
            paths = self._write_extraction_files(paper, result)
            extraction.text_content = text_content
            extraction.markdown_path = paths["markdown"]
            extraction.html_path = paths["html"]
            extraction.json_path = paths["json"]
            extraction.doctags_path = paths["doctags"]
            extraction.extraction_status = "completed"
            extraction.error_message = None
        except Exception as exc:
            extraction.extraction_status = "failed"
            extraction.error_message = traceback.format_exc()[:4000]
            extraction.markdown_path = None
            extraction.html_path = None
            extraction.json_path = None
            extraction.doctags_path = None

        session.add(extraction)
        session.flush()
        return extraction

    def extract_batch(
        self,
        papers: list[Paper],
        session: Session,
        progress_callback=None,
    ) -> list[PaperExtraction]:
        """Extract a list of papers sequentially with optional progress updates."""
        results = []
        total = len(papers)
        for idx, paper in enumerate(papers, start=1):
            if progress_callback:
                progress_callback(idx, total, paper.title or paper.id)
            extraction = self.extract(paper, session)
            results.append(extraction)
        return results

