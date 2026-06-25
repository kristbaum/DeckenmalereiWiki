"""
Image download and upload handling for DeckenmalereiWiki.
"""

import json
import time
from pathlib import Path
from typing import Optional

import pywikibot
import requests

from .image_providers import EXTERNAL_PROVIDERS, SourceResolver

# Upload files larger than this in chunks, so big images aren't rejected by
# server POST size limits. 0 would disable chunking.
UPLOAD_CHUNK_SIZE = 4 * 1024 * 1024

__all__ = ["EXTERNAL_PROVIDERS", "UPLOAD_CHUNK_SIZE", "ImageHandler"]


class ImageHandler:
    """Handles downloading images from providers and uploading them to MediaWiki."""

    def __init__(self, site, downloads_dir: Path, offline: bool = False):
        """Initialise the handler.

        Args:
            site:          An authenticated :class:`pywikibot.site.APISite`
                           instance (or ``None`` for offline use, e.g. the
                           generator, which never touches the wiki).
            downloads_dir: Directory where downloaded images are cached.
            offline:       When ``True``, never make network calls to resolve a
                           resource (e.g. the BADW EasyDB API). Used by the
                           article generator's ``parse`` step, which resolves
                           ``File:`` filenames purely from the local downloads
                           and their ``{entity_id}.json`` metadata sidecars.
        """
        self.site = site
        self.downloads_dir = downloads_dir
        self.resolver = SourceResolver(offline=offline)
        # Normalised set of file names that exist on the wiki, fetched once via
        # ``load_existing_filenames``. ``None`` means "not loaded": uploads then
        # fall back to a per-file check.
        self._existing_filenames: Optional[set[str]] = None

    @staticmethod
    def _is_cc_license(license: str) -> bool:
        return license.strip().upper().startswith("CC")

    def is_external(self, url: str) -> bool:
        """Whether *url*'s provider is referenced by link, not uploaded."""
        return self.resolver.is_external(url)

    def source_url(self, url: str, resource_id: str) -> Optional[str]:
        """Return the URL of the original image's source page, or ``None``."""
        return self.resolver.source_url(url, resource_id)

    def _existing_download(self, entity_id: str) -> Optional[Path]:
        """Return the already-downloaded image for *entity_id*, if any.

        Ignores ``.json`` metadata sidecars written alongside images.
        """
        if not self.downloads_dir.is_dir():
            return None
        return next(
            (
                p
                for p in self.downloads_dir.glob(f"{entity_id}.*")
                if p.suffix != ".json"
            ),
            None,
        )

    def read_sidecar(self, entity_id: str) -> Optional[dict]:
        """Return this entity's ``{entity_id}.json`` metadata sidecar, or ``None``.

        The ``download-images`` step writes one sidecar next to every image,
        recording everything needed to upload it (license, description,
        rights/originator actors, source link and the saved filename). Returns
        ``None`` when there is no sidecar or it cannot be parsed.
        """
        path = self.downloads_dir / f"{entity_id}.json"
        if not path.is_file():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def _sidecar_image_file(self, entity_id: str) -> Optional[str]:
        """Return the ``image_file`` recorded in this entity's metadata sidecar.

        The ``download-images`` step writes ``{entity_id}.json`` next to each
        image, recording the exact filename it saved. ``parse`` reads this
        instead of querying any provider API. Returns ``None`` when there is no
        sidecar or it records no downloaded file.
        """
        sidecar = self.read_sidecar(entity_id)
        return sidecar.get("image_file") if sidecar else None

    def image_filename(self, entity_id: str, url: str, resource_id: str) -> str:
        """Return the MediaWiki filename (``{entity_id}{ext}``) for a resource.

        Resolution order, all offline-friendly: an already-downloaded file, then
        the filename recorded in the ``{entity_id}.json`` metadata sidecar, then
        the provider's extension rule. This keeps the ``File:`` reference in step
        with the uploaded file without forcing a network call during ``parse``.
        """
        existing = self._existing_download(entity_id)
        if existing:
            return existing.name
        sidecar_file = self._sidecar_image_file(entity_id)
        if sidecar_file:
            return sidecar_file
        return f"{entity_id}{self.resolver.resolve_extension(url, resource_id)}"

    def download_image(
        self, url: str, entity_id: str, resource_id: str
    ) -> Optional[Path]:
        """Download an image from *url* and save it locally.

        Images are downloaded regardless of license; the license is recorded in
        the ``{{BildMeta}}`` metadata at upload time instead of gating the
        download.

        Args:
            url:         Provider base URL (used to determine download strategy).
            entity_id:   Entity ID used in the output filename.
            resource_id: Resource ID from resources.json.

        Returns:
            Local :class:`~pathlib.Path` of the downloaded file, or ``None``.
        """
        try:
            # Check if already downloaded before making network calls.
            existing = self._existing_download(entity_id)
            if existing:
                print(f"  Image already downloaded: {existing.name}")
                return existing

            image_url, _, ext = self.resolver.resolve_source(url, resource_id)
            if image_url is None:
                print(f"  No downloadable version found for {resource_id}")
                return None

            filename = f"{entity_id}{ext}"
            filepath = self.downloads_dir / filename

            print(f"  Downloading: {image_url}")
            response = requests.get(image_url, timeout=30, stream=True)
            response.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f"  Saved: {filename}")
            time.sleep(0.5)
            return filepath

        except Exception as e:
            print(f"  Failed to download from {url} (resource: {resource_id}): {e}")
            return None

    @staticmethod
    def _build_description(
        description: str,
        license_info: str,
        rights_holders: list | None,
        originators: list | None,
        source_url: str | None = None,
    ) -> str:
        """Build a {{BildMeta}} template call for the file description page.

        Always records a ``cc`` flag (``ja``/``nein``) classifying whether the
        license is a Creative Commons license, and—when known—a ``quelle`` link
        to the original image.
        """
        params: dict[str, str] = {}
        if description:
            params["beschreibung"] = description
        if originators:
            params["urheber"] = ", ".join(originators)
        if rights_holders:
            params["rechteinhaber"] = ", ".join(rights_holders)
        if license_info:
            params["lizenz"] = license_info
        params["cc"] = "ja" if ImageHandler._is_cc_license(license_info) else "nein"
        if source_url:
            params["quelle"] = source_url
        lines = ["{{BildMeta"]
        for key, value in params.items():
            lines.append(f"| {key} = {value}")
        lines.append("}}")
        return "\n".join(lines)

    @staticmethod
    def _normalize_filename(name: str) -> str:
        """Normalise *name* the way MediaWiki normalises file page titles.

        MediaWiki treats spaces and underscores as equivalent in titles and,
        with the default ``$wgCapitalLinks``, upper-cases the first character.
        ``allimages`` returns titles with spaces (e.g. ``Fmb28989 20.jpg``)
        while our local files use underscores (``fmb28989_20.jpg``), so both
        sides must be canonicalised before comparison.
        """
        name = name.replace(" ", "_")
        return name[:1].upper() + name[1:] if name else name

    def fetch_existing_filenames(self) -> set[str]:
        """Return the normalised set of file names currently on the wiki.

        Queries the MediaWiki ``allimages`` list so uploads can be reconciled
        against what actually exists, instead of trusting per-file checks or
        earlier log output (an upload may have been logged without the file
        ever landing on the wiki).
        """
        names: set[str] = set()
        try:
            for image in self.site.allimages():
                # ``title(with_ns=False)`` drops the "File:"/"Datei:" prefix.
                names.add(self._normalize_filename(image.title(with_ns=False)))
        except Exception as e:
            print(f"  Could not fetch existing wiki images: {e}")
        return names

    def load_existing_filenames(self) -> set[str]:
        """Fetch and cache the wiki's file list for this handler.

        Subsequent :meth:`upload_image` calls reconcile against this set rather
        than doing a per-file existence check.
        """
        self._existing_filenames = self.fetch_existing_filenames()
        print(f"  Wiki currently holds {len(self._existing_filenames)} file(s)")
        return self._existing_filenames

    def _already_on_wiki(self, filename: str) -> bool:
        """Whether *filename* already exists on the wiki.

        Uses the cached :attr:`_existing_filenames` set when it has been loaded
        (authoritative reconciliation); otherwise falls back to a per-file API
        check.
        """
        if self._existing_filenames is not None:
            return self._normalize_filename(filename) in self._existing_filenames
        return pywikibot.FilePage(self.site, f"File:{filename}").exists()

    def _do_upload(
        self, filepath: Path, filepage, description: str, ignore: bool
    ) -> bool:
        """Issue a single pywikibot upload call and return whether it succeeded.

        ``ignore_warnings`` lets us force-publish a file that triggers a
        ``duplicate`` warning. When warnings are present and ``ignore`` is
        ``False``, pywikibot raises :exc:`pywikibot.exceptions.UploadError`;
        we catch it and return ``False`` so the caller can retry with
        ``ignore=True``.
        """
        try:
            return self.site.upload(
                filepage,
                source_filename=str(filepath),
                comment="Automatischer Bildimport",
                text=description,
                ignore_warnings=ignore,
                chunk_size=UPLOAD_CHUNK_SIZE,
            )
        except pywikibot.exceptions.UploadError:
            return False

    def upload_image(
        self,
        filepath: Path,
        description: str = "",
        license_info: str = "",
        rights_holders: list | None = None,
        originators: list | None = None,
        source_url: str | None = None,
        overwrite_existing: bool = False,
    ) -> bool:
        """Upload *filepath* to MediaWiki. Returns ``True`` on success.

        When the image is already on the wiki and *overwrite_existing* is
        ``True``, the binary is left untouched but the file's ``{{BildMeta}}``
        description page is rewritten with the freshly built metadata (useful
        after the source data gains rights holders / originators). With
        *overwrite_existing* ``False`` an already-present image is skipped.

        A common case is a ``duplicate`` warning: the image is byte-for-byte
        identical to a file already on the wiki under a different name, so
        MediaWiki refuses to publish it. Because the articles reference each
        image by its own ``{entity_id}`` filename, the upload is re-issued with
        ``ignore_warnings`` so the file is actually published and the ``File:``
        link resolves. The wiki's own page existence is used as the final
        arbiter of success.
        """
        try:
            filename = filepath.name
            full_description = self._build_description(
                description, license_info, rights_holders, originators, source_url
            )
            if self._already_on_wiki(filename):
                if overwrite_existing:
                    return self._update_description_page(filename, full_description)
                print(f"  Image already exists: {filename}")
                return True

            print(f"  Uploading: {filename}")
            filepage = pywikibot.FilePage(self.site, f"File:{filename}")
            if not self._do_upload(filepath, filepage, full_description, ignore=False):
                print(f"  Upload of {filename} returned warnings; forcing publish")
                self._do_upload(filepath, filepage, full_description, ignore=True)

            # Final arbiter: confirm the file actually exists on the wiki.
            if not pywikibot.FilePage(self.site, f"File:{filename}").exists():
                print(f"  Upload did not publish {filename}")
                return False

            print(f"  Uploaded: {filename}")
            self._remember_uploaded(filename)
            return True
        except Exception as e:
            print(f"  Failed to upload {filepath}: {e}")
            return False

    def _update_description_page(self, filename: str, description: str) -> bool:
        """Overwrite the wikitext of an existing file's description page.

        Edits the ``File:`` page text only; the uploaded image binary is left
        in place. Returns ``True`` on a successful edit.
        """
        try:
            page = pywikibot.FilePage(self.site, f"File:{filename}")
            page.text = description
            page.save(summary="BildMeta-Metadaten aktualisiert")
            print(f"  Updated description page: {filename}")
            return True
        except Exception as e:
            print(f"  Failed to update description page for {filename}: {e}")
            return False

    def _remember_uploaded(self, filename: str) -> None:
        """Add *filename* to the cached wiki file set, if it is loaded."""
        if self._existing_filenames is not None:
            self._existing_filenames.add(self._normalize_filename(filename))
