"""Generic output checks that must pass for every generated article."""

import re

from conftest import all_headings


def test_infobox_present(any_article):
    assert "{{Infobox Deckenmalerei" in any_article


def test_infobox_has_required_fields(any_article):
    for field in (
        "| titel =",
        "| beschreibung =",
        "| bild =",
        "| lizenz =",
        "| author =",
        "| entity_id =",
    ):
        assert field in any_article, f"Missing infobox field: {field!r}"


def test_headings_have_no_bold_markup(any_article):
    for heading in all_headings(any_article):
        assert "'''" not in heading, f"Bold markup in heading: {heading!r}"


def test_headings_have_no_italic_markup(any_article):
    for heading in all_headings(any_article):
        assert "''" not in heading, f"Italic markup in heading: {heading!r}"


def test_no_unconverted_html_heading_tags(any_article):
    match = re.search(r"<h[1-6][^>]*>", any_article)
    assert match is None, f"Unconverted HTML heading tag found: {match.group()!r}"


def test_no_unconverted_strong_tags(any_article):
    match = re.search(r"<strong>", any_article, re.IGNORECASE)
    assert match is None, "Unconverted <strong> tag found in output"


def test_has_einzelnachweise_section(any_article):
    assert "== Einzelnachweise ==" in any_article


def test_no_empty_headings(any_article):
    empty = re.findall(r"^={1,6}\s*={1,6}$", any_article, re.MULTILINE)
    assert not empty, f"Empty headings found: {empty}"


def test_no_soft_hyphens(any_article):
    assert "­" not in any_article, "Soft hyphen (U+00AD) found in output"
