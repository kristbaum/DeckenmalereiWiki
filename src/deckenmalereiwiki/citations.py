"""
Citation parsing and reference replacement for MediaWiki output.
"""

import re

# Some texts wrap the [x] markers in footnote anchors instead of writing the
# bracket directly. Definitions point at "#_ftnref<n>" and inline references at
# "#_ftn<n>", e.g.
#   <a href="http://.../edit/<id>#_ftnref1">[1]</a>Citation text
#   <a href="http://.../edit/<id>#_ftn1">[1]</a>
# Normalising these anchors back to a bare "[n]" lets the same parsing logic
# handle both styles.
_FOOTNOTE_ANCHOR_PATTERN = re.compile(
    r'<a\b[^>]*?href="[^"]*#_ftn(?:ref)?\d+"[^>]*>\s*\[\s*(\d+)\s*\]\s*</a>',
    flags=re.IGNORECASE,
)


# Markers that the editor wrapped in inline formatting, e.g. "<u>[7]</u>" or
# "<sup>[3] </sup>" (the space may sit inside the tag).
_FORMATTED_MARKER_PATTERN = re.compile(
    r"<(u|sup|strong|b|em|i|span)\b[^>]*>\s*\[\s*(\d+)\s*\](\s*)</\1>",
    flags=re.IGNORECASE,
)

# Empty headings (e.g. a stray "<h5></h5>" after the footnote block) carry no
# content but would otherwise stop the trailing definitions from being parsed.
_EMPTY_HEADING_PATTERN = re.compile(r"<h[1-6][^>]*>\s*</h[1-6]>", re.IGNORECASE)


def _normalize_footnote_anchors(text: str) -> str:
    """Replace anchored/formatted footnote markers with bare "[n]" brackets."""
    text = _FOOTNOTE_ANCHOR_PATTERN.sub(r"[\1]", text)
    text = _FORMATTED_MARKER_PATTERN.sub(r"[\2]\3", text)
    return _EMPTY_HEADING_PATTERN.sub("", text)


def parse_citations(text: str, part_id: str) -> tuple[str, dict[str, str]]:
    """Parse citations from text and return cleaned text with citation map.

    Citations are marked as [x] in text with definitions at the end like:
    <p>[1] Citation text</p>
    <p>[2] Another citation</p>

    The [x] markers may also appear wrapped in footnote anchors such as
    ``<a href="...#_ftnref1">[1]</a>Citation text`` (definitions) and
    ``<a href="...#_ftn1">[1]</a>`` (inline references); these are normalized to
    bare brackets before parsing.

    Whitespace inside the brackets (e.g. "[ 1 ]") is tolerated, both for the
    inline markers and the definitions at the end. A definition may also span
    several paragraphs; continuation paragraphs (those that do not start with a
    [x] marker) are appended to the preceding citation:
    <p>[3] First half,</p>
    <p>second half.</p>

    Returns:
        tuple: (cleaned_text, citation_map) where citation_map keys are like 'partid_1'
    """
    if not text:
        return text, {}

    text = _normalize_footnote_anchors(text)

    # A definition is a paragraph that *starts* with a [x] marker. Inline
    # references sit inside body paragraphs, so they never match here.
    marker_pattern = re.compile(r"<p>\s*\[\s*(\d+)\s*\]\s*(.*?)</p>", flags=re.DOTALL)
    paragraph_pattern = re.compile(r"<p>.*?</p>", flags=re.DOTALL)

    first_marker = marker_pattern.search(text)
    if not first_marker:
        return text, {}

    citation_start = first_marker.start()
    tail = text[citation_start:]

    # The trailing citation block must consist solely of <p>…</p> paragraphs.
    # If anything else remains, the [x] is not a real definition (e.g. it sits
    # mid-document) and we leave the text untouched.
    if paragraph_pattern.sub("", tail).strip():
        return text, {}

    citations: dict[str, str] = {}
    current_num = None
    for para in paragraph_pattern.finditer(tail):
        block = para.group(0)
        marker = marker_pattern.match(block)
        if marker:
            current_num = marker.group(1)
            citations[current_num] = marker.group(2).strip()
        elif current_num is not None:
            # Continuation paragraph: append to the current citation.
            continuation = re.sub(r"</?p>", "", block).strip()
            if continuation:
                citations[current_num] = (
                    f"{citations[current_num]} {continuation}".strip()
                )

    cleaned_text = text[:citation_start].rstrip()
    cleaned_text = re.sub(r"(<p>\s*</p>\s*)+$", "", cleaned_text)

    citation_map = {
        f"{part_id}_{num}": citation_text for num, citation_text in citations.items()
    }

    return cleaned_text, citation_map


def replace_citation_refs(
    text: str,
    part_id: str,
    all_citations: dict[str, str],
    used_refs: dict[str, bool],
    ref_name_mapping: dict[str, str] | None = None,
) -> str:
    """Replace [x] references with MediaWiki <ref> tags.

    Args:
        text: Text containing [x] references
        part_id: ID of the text part
        all_citations: All citations collected from all parts (deduplicated)
        used_refs: Dict tracking which refs have been used (for reuse)
        ref_name_mapping: Optional mapping from original ref names to canonical names

    Returns:
        Text with [x] replaced by <ref> tags
    """

    def replace_ref(match):
        num = match.group(1)
        original_ref_name = f"{part_id}_{num}"

        if ref_name_mapping:
            ref_name = ref_name_mapping.get(original_ref_name, original_ref_name)
        else:
            ref_name = original_ref_name

        if ref_name not in all_citations:
            return match.group(0)

        citation_text = all_citations[ref_name]

        if ref_name in used_refs:
            return f'<ref name="{ref_name}" />'
        else:
            used_refs[ref_name] = True
            return f'<ref name="{ref_name}">{citation_text}</ref>'

    text = re.sub(r"(?<!^)\[\s*(\d+)\s*\]", replace_ref, text, flags=re.MULTILINE)

    return text


# Footnotes whose meaning depends on their position: "Ebd."/"Ibid." point to the
# preceding note, "Ders."/"Dies." repeat the preceding author, "a. a. O." the
# previously cited work, and "wie Anm. 5" names a note by its (per-TEXT_PART)
# number. Two such notes with identical text in different sections usually
# mean different things, so they must never be merged.
_RELATIVE_CITATION_PATTERN = re.compile(
    r"^\s*(?:Ebd|Ebenda|Ibid|Ibidem|Ders|Dies|a\.\s*a\.\s*O)\b"
    r"|\b(?:Anm|Fn|Fußnote)\.?\s*\d",
    flags=re.IGNORECASE,
)


def is_relative_citation(citation_text: str) -> bool:
    """Return True if *citation_text* only makes sense relative to its position."""
    return bool(_RELATIVE_CITATION_PATTERN.search(citation_text))


def build_ref_name_mapping(
    all_citations: dict[str, str], merge_duplicates: bool
) -> tuple[dict[str, str], dict[str, str]]:
    """Map each footnote to its canonical name.

    With *merge_duplicates* (wiki style), footnotes with identical text share
    one canonical name, so the article cites a single ``<ref name>`` several
    times. Relative notes (see :func:`is_relative_citation`) are never merged.
    Without it (scholarly/JATS style), every source footnote stays unique.

    Returns:
        tuple: (ref_name_mapping, canonical_citations) where ref_name_mapping maps
        every original ref name to its canonical one and canonical_citations maps
        canonical names to their text.
    """
    ref_name_mapping: dict[str, str] = {}
    canonical_citations: dict[str, str] = {}
    text_to_name: dict[str, str] = {}
    for ref_name, citation_text in all_citations.items():
        mergeable = merge_duplicates and not is_relative_citation(citation_text)
        if mergeable and citation_text in text_to_name:
            ref_name_mapping[ref_name] = text_to_name[citation_text]
            continue
        if mergeable:
            text_to_name[citation_text] = ref_name
        ref_name_mapping[ref_name] = ref_name
        canonical_citations[ref_name] = citation_text
    return ref_name_mapping, canonical_citations
