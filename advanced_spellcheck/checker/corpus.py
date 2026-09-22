"""Turning the source HTML into the plain text that gets proofread."""

import random
import re
from dataclasses import dataclass, field
from html import unescape

from checker.config import CHARS_PER_TOKEN, PORTAL_URL, QUOTE_MASK_MIN_LENGTH
from deckenmalereiwiki.citations import parse_citations
from deckenmalereiwiki.loader import DataLoader

# --------------------------------------------------------------------------
# Text preparation
# --------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCKQUOTE_RE = re.compile(r"<blockquote\b.*?</blockquote>", re.DOTALL | re.IGNORECASE)
_GERMAN_QUOTE_RE = re.compile(r"[„»].{1,2000}?[“«]", re.DOTALL)
_STRAIGHT_QUOTE_RE = re.compile(r"\"[^\"\n]{1,2000}?\"", re.DOTALL)
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
# Boilerplate publication note; everything after it is a bibliographic citation
# with punctuation conventions of its own, not prose the editors wrote.
_PUBLICATION_NOTE_RE = re.compile(r"Bereits publiziert in\s*:?.*", re.DOTALL | re.IGNORECASE)
_BIBLIOGRAPHY_HEADING_RE = re.compile(
    r"^(literatur|quellen|bibliogra|nachweis|abbildungsnachweis)", re.IGNORECASE
)
_FOOTNOTE_MARKER_RE = re.compile(r"\[\s*\d+\s*\]")
_BLOCK_END_RE = re.compile(r"</(p|div|h[1-6]|li|blockquote|tr)>", re.IGNORECASE)


def html_to_plain(html: str) -> str:
    """Return *html* as plain text, with block elements separated by newlines."""
    if not html:
        return ""
    text = html.replace("­", "")  # soft hyphens
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = _BLOCK_END_RE.sub(lambda m: m.group(0) + "\n", text)
    text = _TAG_RE.sub("", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def mask_quotations(text: str) -> tuple[str, int]:
    """Replace long quoted passages with a placeholder.

    Historical inscriptions, Latin passages and 17th/18th-century spellings are
    transcriptions, not text the editors wrote, and every model reports them as
    spelling errors. Masking them means the model cannot see them at all, which
    is more reliable than asking it to ignore them. Short quoted terms (below
    ``QUOTE_MASK_MIN_LENGTH``) stay visible - those are ordinary vocabulary.

    Returns the masked text and the number of passages masked.
    """
    count = 0

    def mask(match: re.Match[str]) -> str:
        nonlocal count
        if len(match.group(0)) < QUOTE_MASK_MIN_LENGTH:
            return match.group(0)
        count += 1
        return "[ZITAT]"

    text = _BLOCKQUOTE_RE.sub(lambda m: "[ZITAT]", text)
    text = _GERMAN_QUOTE_RE.sub(mask, text)
    text = _STRAIGHT_QUOTE_RE.sub(mask, text)
    return text, count


def prepare_section_text(html: str, part_id: str) -> str:
    """Turn a TEXT_PART's HTML into the plain text that gets proofread.

    Drops the footnote definitions at the end of the section (bibliographic
    strings with punctuation conventions of their own, which would otherwise
    dominate the findings), strips the inline ``[n]`` markers, and masks long
    quotations.
    """
    body, _citations = parse_citations(html or "", part_id)
    text = html_to_plain(body)
    text = _FOOTNOTE_MARKER_RE.sub("", text)
    text = _PUBLICATION_NOTE_RE.sub("", text)
    # URLs are not prose. Left in, models proofread them: they report the query
    # string as a typo and the "&amp;" of a link as a spelling error.
    text = _URL_RE.sub("", text)
    text, _masked = mask_quotations(text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r" +([,.;:!?])", r"\1", text).strip()


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


# --------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------


@dataclass
class Section:
    id: str
    heading: str
    text: str


@dataclass
class Article:
    id: str
    title: str
    sections: list[Section] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"{PORTAL_URL}{self.id}"

    def section_url(self, section_id: str) -> str:
        if section_id == self.id:
            return self.url
        return f"{self.url}#{section_id}"


def load_articles(loader: DataLoader) -> list[Article]:
    """Build the proofreading corpus: one Article per TEXT entity."""
    articles = []
    for entity in loader.get_text_entities():
        article = Article(
            id=entity["ID"], title=entity.get("appellation") or f"Ohne Titel {entity['ID']}"
        )
        short_text = prepare_section_text(entity.get("shortText") or "", entity["ID"])
        if short_text:
            article.sections.append(Section(entity["ID"], "Einleitung", short_text))
        for part in loader.get_text_parts(entity["ID"]):
            heading = part.get("appellation") or "Abschnitt"
            if _BIBLIOGRAPHY_HEADING_RE.match(heading.strip()):
                continue
            text = prepare_section_text(part.get("text") or "", part["ID"])
            if text:
                article.sections.append(Section(part["ID"], heading, text))
        if article.sections:
            articles.append(article)
    return articles


def select_articles(
    articles: list[Article], *, test: bool, test_size: int, seed: int, limit: int | None
) -> list[Article]:
    """Pick the articles to process.

    ``--test`` draws a seeded random sample, so a test run is representative of
    the corpus and identical across models - which is the point of a pilot:
    running two candidate models over the same articles and comparing findings
    by hand.
    """
    if test:
        rng = random.Random(seed)
        return rng.sample(articles, min(test_size, len(articles)))
    if limit:
        return articles[:limit]
    return articles
