"""Regression tests specific to the Bad Buchau article."""


def test_artikel_modern(bad_buchau):
    expected = (
        "{{Artikel-modern\n"
        "| AutorIn1 = Laß, Heiko\n"
        "| Titel = Bad Buchau, Fürstabtei und Residenz\n"
        "| Ort = Bad Buchau\n"
        "| Jahr = 2022\n"
        "| ID = d2c88b64-a55e-4048-bb06-afe91f3f34c8\n"
        "}}"
    )
    assert expected in bad_buchau


def test_sections(bad_buchau):
    sections = [
        "== Das Stift Bad Buchau ==",
        #        "=== Kurzbeschreibung und Lage ===",
        #        "=== Bau-, Ausstattungs- und Nutzungsgeschichte ===",
        #        "=== Auftraggeber ===",
        "=== Die Stiftskirche St. Cornelius und Cyprian ===",
        "==== Die Decke des Hauptschiffs ====",
        "===== Das Hauptbild =====",
        "====== Die Krönung Mariens ======",
        #        "====== Vorlagen und Vergleiche ======",
        #        "===== Gestalterische Mittel - Komposition und Ansichtigkeit =====",
        "===== Das Mannawunder =====",
        "==== Die Decke im Chor ====",
        "===== Gaudium =====",
        "== Die Abteigebäude ==",
        "=== Der so genannte Goldene Saal ===",
        "==== Die Wandmalereireste im Grünen Zimmer ====",
    ]
    for section in sections:
        assert section in bad_buchau, f"Missing section: {section!r}"
