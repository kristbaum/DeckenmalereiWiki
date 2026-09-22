"""Checking a model's findings against the text it was actually given."""

from checker.corpus import _URL_RE

# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

_QUOTE_CHARS = str.maketrans({c: '"' for c in "„“”‚‘’«»''"})
_DASH_CHARS = str.maketrans({c: "-" for c in "–—‒−"})


def _collapse(text: str) -> str:
    """Whitespace-normalised, for comparing two strings for real difference."""
    return " ".join(text.split())


def _loose(text: str) -> str:
    """Lowercased and punctuation-normalised, for finding a quote in the text.

    Models re-render quotation marks and dashes when they copy a passage, so a
    strict substring test would reject sound findings.
    """
    return _collapse(text.translate(_QUOTE_CHARS).translate(_DASH_CHARS).lower())


def validate_finding(finding: dict, haystack: str) -> str | None:
    """Return why a finding must be discarded, or None if it is sound.

    The model is given the text, so every claim it makes is checkable against
    that text. Three checks remove the bulk of the noise:

    * a finding whose suggestion equals the quoted passage changes nothing -
      models produce these constantly, with an invented justification;
    * a quoted passage that does not occur in the text that was sent was either
      hallucinated or attributed to the wrong section;
    * a passage containing a URL is not prose.
    """
    zitat = (finding.get("zitat") or "").strip()
    vorschlag = (finding.get("vorschlag") or "").strip()
    if not zitat or not vorschlag:
        return "unvollständig"
    if _collapse(zitat) == _collapse(vorschlag):
        return "keine Änderung"
    if _loose(zitat) not in haystack:
        return "Zitat nicht im Text"
    if _URL_RE.search(zitat):
        return "URL"
    return None


def find_context(zitat: str, source: str, window: int = 60) -> str:
    """The quoted passage with surrounding text, so an editor can find it.

    Short quotes ("uns" for "und") are precise but unlocatable on their own.
    The text is already in hand, so the context costs nothing and saves the
    editor a search.
    """
    haystack = _loose(source)
    needle = _loose(zitat)
    position = haystack.find(needle)
    if position < 0:
        return ""
    start = max(0, position - window)
    end = min(len(haystack), position + len(needle) + window)
    snippet = haystack[start:end].strip()
    return ("… " if start > 0 else "") + snippet + (" …" if end < len(haystack) else "")
