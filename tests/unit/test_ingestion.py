"""Unit tests for ingestion — dedup logic and Zotero field mapping."""
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base, Paper
from app.ingestion.indexer import scan_and_index
from app.ingestion.zotero_client import ZoteroClient, _sha256


# ── _sha256 ───────────────────────────────────────────────────────────────────

def test_sha256_produces_expected_hash(tmp_path):
    f = tmp_path / "test.pdf"
    f.write_bytes(b"hello world")
    expected = hashlib.sha256(b"hello world").hexdigest()
    assert _sha256(f) == expected


def test_sha256_different_content_different_hashes(tmp_path):
    f1 = tmp_path / "a.pdf"
    f2 = tmp_path / "b.pdf"
    f1.write_bytes(b"content A")
    f2.write_bytes(b"content B")
    assert _sha256(f1) != _sha256(f2)


# ── map_item_to_fields ────────────────────────────────────────────────────────

RAW_ITEM = {
    "data": {
        "key": "ABC123",
        "title": "A Great Paper",
        "shortTitle": "Great Paper",
        "citationKey": "Doe2023Great",
        "creators": [
            {"firstName": "Jane", "lastName": "Doe"},
            {"firstName": "John", "lastName": "Smith"},
            {"name": "Anonymous Collective"},
        ],
        "date": "2023-05",
        "DOI": "10.1234/example",
        "publicationTitle": "Nature",
    }
}


def test_map_item_extracts_title():
    fields = ZoteroClient.map_item_to_fields(RAW_ITEM)
    assert fields["title"] == "A Great Paper"


def test_map_item_extracts_short_title():
    fields = ZoteroClient.map_item_to_fields(RAW_ITEM)
    assert fields["short_title"] == "Great Paper"


def test_map_item_extracts_citation_key():
    fields = ZoteroClient.map_item_to_fields(RAW_ITEM)
    assert fields["citation_key"] == "Doe2023Great"


def test_map_item_extracts_authors():
    fields = ZoteroClient.map_item_to_fields(RAW_ITEM)
    assert "Jane Doe" in fields["authors"]
    assert "John Smith" in fields["authors"]
    assert "Anonymous Collective" in fields["authors"]


def test_map_item_extracts_year():
    fields = ZoteroClient.map_item_to_fields(RAW_ITEM)
    assert fields["year"] == 2023


def test_map_item_extracts_doi():
    fields = ZoteroClient.map_item_to_fields(RAW_ITEM)
    assert fields["doi"] == "10.1234/example"


def test_map_item_extracts_venue():
    fields = ZoteroClient.map_item_to_fields(RAW_ITEM)
    assert fields["venue"] == "Nature"


def test_map_item_missing_date_returns_none():
    raw = {"data": {"key": "X", "title": "T"}}
    fields = ZoteroClient.map_item_to_fields(raw)
    assert fields["year"] is None


def test_map_item_missing_optional_zotero_fields_return_none():
    raw = {"data": {"key": "X", "title": "T"}}
    fields = ZoteroClient.map_item_to_fields(raw)
    assert fields["short_title"] is None
    assert fields["citation_key"] is None


def test_map_item_empty_optional_zotero_fields_return_none():
    raw = {
        "data": {
            "key": "X",
            "title": "T",
            "shortTitle": "  ",
            "citationKey": "",
        }
    }
    fields = ZoteroClient.map_item_to_fields(raw)
    assert fields["short_title"] is None
    assert fields["citation_key"] is None


def test_map_item_missing_doi_returns_none():
    raw = {"data": {"key": "X", "title": "T"}}
    fields = ZoteroClient.map_item_to_fields(raw)
    assert fields["doi"] is None


def test_map_item_empty_creators_returns_none():
    raw = {"data": {"key": "X", "creators": []}}
    fields = ZoteroClient.map_item_to_fields(raw)
    assert fields["authors"] is None


def test_scan_and_index_refreshes_metadata_for_existing_duplicate(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"same paper")
    file_hash = _sha256(pdf_path)

    with Session(engine) as session:
        session.add(
            Paper(
                file_hash=file_hash,
                file_path="old/path.pdf",
                zotero_key="OLDKEY",
                title="Old Title",
            )
        )
        session.commit()

        client = MagicMock()
        client.get_all_top_items.return_value = [{"data": {"key": "ITEM1", "title": "New Title"}}]
        client.get_pdf_attachments.return_value = [MagicMock(item_key="ATTACH1")]
        client.download_pdf.return_value = (pdf_path, file_hash)
        client.clone.return_value = client
        client.map_item_to_fields.return_value = {
            "zotero_key": "NEWKEY",
            "title": "New Title",
            "short_title": "Short New",
            "citation_key": "Doe2026New",
            "authors": ["Jane Doe"],
            "year": 2026,
            "doi": "10.1000/new",
            "venue": "Science",
        }

        summary = scan_and_index(
            client=client,
            session=session,
            dest_dir=tmp_path,
            selected_collection_key="COLL1",
        )
        session.commit()

        paper = session.query(Paper).filter_by(file_hash=file_hash).one()

    assert summary.new_indexed == 0
    assert summary.duplicates_skipped == 1
    assert paper.file_path == str(pdf_path)
    assert paper.zotero_key == "NEWKEY"
    assert paper.zotero_collection_key == "COLL1"
    assert paper.title == "New Title"
    assert paper.short_title == "Short New"
    assert paper.citation_key == "Doe2026New"
    assert paper.authors == ["Jane Doe"]
    assert paper.year == 2026
    assert paper.doi == "10.1000/new"
    assert paper.venue == "Science"


def test_scan_and_index_uses_worker_clones_when_parallelized(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"parallel paper")
    file_hash = _sha256(pdf_path)

    worker_client = MagicMock()
    worker_client.get_pdf_attachments.side_effect = [
        [MagicMock(item_key="ATTACH1")],
        [MagicMock(item_key="ATTACH2")],
    ]
    worker_client.download_pdf.side_effect = [
        (pdf_path, file_hash),
        (pdf_path, file_hash),
    ]

    client = MagicMock()
    client.get_all_top_items.return_value = [
        {"data": {"key": "ITEM1", "title": "Paper 1"}},
        {"data": {"key": "ITEM2", "title": "Paper 2"}},
    ]
    client.clone.return_value = worker_client
    client.map_item_to_fields.return_value = {
        "zotero_key": "NEWKEY",
        "title": "Parallel Title",
        "short_title": None,
        "citation_key": None,
        "authors": ["Jane Doe"],
        "year": 2026,
        "doi": None,
        "venue": None,
    }

    progress_events: list[tuple[int, int, str]] = []

    with Session(engine) as session:
        summary = scan_and_index(
            client=client,
            session=session,
            dest_dir=tmp_path,
            max_workers=2,
            progress_callback=lambda current, total, label: progress_events.append(
                (current, total, label)
            ),
        )

    assert summary.total_items == 2
    assert summary.pdf_found == 2
    assert summary.new_indexed == 1
    assert summary.duplicates_skipped == 1
    assert client.clone.call_count == 2
    assert len(progress_events) == 2
    assert {event[2] for event in progress_events} == {"Paper 1", "Paper 2"}


# ── get_pdf_attachments filtering ─────────────────────────────────────────────

def test_get_pdf_attachments_filters_by_content_type():
    mock_children = [
        {"data": {"key": "K1", "itemType": "attachment", "contentType": "application/pdf", "title": "paper.pdf", "filename": "paper.pdf"}},
        {"data": {"key": "K2", "itemType": "attachment", "contentType": "text/html", "title": "snapshot"}},
        {"data": {"key": "K3", "itemType": "note"}},
    ]
    with patch("app.ingestion.zotero_client.zotero.Zotero") as MockZot:
        instance = MockZot.return_value
        instance.children.return_value = mock_children
        client = ZoteroClient.__new__(ZoteroClient)
        client._zot = instance
        result = client.get_pdf_attachments("PARENT1")

    assert len(result) == 1
    assert result[0].item_key == "K1"
    assert result[0].content_type == "application/pdf"


def test_download_pdf_moves_file_from_isolated_temp_dir(tmp_path):
    with patch("app.ingestion.zotero_client.zotero.Zotero") as MockZot:
        instance = MockZot.return_value

        def fake_dump(attachment_key, path):
            dumped = Path(path) / "downloaded-file.pdf"
            dumped.write_bytes(b"pdf bytes")

        instance.dump.side_effect = fake_dump

        client = ZoteroClient("api", "lib")
        local_path, file_hash = client.download_pdf("ATTACH1", tmp_path)

    assert local_path == tmp_path / "ATTACH1.pdf"
    assert local_path.exists()
    assert file_hash == _sha256(local_path)


def test_get_collections_builds_hierarchy_paths():
    raw_collections = [
        {"data": {"key": "C1", "name": "Root"}},
        {"data": {"key": "C2", "name": "Child", "parentCollection": "C1"}},
        {"data": {"key": "C3", "name": "Leaf", "parentCollection": "C2"}},
    ]
    with patch("app.ingestion.zotero_client.zotero.Zotero") as MockZot:
        instance = MockZot.return_value
        instance.collections.return_value = "collections-endpoint"
        instance.everything.return_value = raw_collections

        client = ZoteroClient.__new__(ZoteroClient)
        client._zot = instance
        collections = client.get_collections()

    by_key = {collection.key: collection for collection in collections}
    assert by_key["C1"].path == "Root"
    assert by_key["C2"].path == "Root / Child"
    assert by_key["C3"].path == "Root / Child / Leaf"


def test_resolve_collection_scope_includes_descendants():
    with patch("app.ingestion.zotero_client.zotero.Zotero") as MockZot:
        instance = MockZot.return_value
        instance.collections.return_value = "collections-endpoint"
        instance.everything.return_value = [
            {"data": {"key": "C1", "name": "Root"}},
            {"data": {"key": "C2", "name": "A", "parentCollection": "C1"}},
            {"data": {"key": "C3", "name": "B", "parentCollection": "C1"}},
            {"data": {"key": "C4", "name": "A1", "parentCollection": "C2"}},
        ]

        client = ZoteroClient.__new__(ZoteroClient)
        client._zot = instance
        resolved = client.resolve_collection_scope("C1")

    assert resolved == ["C1", "C2", "C4", "C3"]


def test_get_all_top_items_scoped_filters_and_dedups_items():
    with patch("app.ingestion.zotero_client.zotero.Zotero") as MockZot:
        instance = MockZot.return_value
        instance.collections.return_value = "collections-endpoint"
        instance.collection_items.side_effect = ["c1-endpoint", "c2-endpoint"]
        instance.everything.side_effect = [
            [
                {"data": {"key": "C1", "name": "Root"}},
                {"data": {"key": "C2", "name": "Child", "parentCollection": "C1"}},
            ],
            [
                {"data": {"key": "I1", "itemType": "journalArticle", "title": "Paper 1"}},
                {"data": {"key": "A1", "itemType": "attachment", "parentItem": "I1"}},
            ],
            [
                {"data": {"key": "I1", "itemType": "journalArticle", "title": "Paper 1"}},
                {"data": {"key": "I2", "itemType": "journalArticle", "title": "Paper 2"}},
            ],
        ]

        client = ZoteroClient.__new__(ZoteroClient)
        client._zot = instance
        items = client.get_all_top_items(collection_key="C1")

    item_keys = [item["data"]["key"] for item in items]
    assert item_keys == ["I1", "I2"]


def test_get_all_top_items_without_scope_uses_top_endpoint():
    with patch("app.ingestion.zotero_client.zotero.Zotero") as MockZot:
        instance = MockZot.return_value
        instance.top.return_value = "top-endpoint"
        instance.everything.return_value = [
            {"data": {"key": "I1", "itemType": "journalArticle"}},
        ]

        client = ZoteroClient.__new__(ZoteroClient)
        client._zot = instance
        items = client.get_all_top_items()

    assert len(items) == 1
    instance.top.assert_called_once()
