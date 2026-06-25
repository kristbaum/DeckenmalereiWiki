"""Unit tests for citation parsing and reference replacement."""

from deckenmalereiwiki.citations import parse_citations, replace_citation_refs


def test_bare_bracket_definitions():
    text = (
        "<p>Body text.[1]</p>"
        "<p>[1] Vollmer, Restaurierungsgeschichte, 1997, S. 108.</p>"
        "<p>[2] Steichele, Augsburg, 1864, S. 654f.</p>"
    )
    cleaned, citations = parse_citations(text, "part")
    assert citations == {
        "part_1": "Vollmer, Restaurierungsgeschichte, 1997, S. 108.",
        "part_2": "Steichele, Augsburg, 1864, S. 654f.",
    }
    assert cleaned == "<p>Body text.[1]</p>"


def test_anchored_footnote_definitions():
    """Markers wrapped in #_ftnref / #_ftn anchors are captured too."""
    base = "http://www.deckenmalerei.eu/edit/abc"
    text = (
        f'<p>Body text.<a href="{base}#_ftn1">[1]</a></p>'
        f'<p><a href="{base}#_ftnref1">[1]</a>Gross 2018b.</p>'
        f'<p><a href="{base}#_ftnref2">[2]</a>Dazu ausführlich: Hinterkeuser 2018.</p>'
    )
    cleaned, citations = parse_citations(text, "part")
    assert citations == {
        "part_1": "Gross 2018b.",
        "part_2": "Dazu ausführlich: Hinterkeuser 2018.",
    }
    # The inline anchor in the body is normalized to a bare "[1]" marker so the
    # replacement pass can turn it into a <ref> tag, and no anchor markup leaks.
    assert cleaned == "<p>Body text.[1]</p>"
    assert "#_ftn" not in cleaned


def test_anchored_refs_become_ref_tags():
    base = "http://www.deckenmalerei.eu/edit/abc"
    text = (
        f'<p>Body text.<a href="{base}#_ftn1">[1]</a></p>'
        f'<p><a href="{base}#_ftnref1">[1]</a>Gross 2018b.</p>'
    )
    cleaned, citations = parse_citations(text, "part")

    used_refs = {}
    result = replace_citation_refs(cleaned, "part", citations, used_refs)
    assert result == '<p>Body text.<ref name="part_1">Gross 2018b.</ref></p>'


def test_text_without_citations_is_untouched():
    text = "<p>Just some prose with no references.</p>"
    cleaned, citations = parse_citations(text, "part")
    assert citations == {}
    assert cleaned == text
