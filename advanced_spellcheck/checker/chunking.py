"""Packing an article's sections into requests of a bounded size."""

from dataclasses import dataclass

from checker.corpus import Article, Section, estimate_tokens

# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------


@dataclass
class Chunk:
    article: Article
    sections: list[Section]

    @property
    def tokens(self) -> int:
        return sum(estimate_tokens(s.text) for s in self.sections)


def split_long_section(section: Section, budget: int) -> list[Section]:
    """Split an oversized section on paragraph boundaries."""
    paragraphs = [p for p in section.text.split("\n\n") if p.strip()]
    parts: list[Section] = []
    buffer: list[str] = []
    for paragraph in paragraphs:
        candidate = buffer + [paragraph]
        if buffer and estimate_tokens("\n\n".join(candidate)) > budget:
            parts.append(Section(section.id, section.heading, "\n\n".join(buffer)))
            buffer = [paragraph]
        else:
            buffer = candidate
    if buffer:
        parts.append(Section(section.id, section.heading, "\n\n".join(buffer)))
    return parts


def chunk_article(article: Article, budget: int) -> list[Chunk]:
    """Pack an article's sections into requests of at most *budget* text tokens.

    Sections from different articles are never mixed: attributing a finding to
    the wrong building is worse than paying for an extra request.
    """
    chunks: list[Chunk] = []
    buffer: list[Section] = []
    used = 0
    for section in article.sections:
        pieces = (
            split_long_section(section, budget)
            if estimate_tokens(section.text) > budget
            else [section]
        )
        for piece in pieces:
            size = estimate_tokens(piece.text)
            if buffer and used + size > budget:
                chunks.append(Chunk(article, buffer))
                buffer, used = [], 0
            buffer.append(piece)
            used += size
    if buffer:
        chunks.append(Chunk(article, buffer))
    return chunks
