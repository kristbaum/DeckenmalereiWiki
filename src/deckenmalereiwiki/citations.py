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

    Returns:
        tuple: (cleaned_text, citation_map) where citation_map keys are like 'partid_1'
    """
    if not text:
        return text, {}

    citation_pattern = r"<p>\s*\[(\d+)\]\s*(.+?)</p>"

    citations = {}
    citation_matches = list(re.finditer(citation_pattern, text, flags=re.DOTALL))

    if not citation_matches:
        return text, {}

    citation_start = len(text)

    for match in reversed(citation_matches):
        num = match.group(1)
        citation_text = match.group(2).strip()
        citations[num] = citation_text
        citation_start = match.start()

    # Only remove citations if they are at the end of the text
    text_after_first_citation = text[citation_start:]
    non_citation_content = re.sub(
        citation_pattern, "", text_after_first_citation, flags=re.DOTALL
    )
    non_citation_content = re.sub(r"<p>\s*</p>", "", non_citation_content).strip()

    if not non_citation_content or non_citation_content == "":
        cleaned_text = text[:citation_start].rstrip()
        cleaned_text = re.sub(r"(<p>\s*</p>\s*)+$", "", cleaned_text)
    else:
        cleaned_text = text
        citations = {}

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

    text = re.sub(r"(?<!^)\[(\d+)\]", replace_ref, text, flags=re.MULTILINE)

    return text
