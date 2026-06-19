"""Unit tests for the {{BildMeta}} template builder (no network/files needed)."""

from deckenmalereiwiki.image_handler import ImageHandler


def test_bildmeta_includes_source_and_cc_for_cc_license():
    out = ImageHandler._build_description(
        "Deckenfresko",
        "CC BY-SA 4.0",
        ["Leibniz-Institut"],
        ["Laß, Heiko"],
        source_url="https://previous.bildindex.de/bilder/fmd1a.jpg",
    )
    assert out.startswith("{{BildMeta")
    assert out.rstrip().endswith("}}")
    assert "| beschreibung = Deckenfresko" in out
    assert "| urheber = Laß, Heiko" in out
    assert "| rechteinhaber = Leibniz-Institut" in out
    assert "| lizenz = CC BY-SA 4.0" in out
    assert "| cc = ja" in out
    assert "| quelle = https://previous.bildindex.de/bilder/fmd1a.jpg" in out


def test_bildmeta_marks_non_cc_license():
    out = ImageHandler._build_description(
        "Foto", "Rechte vorbehalten", None, None, source_url=None
    )
    assert "| lizenz = Rechte vorbehalten" in out
    assert "| cc = nein" in out
    # No source URL provided → no quelle line.
    assert "| quelle" not in out


def test_bildmeta_cc_flag_always_present_even_without_license():
    out = ImageHandler._build_description("", "", None, None)
    assert "| cc = nein" in out
    # Empty license must not emit an empty lizenz line.
    assert "| lizenz" not in out
