"""Unit tests for extraction pipeline local file export."""
from unittest.mock import MagicMock

from app.config import settings
from app.db.models import Paper
from app.extraction.docling_pipeline import ExtractionPipeline


def _mock_query_with_first(first_value):
    query = MagicMock()
    query.filter_by.return_value.first.return_value = first_value
    return query


def _make_pipeline(monkeypatch, tmp_path, *, markdown=True, html=True, json=True, doctags=True):
    """Build a pipeline with a mocked converter and patched settings."""
    monkeypatch.setattr(settings, "extraction_dir", tmp_path / "extractions")
    monkeypatch.setattr(settings, "extraction_write_markdown", markdown)
    monkeypatch.setattr(settings, "extraction_write_html", html)
    monkeypatch.setattr(settings, "extraction_write_json", json)
    monkeypatch.setattr(settings, "extraction_write_doctags", doctags)

    pipeline = ExtractionPipeline.__new__(ExtractionPipeline)
    doc = MagicMock()
    doc.export_to_markdown.return_value = "# Extracted"
    doc.export_to_html.return_value = "<h1>Extracted</h1>"
    doc.export_to_dict.return_value = {"text": "Extracted"}
    doc.export_to_doctags.return_value = "<doctag>Extracted</doctag>"
    pipeline._converter = MagicMock()
    pipeline._converter.convert.return_value.document = doc
    return pipeline


def test_extract_writes_all_formats(tmp_path, monkeypatch):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    pipeline = _make_pipeline(monkeypatch, tmp_path)

    session = MagicMock()
    session.query.side_effect = [
        _mock_query_with_first(None),
        _mock_query_with_first(None),
    ]

    paper = Paper(id="paper-1", file_hash="abc", file_path=str(pdf_path))
    extraction = pipeline.extract(paper, session)

    base = tmp_path / "extractions"
    assert (base / "markdown" / "paper-1.md").read_text(encoding="utf-8") == "# Extracted"
    assert (base / "html" / "paper-1.html").read_text(encoding="utf-8") == "<h1>Extracted</h1>"
    assert "Extracted" in (base / "json" / "paper-1.json").read_text(encoding="utf-8")
    assert (base / "doctags" / "paper-1.doctags").read_text(encoding="utf-8") == "<doctag>Extracted</doctag>"

    assert extraction.extraction_status == "completed"
    assert extraction.text_content == "# Extracted"
    assert extraction.markdown_path == str(base / "markdown" / "paper-1.md")
    assert extraction.html_path == str(base / "html" / "paper-1.html")
    assert extraction.json_path == str(base / "json" / "paper-1.json")
    assert extraction.doctags_path == str(base / "doctags" / "paper-1.doctags")


def test_extract_disabled_format_keeps_path_none(tmp_path, monkeypatch):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    pipeline = _make_pipeline(monkeypatch, tmp_path, html=False, doctags=False)

    session = MagicMock()
    session.query.side_effect = [
        _mock_query_with_first(None),
        _mock_query_with_first(None),
    ]

    paper = Paper(id="paper-2", file_hash="def", file_path=str(pdf_path))
    extraction = pipeline.extract(paper, session)

    base = tmp_path / "extractions"
    assert (base / "markdown" / "paper-2.md").exists()
    assert not (base / "html" / "paper-2.html").exists()
    assert (base / "json" / "paper-2.json").exists()
    assert not (base / "doctags" / "paper-2.doctags").exists()

    assert extraction.extraction_status == "completed"
    assert extraction.html_path is None
    assert extraction.doctags_path is None
    assert extraction.markdown_path is not None
    assert extraction.json_path is not None


def test_extract_all_disabled_keeps_all_paths_none(tmp_path, monkeypatch):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    pipeline = _make_pipeline(monkeypatch, tmp_path, markdown=False, html=False, json=False, doctags=False)

    session = MagicMock()
    session.query.side_effect = [
        _mock_query_with_first(None),
        _mock_query_with_first(None),
    ]

    paper = Paper(id="paper-3", file_hash="ghi", file_path=str(pdf_path))
    extraction = pipeline.extract(paper, session)

    assert extraction.extraction_status == "completed"
    assert extraction.markdown_path is None
    assert extraction.html_path is None
    assert extraction.json_path is None
    assert extraction.doctags_path is None

