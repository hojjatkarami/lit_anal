"""PDF text extraction using Docling."""
from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Paper, PaperExtraction


class ExtractionPipeline:
    def __init__(self) -> None:
        # Lazy-import Docling so import errors are surfaced at extraction time,
        # not at app startup.
        from docling.document_converter import DocumentConverter
        self._DocumentConverter = DocumentConverter
        self._converter_cache: dict[tuple[bool, bool], object] = {}

    def _get_converter(self, *, extract_images: bool, formula_enrichment: bool):
        key = (extract_images, formula_enrichment)
        if key not in self._converter_cache:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import PdfFormatOption

            pipeline_options = PdfPipelineOptions(
                generate_picture_images=extract_images,
                do_formula_enrichment=formula_enrichment,
            )
            self._converter_cache[key] = self._DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
        return self._converter_cache[key]

    def _write_extraction_files(
        self, paper: Paper, result: Any, *, extract_images: bool
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
            "images_dir": None,
        }

        image_mode = None
        images_dir: Path | None = None
        if extract_images:
            from docling_core.types.doc.base import ImageRefMode

            image_mode = ImageRefMode.REFERENCED
            images_dir = base / "images" / paper.id
            images_dir.mkdir(parents=True, exist_ok=True)

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
            if extract_images and fmt in {"markdown", "html", "json"}:
                if fmt == "markdown":
                    result.document.save_as_markdown(
                        out_path,
                        artifacts_dir=images_dir,
                        image_mode=image_mode,
                    )
                elif fmt == "html":
                    result.document.save_as_html(
                        out_path,
                        artifacts_dir=images_dir,
                        image_mode=image_mode,
                    )
                else:
                    result.document.save_as_json(
                        out_path,
                        artifacts_dir=images_dir,
                        image_mode=image_mode,
                    )
            else:
                out_path.write_text(exporter(), encoding="utf-8")
            paths[fmt] = str(out_path)

        if images_dir:
            if any(images_dir.glob("*")):
                paths["images_dir"] = str(images_dir)
            else:
                images_dir.rmdir()

        return paths

    def extract(
        self,
        paper: Paper,
        session: Session,
        *,
        extract_images: bool | None = None,
        formula_enrichment: bool | None = None,
    ) -> PaperExtraction:
        """
        Extract text from the PDF attached to *paper* and persist a
        PaperExtraction record.  Idempotent: if a 'completed' extraction
        already exists it is returned unchanged.
        """
        should_extract_images = (
            settings.extraction_extract_images
            if extract_images is None
            else extract_images
        )
        should_formula_enrichment = (
            settings.extraction_formula_enrichment
            if formula_enrichment is None
            else formula_enrichment
        )

        existing = (
            session.query(PaperExtraction)
            .filter_by(paper_id=paper.id, extraction_status="completed")
            .first()
        )
        if existing and not should_extract_images:
            return existing
        if existing and should_extract_images:
            existing_images_dir = getattr(existing, "images_dir", None)
            has_images = bool(existing_images_dir and Path(existing_images_dir).exists())
            if has_images:
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
            if hasattr(extraction, "images_dir"):
                extraction.images_dir = None
            session.add(extraction)
            session.flush()
            return extraction

        try:
            converter = self._get_converter(
                extract_images=should_extract_images,
                formula_enrichment=should_formula_enrichment,
            )
            result = converter.convert(paper.file_path)
            text_content = result.document.export_to_markdown()
            paths = self._write_extraction_files(
                paper,
                result,
                extract_images=should_extract_images,
            )
            extraction.text_content = text_content
            extraction.markdown_path = paths["markdown"]
            extraction.html_path = paths["html"]
            extraction.json_path = paths["json"]
            extraction.doctags_path = paths["doctags"]
            if hasattr(extraction, "images_dir"):
                extraction.images_dir = paths["images_dir"]
            extraction.extraction_status = "completed"
            extraction.error_message = None
        except Exception as exc:
            extraction.extraction_status = "failed"
            extraction.error_message = traceback.format_exc()[:4000]
            extraction.markdown_path = None
            extraction.html_path = None
            extraction.json_path = None
            extraction.doctags_path = None
            if hasattr(extraction, "images_dir"):
                extraction.images_dir = None

        session.add(extraction)
        session.flush()
        return extraction

    def extract_batch(
        self,
        papers: list[Paper],
        session: Session,
        progress_callback=None,
        *,
        extract_images: bool | None = None,
        formula_enrichment: bool | None = None,
    ) -> list[PaperExtraction]:
        """Extract a list of papers sequentially with optional progress updates."""
        results = []
        total = len(papers)
        for idx, paper in enumerate(papers, start=1):
            if progress_callback:
                progress_callback(idx, total, paper.title or paper.id)
            extraction = self.extract(
                paper,
                session,
                extract_images=extract_images,
                formula_enrichment=formula_enrichment,
            )
            results.append(extraction)
        return results

