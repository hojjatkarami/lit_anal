"""Unit tests for HTML evidence search/highlight helpers."""

from app.ui.html_search import highlight_first_match_in_html


def test_highlight_first_match_in_html_case_insensitive_first_only():
    html = "<html><body><p>Alpha beta alpha.</p></body></html>"

    highlighted, found, strategy = highlight_first_match_in_html(html, "ALPHA")

    assert found is True
    assert strategy == "exact"
    assert highlighted.count("id=\"evidence-find-match\"") == 1
    assert "<mark id=\"evidence-find-match\"" in highlighted


def test_highlight_first_match_in_html_no_match_returns_original():
    html = "<html><body><p>No relevant quote here.</p></body></html>"

    highlighted, found, strategy = highlight_first_match_in_html(html, "missing phrase")

    assert found is False
    assert strategy == "none"
    assert highlighted == html


def test_highlight_first_match_in_html_empty_query_returns_original():
    html = "<html><body><p>Any text.</p></body></html>"

    highlighted, found, strategy = highlight_first_match_in_html(html, "   ")

    assert found is False
    assert strategy == "none"
    assert highlighted == html


def test_highlight_first_match_in_html_uses_fallback_1_for_whitespace_variation():
    html = "<html><body><p>Alpha    beta gamma</p></body></html>"

    highlighted, found, strategy = highlight_first_match_in_html(html, "Alpha beta")

    assert found is True
    assert strategy == "fallback_1"
    assert "<mark id=\"evidence-find-match\"" in highlighted


def test_highlight_first_match_in_html_uses_fallback_2_for_tag_gap():
    html = "<html><body><p>Alpha <em>beta</em> gamma</p></body></html>"

    highlighted, found, strategy = highlight_first_match_in_html(html, "Alpha beta")

    assert found is True
    assert strategy == "fallback_2"
    assert "<mark id=\"evidence-find-match\"" in highlighted
