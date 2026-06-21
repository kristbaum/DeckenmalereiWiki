"""Regression tests specific to the Egloffstein article."""


def test_artikel_modern(egloffstein):
    expected = (
        "{{Artikel-modern\n"
        "| AutorIn1 = Friedrich, Verena\n"
        "| Titel = Egloffstein, Schlosskirche St. Bartholomäus\n"
        "| Ort = Egloffstein\n"
        "| Jahr = 2025\n"
        "| ID = a2e60a1e-606f-4841-9faf-ccc2162a0f6a\n"
        "}}"
    )
    assert expected in egloffstein


def test_sections(egloffstein):
    sections = [
        "== Burg und Schlosskirche Egloffstein ==",
        "=== Die Burg ===",
        #        "=== Überblick über die Bau- und Besitzgeschichte ===",
        "=== Die barocke Schlosskirche St. Bartholomäus ===",
        #        "=== Forschungsstand ===",
        #        "=== Die Baugeschichte der barocken Schlosskirche ===",
        #        "=== Auftraggeber Albrecht Christoph Karl Friedrich von Egloffstein (1706–1750) und seine Nachfolger ===",
        #        "==== Architekt des 19. Jahrhunderts: Sebastian Theodor Justus Eyrich (1838-1907) ====",
        "==== Das Innere der Kirche ====",
        #        "==== Beschreibung des Inneren ====",
        #        "==== Der barocke Kanzelaltar ====",
        #        "==== Beschreibung der Decke mit ihrem Stuckdekor ====",
        "===== Der Plafond mit den sieben Rundbildern =====",
        #        "===== Beschreibung und Ikonographie des Deckengemäldes =====",
        #        "===== Der mutmaßliche Fassmaler Johann Georg Aßner =====",
        #        "===== Gestalterische Mittel =====",
        "====== Die Opferung Isaaks ======",
        "====== Die Heilige Dreifaltigkeit ======",
        "====== Der Gute Hirte ======",
        "====== Evangelist Matthäus ======",
        "====== Evangelist Johannes ======",
        "====== Evangelist Markus ======",
        "====== Evangelist Lukas ======",
        "=== Programm und Synthese ===",
    ]
    for section in sections:
        assert section in egloffstein, f"Missing section: {section!r}"
