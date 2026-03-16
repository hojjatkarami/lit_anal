"""Unit tests for DocTags quote matching and bbox extraction helpers."""

from app.ui.doctags_search import find_first_match_in_doctags


def test_find_first_match_in_doctags_exact_first_match_only():
    doctags = (
        "<doctag>"
        "<text><loc_10><loc_20><loc_110><loc_40>Alpha beta gamma</text>"
        "<text><loc_20><loc_60><loc_120><loc_80>Alpha beta gamma</text>"
        "</doctag>"
    )

    match, strategy = find_first_match_in_doctags(doctags, "alpha beta")

    assert match is not None
    assert strategy == "exact"
    assert match.page == 1
    assert match.left == 10
    assert match.top == 20
    assert match.right == 110
    assert match.bottom == 40


def test_find_first_match_in_doctags_fallback_1_whitespace_normalized():
    doctags = "<doctag><text><loc_1><loc_2><loc_10><loc_20>Alpha    beta   gamma</text></doctag>"

    match, strategy = find_first_match_in_doctags(doctags, "Alpha beta")

    assert match is not None
    assert strategy == "fallback_1"


def test_find_first_match_in_doctags_handles_page_break():
    doctags = (
        "<doctag>"
        "<text><loc_1><loc_2><loc_10><loc_20>Other text</text>"
        "<page_break>"
        "<text><loc_11><loc_22><loc_111><loc_44>Evidence quote here</text>"
        "</doctag>"
    )

    match, strategy = find_first_match_in_doctags(doctags, "Evidence quote")

    assert match is not None
    assert strategy == "exact"
    assert match.page == 2


def test_find_first_match_in_doctags_no_match_returns_none():
    doctags = "<doctag><text><loc_1><loc_2><loc_10><loc_20>Completely different</text></doctag>"

    match, strategy = find_first_match_in_doctags(doctags, "missing phrase")

    assert match is None
    assert strategy == "none"


def test_doctags_match_to_pdf_annotation_builds_expected_shape():
    doctags = "<doctag><text><loc_5><loc_15><loc_35><loc_25>Token payload</text></doctag>"

    match, _ = find_first_match_in_doctags(doctags, "Token")
    assert match is not None

    annotation = match.to_pdf_annotation(annotation_id="a1")

    assert annotation["id"] == "a1"
    assert annotation["page"] == 1
    assert annotation["x"] == 5
    assert annotation["y"] == 15
    assert annotation["width"] == 30
    assert annotation["height"] == 10
    assert annotation["color"] == "#ffeb3b"
    assert annotation["border"] == 2
