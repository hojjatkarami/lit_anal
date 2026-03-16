"""Unit tests for extraction pipeline local markdown export."""
from unittest.mock import MagicMock

from app.config import settings
from app.db.models import Paper
from app.extraction.docling_pipeline import ExtractionPipeline


def _mock_query_with_first(first_value):
    query = MagicMock()
    query.filter_by.return_value.first.return_value = first_value
    return query


def test_extract_writes_markdown_file(tmp_path, monkeypatch):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(settings, "extraction_write_markdown", True)
    monkeypatch.setattr(settings, "extraction_markdown_dir", tmp_path / "extractions")

    pipeline = ExtractionPipeline.__new__(ExtractionPipeline)
    pipeline._converter = MagicMock()
    pipeline._converter.convert.return_value.document.export_to_markdown.return_value = "# Extracted"

    session = MagicMock()
    session.query.side_effect = [
        _mock_query_with_first(None),
        _mock_query_with_first(None),
    ]

    paper = Paper(id="paper-1", file_hash="abc", file_path=str(pdf_path))
    extraction = pipeline.extract(paper, session)

    out_file = (tmp_path / "extractions" / "paper-1.md")
    assert out_file.exists()
    assert out_file.read_text(encoding="utf-8") == "# Extracted"
    assert extraction.extraction_status == "completed"
    assert extraction.text_content == "# Extracted"
    assert extraction.markdown_path == str(out_file)


def test_extract_without_markdown_export_keeps_markdown_path_none(tmp_path, monkeypatch):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(settings, "extraction_write_markdown", False)
    monkeypatch.setattr(settings, "extraction_markdown_dir", tmp_path / "extractions")

    pipeline = ExtractionPipeline.__new__(ExtractionPipeline)
    pipeline._converter = MagicMock()
    pipeline._converter.convert.return_value.document.export_to_markdown.return_value = "# Extracted"

    session = MagicMock()
    session.query.side_effect = [
        _mock_query_with_first(None),
        _mock_query_with_first(None),
    ]

    paper = Paper(id="paper-2", file_hash="def", file_path=str(pdf_path))
    extraction = pipeline.extract(paper, session)

    out_file = (tmp_path / "extractions" / "paper-2.md")
    assert not out_file.exists()
    assert extraction.extraction_status == "completed"
    assert extraction.markdown_path is None
