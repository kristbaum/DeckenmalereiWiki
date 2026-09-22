"""System and user prompts for the two passes."""

from checker.chunking import Chunk
from checker.config import GLOSSARY_PROMPT_LIMIT

# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------

_COMMON_RULES = """
Die Texte stammen aus dem "Corpus der barocken Deckenmalerei in Deutschland"
(CbDD), einem kunsthistorischen Fachkorpus in deutscher Sprache.

Feste Regeln:
- Melde ausschließlich echte Fehler. Im Zweifel meldest du nichts. Eine kurze,
  fehlerfreie Liste ist wertvoller als eine lange mit Fehlalarmen.
- "[ZITAT]" ist ein Platzhalter für eine historische Inschrift oder ein
  wörtliches Zitat. Melde dazu nichts und bemängle den Platzhalter nicht.
- Historische Schreibweisen, lateinische Wendungen und kunsthistorische
  Fachbegriffe sind korrekt, auch wenn sie ungewöhnlich aussehen.
- Orts-, Personen- und Gebäudenamen sind korrekt, sofern sie nicht innerhalb
  desselben Textes widersprüchlich geschrieben werden.
- Erfinde niemals Quellen, Literaturangaben oder Datierungen.
- Antworte ausschließlich mit JSON in genau dieser Form:
  {"funde": [{"abschnitt_id": "...", "zitat": "...", "kategorie": "...",
  "vorschlag": "...", "begruendung": "..."}]}
- "zitat" ist die fehlerhafte Textstelle, WORTWÖRTLICH aus dem Text kopiert,
  höchstens 150 Zeichen lang. Zitiere nur den fehlerhaften Teil, nicht den
  ganzen Satz. Erfinde keine Textstellen: Was nicht wörtlich im Text steht,
  wird verworfen.
- "vorschlag" ist dieselbe Stelle in korrigierter Fassung. "vorschlag" MUSS
  sich von "zitat" unterscheiden. Ist beides gleich, gibt es keinen Fehler -
  dann melde nichts.
- Melde nichts zu URLs, Dateinamen oder Literaturangaben.
- Halte "zitat" so kurz wie möglich. Beispiel: Steht im Text "kann einen
  Krebs erkenne, der", dann lautet der Fund
  {"zitat": "erkenne", "vorschlag": "erkennt", ...} - nicht der ganze Satz.
- "begruendung" ist ein knapper deutscher Satz.
- Gibt es nichts zu melden, antworte mit {"funde": []}.
""".strip()

SYSTEM_PROMPTS = {
    "simple": _COMMON_RULES
    + """

Du bist Korrektor für Rechtschreibung und Typografie. Du prüfst NUR:
- Rechtschreibfehler und Tippfehler
- Zeichensetzung, insbesondere Kommaregeln
- deutsche Typografie: Anführungszeichen („…“), Gedankenstriche, Leerzeichen
- stehengebliebene Auszeichnung oder Platzhaltertext (z. B. "Platzhalter xy")
- uneinheitliche Schreibung desselben Eigennamens innerhalb eines Textes

Erlaubte Werte für "kategorie": Rechtschreibung, Zeichensetzung, Typografie,
Markup, Uneinheitlich.

Du bewertest NICHT: Stil, Wortwahl, Inhalt, Datierungen, Satzbau, Überschriften
oder die Wahl eines Fachbegriffs. Ein langer Satz ist kein Fehler. Eine
ungewöhnliche, aber korrekte Formulierung ist kein Fehler.""",
    "complex": _COMMON_RULES
    + """

Du bist fachlicher Lektor. Rechtschreibung und Zeichensetzung interessieren
dich NICHT - die prüft ein anderer Durchgang. Du prüfst:
- unklare, verstümmelte oder unvollständige Sätze
- inhaltliche Widersprüche innerhalb des Artikels, z. B. eine Datierung, die
  der Baugeschichte widerspricht
- Verweise auf Abbildungen, Grundrisse, Flügel-Buchstaben oder Quellen, die im
  Text weder gezeigt noch erklärt werden
- unerklärte Abkürzungen und uneinheitliche Fachterminologie
- überlange oder schwer lesbare Konstruktionen

Erlaubte Werte für "kategorie": Unklar, Widerspruch, Fehlender Bezug,
Terminologie, Stil.

Melde nur, was einer Redakteurin tatsächlich Arbeit abnimmt.""",
}


def relevant_terms(chunk: Chunk, glossary: list[str]) -> list[str]:
    """The glossary entries that actually occur in this chunk.

    Half the corpus is shorter than 300 tokens, so sending the whole glossary
    means a prompt several times larger than the text being checked. Only terms
    the model can actually see are worth paying for.
    """
    if not glossary:
        return []
    haystack = " ".join(section.text for section in chunk.sections).lower()
    return [term for term in glossary if term.lower() in haystack]


def build_user_prompt(chunk: Chunk, glossary: list[str]) -> str:
    parts = [f"Artikel: {chunk.article.title}", ""]
    glossary = relevant_terms(chunk, glossary)
    if glossary:
        terms = ", ".join(glossary[:GLOSSARY_PROMPT_LIMIT])
        parts += [
            (
                "Die folgenden Fachbegriffe und Eigennamen sind korrekt "
                "geschrieben und dürfen nicht als Fehler gemeldet werden:"
            ),
            terms,
            "",
        ]
    for section in chunk.sections:
        parts += [f"[abschnitt_id: {section.id}] {section.heading}", section.text, ""]
    return "\n".join(parts)
