"""The domain vocabulary that must not be reported as misspelled."""

import re
from collections import Counter
from pathlib import Path

from checker.config import GLOSSARY_FILE, GLOSSARY_PROMPT_LIMIT
from checker.corpus import Article

# --------------------------------------------------------------------------
# Glossary
# --------------------------------------------------------------------------

_WORD_RE = re.compile(r"\b[A-ZÄÖÜ][a-zäöüß]{5,}\b")

# Plain German wordlists shipped by most Linux distributions. Used to drop
# ordinary vocabulary from the glossary, so only corpus-specific terms remain.
DICTIONARY_CANDIDATES = [
    Path("/usr/share/dict/ngerman"),
    Path("/usr/share/dict/ogerman"),
    Path("/usr/share/dict/german"),
]


def load_dictionary(path: Path | None) -> set[str] | None:
    """Load a German wordlist, or return None if none is available."""
    candidates = [path] if path else DICTIONARY_CANDIDATES
    for candidate in candidates:
        if candidate and candidate.exists():
            words = {
                line.strip()
                for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines()
                if line.strip()
            }
            print(f"  dictionary: {candidate} ({len(words):,} words)")
            return words
    return None


def load_glossary() -> list[str]:
    if not GLOSSARY_FILE.exists():
        return []
    return [
        line.strip()
        for line in GLOSSARY_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def build_glossary(
    articles: list[Article], min_count: int, limit: int, dictionary_path: Path | None
) -> None:
    """Derive the domain vocabulary from the corpus, for hand-pruning.

    A capitalised word that occurs often across the corpus but is unknown to a
    general German wordlist is domain vocabulary (Supraporte, Scheinarchitektur,
    Plafond), a mythological name (Bacchus, Aeneas) or a building part
    (Südflügel) - exactly what a proofreading model reports as a typo. Words the
    dictionary knows are dropped: they are never falsely flagged and would only
    consume prompt tokens.

    Without a system dictionary the list falls back to plain frequency, which is
    noisier; prune it by hand or pass --dictionary.
    """
    counter: Counter[str] = Counter()
    for article in articles:
        for section in article.sections:
            counter.update(_WORD_RE.findall(section.text))

    dictionary = load_dictionary(dictionary_path)
    terms = []
    for term, count in counter.most_common():
        if count < min_count:
            break
        if dictionary and (term in dictionary or term.lower() in dictionary):
            continue
        terms.append(term)
        if len(terms) >= limit:
            break

    source = "unbekannt im Wörterbuch" if dictionary else "nur nach Häufigkeit"
    header = [
        "# Fachbegriffe und Eigennamen, die nicht als Fehler gemeldet werden sollen.",
        f"# Automatisch erzeugt aus dem Korpus (>= {min_count} Vorkommen, {source}).",
        f"# Von Hand zu kürzen; nur die ersten {GLOSSARY_PROMPT_LIMIT} Zeilen gehen in den Prompt.",
        "",
    ]
    GLOSSARY_FILE.write_text("\n".join(header + terms) + "\n", encoding="utf-8")
    print(f"Wrote {len(terms)} term(s) to {GLOSSARY_FILE}")
    if not dictionary:
        print("  no German wordlist found - the list is frequency-only and needs pruning")
