"""Checks that downloaded images and their metadata sidecars are consistent.

These tests validate the output of the ``download-images`` command:

    uv run python -m deckenmalereiwiki download-images

That command writes, for every image referenced by an article in ``output/``,
the image file plus a ``{entity_id}.json`` metadata sidecar into ``downloads/``.
When ``downloads/`` has not been populated yet the tests skip, mirroring the
behaviour of the article tests when ``output/`` is empty.

Scope: like the other tests, these only cover the images linked in the two
reference articles (Bad Buchau and Egloffstein), not every article in
``output/``.
"""

import json
from pathlib import Path

import pytest

from conftest import (
    BAD_BUCHAU,
    EGLOFFSTEIN,
    DOWNLOADS_DIR,
    image_filenames,
    image_stems,
)

# These tests are scoped to the images referenced by the two reference articles
# (Bad Buchau and Egloffstein) rather than every article in ``output/``.
ARTICLES = [BAD_BUCHAU, EGLOFFSTEIN]

REQUIRED_KEYS = {
    "entity_id",
    "resource_id",
    "provider",
    "license",
    "is_cc",
    "description",
    "rights_holders",
    "originators",
    "source_url",
    "downloaded",
    "image_file",
}


def _referenced_stems() -> set[str]:
    """Entity-id stems of every image linked in the reference articles."""
    stems: set[str] = set()
    for article in ARTICLES:
        if article.exists():
            stems |= image_stems(article.read_text(encoding="utf-8"))
    return stems


def _sidecars() -> list[Path]:
    """Metadata sidecars for images linked in the reference articles."""
    if not DOWNLOADS_DIR.is_dir():
        return []
    referenced = _referenced_stems()
    return sorted(p for p in DOWNLOADS_DIR.glob("*.json") if p.stem in referenced)


def _require_downloads():
    if not _sidecars():
        pytest.skip(
            "No image metadata in downloads/ — run "
            "`uv run python -m deckenmalereiwiki download-images` first."
        )


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --- Every image referenced by an article must have a metadata sidecar -------


@pytest.fixture(params=ARTICLES, ids=lambda p: p.stem)
def article_path(request) -> Path:
    if not request.param.exists():
        pytest.skip(f"Output file not found: {request.param}")
    return request.param


def test_referenced_images_have_metadata(article_path: Path):
    _require_downloads()
    stems = image_stems(article_path.read_text(encoding="utf-8"))
    sidecar_ids = {p.stem for p in _sidecars()}
    missing = sorted(s for s in stems if s not in sidecar_ids)
    assert not missing, (
        f"{article_path.name} references images with no metadata sidecar in "
        f"downloads/: {missing}"
    )


# --- Each metadata sidecar must be well-formed and match its image -----------


@pytest.fixture(params=_sidecars(), ids=lambda p: p.stem)
def metadata(request) -> tuple[str, dict]:
    return request.param.stem, _load(request.param)


def test_metadata_has_required_keys(metadata: tuple[str, dict]):
    stem, meta = metadata
    missing = REQUIRED_KEYS - meta.keys()
    assert not missing, f"{stem}.json missing keys: {sorted(missing)}"


def test_metadata_entity_id_matches_filename(metadata: tuple[str, dict]):
    stem, meta = metadata
    assert meta["entity_id"] == stem
    assert isinstance(meta["rights_holders"], list)
    assert isinstance(meta["originators"], list)
    assert meta["provider"], f"{stem}.json has an empty provider"


def test_metadata_cc_flag_matches_license(metadata: tuple[str, dict]):
    stem, meta = metadata
    expected = meta["license"].strip().upper().startswith("CC")
    assert meta["is_cc"] is expected, (
        f"{stem}.json is_cc={meta['is_cc']} but license={meta['license']!r}"
    )


def test_non_cc_images_are_downloaded():
    """Downloading must not be gated by license: non-CC images download too."""
    _require_downloads()
    non_cc = [_load(p) for p in _sidecars()]
    non_cc = [m for m in non_cc if not m["is_cc"]]
    if not non_cc:
        pytest.skip("No non-CC images in downloads/ to check")
    assert any(m["downloaded"] for m in non_cc), (
        "No non-CC image was downloaded — license gating may have been "
        "re-introduced into download_image()"
    )


def test_metadata_source_url(metadata: tuple[str, dict]):
    """The original-image link is recorded and points at a real URL when set."""
    stem, meta = metadata
    src = meta["source_url"]
    assert src is None or (
        isinstance(src, str) and src.startswith(("http://", "https://"))
    ), f"{stem}.json has an invalid source_url: {src!r}"
    if meta["downloaded"]:
        assert src, f"{stem} was downloaded but has no source_url"


def test_downloaded_image_file_exists(metadata: tuple[str, dict]):
    stem, meta = metadata
    if not meta["downloaded"]:
        return
    assert meta["image_file"], f"{stem} marked downloaded but image_file is empty"
    image = DOWNLOADS_DIR / meta["image_file"]
    assert image.exists(), f"Missing image file referenced by {stem}.json: {image}"
    assert image.stat().st_size > 0, f"Empty image file: {image}"
    assert Path(meta["image_file"]).stem == stem


def test_downloaded_image_referenced_by_real_filename(metadata: tuple[str, dict]):
    """An article must reference each downloaded image by its real filename.

    The generator resolves the true extension (e.g. BADW serves PNGs), so the
    ``File:`` link must use that exact name — otherwise the wiki link points at
    a file uploaded under a different extension and the image is broken.
    """
    stem, meta = metadata
    if not (meta["downloaded"] and meta["image_file"]):
        return

    referenced: set[str] = set()
    for wiki in ARTICLES:
        if wiki.exists():
            referenced |= image_filenames(wiki.read_text(encoding="utf-8"))

    same_stem = sorted(r for r in referenced if Path(r).stem == stem)
    assert meta["image_file"] in referenced, (
        f"{meta['image_file']} was downloaded but no article references it by "
        f"that exact name; references with the same id: {same_stem}"
    )
