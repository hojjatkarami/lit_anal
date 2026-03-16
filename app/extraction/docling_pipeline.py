"""PDF text extraction using Docling."""
from __future__ import annotations

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

    def _write_extraction_markdown(self, paper: Paper, markdown: str) -> str | None:
        if not settings.extraction_write_markdown:
            return None

        output_dir = Path(settings.extraction_markdown_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{paper.id}.md"
        output_path.write_text(markdown, encoding="utf-8")
        return str(output_path)

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
            session.add(extraction)
            session.flush()
            return extraction

        try:
            result = self._converter.convert(paper.file_path)
            text_content = result.document.export_to_markdown()
            markdown_path = self._write_extraction_markdown(paper, text_content)
            extraction.text_content = text_content
            extraction.markdown_path = markdown_path
            extraction.extraction_status = "completed"
            extraction.error_message = None
        except Exception as exc:
            extraction.extraction_status = "failed"
            extraction.error_message = traceback.format_exc()[:4000]
            extraction.markdown_path = None

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
