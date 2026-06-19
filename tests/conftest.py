import re
from pathlib import Path

import pytest

OUTPUT_DIR = Path(__file__).parent.parent / "output"
DOWNLOADS_DIR = Path(__file__).parent.parent / "downloads"

BAD_BUCHAU = OUTPUT_DIR / "Bad_Buchau,_Fürstabtei_und_Residenz.wiki"
EGLOFFSTEIN = OUTPUT_DIR / "Egloffstein,_Schlosskirche_St_Bartholomäus.wiki"


def _read(path: Path) -> str:
    if not path.exists():
        pytest.skip(f"Output file not found: {path}")
    return path.read_text(encoding="utf-8")


@pytest.fixture(params=[BAD_BUCHAU, EGLOFFSTEIN], ids=lambda p: p.stem)
def any_article(request) -> str:
    return _read(request.param)


@pytest.fixture(scope="module")
def bad_buchau() -> str:
    return _read(BAD_BUCHAU)


@pytest.fixture(scope="module")
def egloffstein() -> str:
    return _read(EGLOFFSTEIN)


HEADING_RE = re.compile(r"^(={1,6})(.+?)\1$", re.MULTILINE)


def all_headings(content: str) -> list[str]:
    return [m.group(0) for m in HEADING_RE.finditer(content)]


# Matches every ``File:<name>`` reference, both the ``[[File:...]]`` body links
# and the bare ``File:...`` entries inside ``<gallery>`` blocks.
FILE_REF_RE = re.compile(r"File:([^|\]\n]+)")


def image_filenames(content: str) -> set[str]:
    """Return the set of full image filenames referenced via ``File:`` links."""
    return {m.group(1).strip() for m in FILE_REF_RE.finditer(content)}


def image_stems(content: str) -> set[str]:
    """Return the set of image entity-id stems referenced via ``File:`` links.

    Strips the extension so references can be matched against ``{entity_id}.json``
    metadata sidecars regardless of extension.
    """
    return {Path(name).stem for name in image_filenames(content)}
