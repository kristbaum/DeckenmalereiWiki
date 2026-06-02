"""
Regression tests for the generated "Bad Buchau, Fürstabtei und Residenz" article.

Run with:  uv run pytest tests/
"""

import re
from pathlib import Path

import pytest

OUTPUT_FILE = (
    Path(__file__).parent.parent / "output" / "Bad_Buchau,_Fürstabtei_und_Residenz.wiki"
)


@pytest.fixture(scope="module")
def content() -> str:
    if not OUTPUT_FILE.exists():
        pytest.skip(f"Output file not found: {OUTPUT_FILE}")
    return OUTPUT_FILE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Infobox
# ---------------------------------------------------------------------------


def test_infobox_present_with_all_fields(content):
    expected = (
        "{{Infobox Deckenmalerei\n"
        "| titel = Bad Buchau, Fürstabtei und Residenz\n"
        "| beschreibung = In der Stiftskirche haben sich Deckenfresken von Andreas Brugger"
        " und Johann Georg Mesmer von 1775/76 erhalten."
        " Sie kreisen u.a. um das Thema des Jüngsten Gerichts, die Himmelfahrt Mariens"
        " sowie die katholische Tugendlehre."
        " Im ehemaligen Tafelzimmer schuf Joseph Anton Reiser 1790 Ideallandschaften.\n"
        "| bild = d2c88b64-a55e-4048-bb06-afe91f3f34c8.jpg\n"
        "| lizenz = CC BY-ND 4.0\n"
        "| author = Laß, Heiko\n"
        "| entity_id = d2c88b64-a55e-4048-bb06-afe91f3f34c8\n"
        "}}"
    )
    assert expected in content


# ---------------------------------------------------------------------------
# Headings
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(={1,6})(.+?)\1$", re.MULTILINE)


def _all_headings(content: str) -> list[str]:
    return [m.group(0) for m in _HEADING_RE.finditer(content)]


def test_headings_have_no_bold_markup(content):
    """No heading line should contain MediaWiki bold markup (''')."""
    for heading in _all_headings(content):
        assert "'''" not in heading, f"Bold markup in heading: {heading!r}"


def test_headings_have_no_italic_markup(content):
    """No heading line should contain MediaWiki italic markup ('')."""
    for heading in _all_headings(content):
        assert "''" not in heading, f"Italic markup in heading: {heading!r}"


def test_expected_top_level_sections_present(content):
    """Key sections must be present with exact titles."""
    sections = [
        "== Das Stift Bad Buchau ==",
        "=== Die Stiftskirche St. Cornelius und Cyprian ===",
        "==== Die Decke des Hauptschiffs ====",
        "===== Das Hauptbild =====",
        "====== Die Krönung Mariens ======",
        "===== Das Mannawunder =====",
        "==== Die Decke im Chor ====",
        "===== Gaudium =====",
        "== Die Abteigebäude ==",
        "=== Der so genannte Goldene Saal ===",
        "==== Die Wandmalereireste im Grünen Zimmer ====",
    ]
    for section in sections:
        assert section in content, f"Missing top-level section: {section!r}"


def test_expected_lower_level_sections_present(content):
    """Key olwer-level sections must be present with exact titles."""
    sections = [
        "=== Kurzbeschreibung und Lage ===",
        "=== Bau-, Ausstattungs- und Nutzungsgeschichte ===",
        "=== Auftraggeber ===",
        "===== Das Hauptbild =====",
        "====== Vorlagen und Vergleiche ======",
        "===== Gestalterische Mittel - Komposition und Ansichtigkeit =====",
    ]
    for section in sections:
        assert section in content, f"Missing lower-level section: {section!r}"


# ---------------------------------------------------------------------------
# HTML hygiene
# ---------------------------------------------------------------------------


def test_no_unconverted_html_heading_tags(content):
    """<h1>–<h6> HTML tags must not appear raw in the output."""
    match = re.search(r"<h[1-6][^>]*>", content)
    assert match is None, f"Unconverted HTML heading tag found: {match.group()!r}"


def test_no_unconverted_strong_tags(content):
    """<strong> HTML tags must not appear raw in the output."""
    match = re.search(r"<strong>", content, re.IGNORECASE)
    assert match is None, "Unconverted <strong> tag found in output"
