"""
Citation parsing and reference replacement for MediaWiki output.
"""

import re
from typing import Dict, Optional


def parse_citations(text: str, part_id: str) -> tuple[str, Dict[str, str]]:
    """Parse citations from text and return cleaned text with citation map.

    Citations are marked as [x] in text with definitions at the end like:
    <p>[1] Citation text</p>
    <p>[2] Another citation</p>

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

    citations: Dict[str, str] = {}
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
    all_citations: Dict[str, str],
    used_refs: Dict[str, bool],
    ref_name_mapping: Optional[Dict[str, str]] = None,
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
