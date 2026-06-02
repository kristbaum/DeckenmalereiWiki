import re
from pathlib import Path

import pytest

OUTPUT_DIR = Path(__file__).parent.parent / "output"

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
