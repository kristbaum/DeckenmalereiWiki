"""Footnote handling: wiki-style merging vs. scholarly (JATS) unique footnotes.

The unit tests cover :func:`build_ref_name_mapping`; the corpus tests scan every
generated ``output_jats/*.xml`` and ``output/*.wiki`` file for structural
footnote problems (dangling/orphaned references, numbering gaps, leftover
``[n]`` markers, merged "Ebd." notes).
"""

import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import pytest

from deckenmalereiwiki.citations import (
    build_ref_name_mapping,
    is_relative_citation,
    parse_citations,
    rewrite_internal_note_refs,
)

ROOT = Path(__file__).parent.parent
JATS_DIR = ROOT / "output_jats"
WIKI_DIR = ROOT / "output"

CITATIONS = {
    "a_1": "Dethlefs, Bildnisgalerie, 2007.",
    "a_2": "Ebd.",
    "b_1": "Dethlefs, Bildnisgalerie, 2007.",
    "b_2": "Ebd.",
    "b_3": "Wie Anm. 1.",
    "c_1": "Wie Anm. 1.",
}


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_wiki_mode_merges_identical_absolute_citations():
    mapping, canonical = build_ref_name_mapping(CITATIONS, merge_duplicates=True)
    assert mapping["b_1"] == "a_1"
    assert "b_1" not in canonical


@pytest.mark.parametrize("ref", ["b_2", "b_3", "c_1"])
def test_wiki_mode_never_merges_relative_citations(ref):
    mapping, canonical = build_ref_name_mapping(CITATIONS, merge_duplicates=True)
    assert mapping[ref] == ref
    assert canonical[ref] == CITATIONS[ref]


def test_jats_mode_keeps_every_footnote():
    mapping, canonical = build_ref_name_mapping(CITATIONS, merge_duplicates=False)
    assert all(k == v for k, v in mapping.items())
    assert canonical == CITATIONS


@pytest.mark.parametrize(
    "text",
    [
        "Ebd.",
        "Ebd., S. 12.",
        "Ebenda, S. 4",
        "ebd.",
        "Ibid., p. 3",
        "Ders., Augsburg, 1864.",
        "Dies., Fresken, 1990.",
        "a. a. O., S. 5",
        "a.a.O.",
        "Wie Anm. 14.",
        "Vgl. Fußnote 3.",
    ],
)
def test_relative_citations_detected(text):
    assert is_relative_citation(text)


@pytest.mark.parametrize(
    "text",
    [
        "Dethlefs, Bildnisgalerie, 2007.",
        "Ebrach, Klosterarchiv, Nr. 3.",  # starts with "Eb…" but is not "Ebd"
        "Diessen, Stiftskirche, 1739.",  # starts with "Dies…" but is not "Dies."
        "Dersch, Hessen, 1915.",
        "Anmerkungen zur Restaurierung, 1997.",
    ],
)
def test_absolute_citations_not_flagged(text):
    assert not is_relative_citation(text)


def test_formatted_markers_are_parsed():
    text = (
        "<p>Body <u>[1]</u> and <sup>[2] </sup>more.</p>"
        "<p><u>[1]</u> Stadtarchiv Nürnberg, E 4/141 Nr. 3.</p>"
        "<p><u>[2]</u> Schwemmer, Bürgerhaus, 1972, S. 121.</p>"
    )
    cleaned, citations = parse_citations(text, "p")
    assert citations == {
        "p_1": "Stadtarchiv Nürnberg, E 4/141 Nr. 3.",
        "p_2": "Schwemmer, Bürgerhaus, 1972, S. 121.",
    }
    assert cleaned == "<p>Body [1] and [2] more.</p>"


def test_trailing_empty_heading_does_not_block_definitions():
    text = "<p>Body.[1]</p><p>[1] Ebd.</p><h5></h5>"
    _, citations = parse_citations(text, "p")
    assert citations == {"p_1": "Ebd."}


def test_definitions_followed_by_real_heading_are_left_alone():
    """A footnote block mid-text is ambiguous; the parser must not guess."""
    text = "<p>Body.[1]</p><p>[1] Bremer, Dyck, 1959.</p><h3>Beschreibung</h3>"
    cleaned, citations = parse_citations(text, "p")
    assert citations == {}
    assert cleaned == text


def _label(number: int) -> str:
    return f"<{number + 60}>"


@pytest.mark.parametrize(
    ("text", "own", "expected"),
    [
        ("Wie Anm. 1.", 3, "Wie Anm. <61>."),
        (
            "Beschreibung von 1614 (wie Anm. 4).",
            6,
            "Beschreibung von 1614 (wie Anm. <64>).",
        ),
        ("Vgl. Anmerkung 2.", 5, "Vgl. Anmerkung <62>."),
        # Self-reference / forward reference: editorial leftover, keep.
        (
            "Grundriss bei Albrecht (wie Anm. 3).",
            3,
            "Grundriss bei Albrecht (wie Anm. 3).",
        ),
        (
            "Dehio, Sachsen I (wie Anm. 2), S. 599f.",
            1,
            "Dehio, Sachsen I (wie Anm. 2), S. 599f.",
        ),
        # Notes in a cited book, not internal references.
        (
            "Isphording, Göz, 1997, S. 58, Anmerkung 314.",
            9,
            "Isphording, Göz, 1997, S. 58, Anmerkung 314.",
        ),
        (
            "Vgl. Fittschen, Caracalla, 2021, S. 362, dort auch Anm. 27.",
            30,
            "Vgl. Fittschen, Caracalla, 2021, S. 362, dort auch Anm. 27.",
        ),
        ("Schickhardt (wie Anm. ##).", 5, "Schickhardt (wie Anm. ##)."),
    ],
)
def test_rewrite_internal_note_refs(text, own, expected):
    assert rewrite_internal_note_refs(text, own, _label) == expected


def test_rewrite_internal_note_refs_keeps_unresolvable_target():
    assert rewrite_internal_note_refs("Wie Anm. 1.", 2, lambda n: None) == "Wie Anm. 1."


# ---------------------------------------------------------------------------
# Corpus checks on generated JATS
# ---------------------------------------------------------------------------


def _jats_files() -> list[Path]:
    files = sorted(JATS_DIR.glob("*.xml"))
    if not files:
        pytest.skip(f"No JATS output in {JATS_DIR}")
    return files


def _fn_problems(path: Path) -> list[str]:
    root = ET.parse(path).getroot()
    body = root.find("body")
    fns = root.findall("back/fn-group/fn")
    fn_ids = [fn.get("id") or "" for fn in fns]
    labels = [fn.findtext("label") for fn in fns]
    xref_rids = [
        x.get("rid") or ""
        for x in (body.iter("xref") if body is not None else [])
        if x.get("ref-type") == "fn"
    ]
    problems = []
    if len(set(fn_ids)) != len(fn_ids):
        problems.append("duplicate fn ids")
    if labels != [str(i) for i in range(1, len(fns) + 1)]:
        problems.append(f"fn labels not 1..{len(fns)}")
    if missing := set(xref_rids) - set(fn_ids):
        problems.append(f"xref to missing fn: {sorted(missing)[:3]}")
    if orphans := set(fn_ids) - set(xref_rids):
        problems.append(f"fn never referenced: {sorted(orphans)[:3]}")
    # Footnotes are numbered by first appearance in the body text.
    first_seen = list(dict.fromkeys(xref_rids))
    if first_seen != fn_ids:
        problems.append("fn order differs from first appearance in body")
    # xref text must equal the label of the target footnote.
    label_of = dict(zip(fn_ids, labels))
    for x in body.iter("xref") if body is not None else []:
        if x.get("ref-type") == "fn" and x.text != label_of.get(x.get("rid")):
            problems.append(f"xref text {x.text!r} != label of {x.get('rid')}")
            break
    return problems


def test_jats_footnote_structure():
    failures = {}
    for path in _jats_files():
        if problems := _fn_problems(path):
            failures[path.name] = problems
    assert not failures, f"{len(failures)} files: {dict(list(failures.items())[:10])}"


def test_jats_unconverted_markers_stay_rare():
    """Few ``[n]`` footnote markers may survive in body paragraphs.

    Bracketed years such as "[1882]" are legitimate text and ignored. The
    remaining ~110 markers are source-data errors the parser deliberately
    leaves alone: footnote blocks placed mid-text (followed by another
    heading, e.g. "Jüchen, Schloss Dyck") and markers whose definition is
    missing from the source (e.g. "[19]" in "Breese im Bruche, Gutskapelle").
    A jump means the parser stopped recognising a definition format.
    """
    marker = re.compile(r"\[\s*(\d{1,3})\s*\]")
    leftovers = []
    for path in _jats_files():
        body = ET.parse(path).getroot().find("body")
        if body is None:
            continue
        for p in body.iter("p"):
            leftovers.extend(
                f"{path.name}: [{m.group(1)}]"
                for m in marker.finditer("".join(p.itertext()))
            )
    assert len(leftovers) < 150, f"{len(leftovers)} leftovers, e.g. {leftovers[:10]}"


def test_jats_note_to_note_xrefs_point_backwards():
    """ "wie Anm. N" links inside footnotes must hit an earlier, existing note."""
    failures = []
    linked = 0
    for path in _jats_files():
        root = ET.parse(path).getroot()
        labels = {
            fn.get("id"): int(fn.findtext("label") or 0)
            for fn in root.findall("back/fn-group/fn")
        }
        for fn in root.findall("back/fn-group/fn"):
            for x in fn.iter("xref"):
                linked += 1
                target = labels.get(x.get("rid"))
                if target is None or target >= labels[fn.get("id")]:
                    failures.append(f"{path.name}: {fn.get('id')} -> {x.get('rid')}")
                elif x.text != str(target):
                    failures.append(f"{path.name}: xref text {x.text!r} != {target}")
    assert not failures, failures[:10]
    assert linked >= 8, "internal 'wie Anm. N' references are no longer linked"


def test_jats_repeated_fn_references_are_rare():
    """Only genuine in-part repeats may point to one fn more than once.

    The source data has ~27 such cases; cross-section merging used to create
    thousands. A jump here means merging crept back in.
    """
    repeats = 0
    for path in _jats_files():
        body = ET.parse(path).getroot().find("body")
        if body is None:
            continue
        counts = Counter(
            x.get("rid") for x in body.iter("xref") if x.get("ref-type") == "fn"
        )
        repeats += sum(n - 1 for n in counts.values() if n > 1)
    assert repeats < 100, repeats


# ---------------------------------------------------------------------------
# Corpus checks on generated wikitext
# ---------------------------------------------------------------------------

REF_DEF = re.compile(r'<ref name="([^"]+)">(.*?)</ref>', re.DOTALL)
REF_REUSE = re.compile(r'<ref name="([^"]+)" />')


def _wiki_files() -> list[Path]:
    files = sorted(WIKI_DIR.glob("*.wiki"))
    if not files:
        pytest.skip(f"No wiki output in {WIKI_DIR}")
    return files


def test_wiki_relative_notes_not_reused_across_sections():
    """A reused "Ebd."-style ref must belong to the same TEXT_PART.

    Ref names are ``{part_id}_{n}``; a reuse is only legitimate when the author
    cited the same note twice inside one part, which never crosses parts.
    """
    failures = []
    for path in _wiki_files():
        content = path.read_text(encoding="utf-8")
        relative = {n for n, t in REF_DEF.findall(content) if is_relative_citation(t)}
        reused = Counter(REF_REUSE.findall(content))
        failures.extend(
            f"{path.name}: {name} reused {reused[name]}x"
            for name in relative
            if reused[name] > 2  # >2: beyond the rare in-part double citation
        )
    assert not failures, failures[:10]


def test_wiki_every_reuse_has_definition():
    failures = []
    for path in _wiki_files():
        content = path.read_text(encoding="utf-8")
        defined = {n for n, _ in REF_DEF.findall(content)}
        if missing := set(REF_REUSE.findall(content)) - defined:
            failures.append(f"{path.name}: {sorted(missing)[:3]}")
    assert not failures, failures[:10]
