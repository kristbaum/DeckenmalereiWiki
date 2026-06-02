"""Regression tests specific to the Bad Buchau article."""


def test_infobox(bad_buchau):
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
    assert expected in bad_buchau


def test_sections(bad_buchau):
    sections = [
        "== Das Stift Bad Buchau ==",
        "=== Kurzbeschreibung und Lage ===",
        "=== Bau-, Ausstattungs- und Nutzungsgeschichte ===",
        "=== Auftraggeber ===",
        "=== Die Stiftskirche St. Cornelius und Cyprian ===",
        "==== Die Decke des Hauptschiffs ====",
        "===== Das Hauptbild =====",
        "====== Die Krönung Mariens ======",
        "====== Vorlagen und Vergleiche ======",
        "===== Gestalterische Mittel - Komposition und Ansichtigkeit =====",
        "===== Das Mannawunder =====",
        "==== Die Decke im Chor ====",
        "===== Gaudium =====",
        "== Die Abteigebäude ==",
        "=== Der so genannte Goldene Saal ===",
        "==== Die Wandmalereireste im Grünen Zimmer ====",
    ]
    for section in sections:
        assert section in bad_buchau, f"Missing section: {section!r}"
