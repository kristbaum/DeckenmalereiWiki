"""
Image download and upload handling for DeckenmalereiWiki.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests


class ImageHandler:
    """Handles downloading images from providers and uploading them to MediaWiki."""

    def __init__(self, site, downloads_dir: Path):
        """Initialise the handler.

        Args:
            site:          An authenticated :mod:`mwclient` site instance.
            downloads_dir: Directory where downloaded images are cached.
        """
        self.site = site
        self.downloads_dir = downloads_dir
        # Cache of EasyDB resolutions: resource_id -> (download_url, extension).
        self._easydb_cache: dict[str, tuple[Optional[str], str]] = {}
        # Normalised set of file names that exist on the wiki, fetched once via
        # ``load_existing_filenames``. ``None`` means "not loaded": uploads then
        # fall back to a per-file check.
        self._existing_filenames: Optional[set[str]] = None

    @staticmethod
    def _is_cc_license(license: str) -> bool:
        return license.strip().upper().startswith("CC")

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

    def _easydb_source(self, resource_id: str) -> tuple[Optional[str], str]:
        """Resolve a BADW EasyDB resource to ``(download_url, extension)``.

        The result is cached per ``resource_id`` so generation and download
        share a single API call. ``download_url`` is ``None`` when no
        downloadable version exists (``extension`` then defaults to ``.jpg``).
        """
        if resource_id in self._easydb_cache:
            return self._easydb_cache[resource_id]

        print(f"  Querying EasyDB API for resource {resource_id}...")
        api_url = (
            f"https://deckenmalerei-bilder.badw.de/api/v1/objects/uuid/{resource_id}"
        )
        api_response = requests.get(api_url, timeout=30)
        api_response.raise_for_status()
        api_data = api_response.json()
        versions = api_data.get("assets", {}).get("datei", [{}])[0].get("versions", {})

        image_url: Optional[str] = None
        for quality in ("full", "huge", "preview"):
            v = versions.get(quality, {})
            if v.get("_download_allowed"):
                image_url = v["download_url"]
                break

        ext = (Path(urlparse(image_url).path).suffix or ".jpg") if image_url else ".jpg"
        result = (image_url, ext)
        self._easydb_cache[resource_id] = result
        time.sleep(0.5)
        return result

    def _resolve_source(
        self, url: str, resource_id: str
    ) -> tuple[Optional[str], str]:
        """Return ``(image_url, extension)`` for a provider *url* and resource.

        ``image_url`` is ``None`` when the resource has no downloadable version.
        This is the single source of truth for both the download filename and
        the ``File:`` reference the generator emits.
        """
        if "bildindex.de" in url:
            return f"https://previous.bildindex.de/bilder/{resource_id}a.jpg", ".jpg"
        if "deckenmalerei-bilder.badw.de" in url:
            return self._easydb_source(resource_id)
        print(f"  Unknown image provider: {url}")
        return url, Path(urlparse(url).path).suffix or ".jpg"

    def resolve_extension(self, url: str, resource_id: str) -> str:
        """Best-effort file extension for a resource (e.g. ``".jpg"``).

        Prefers an already-downloaded file, then provider rules. Never raises:
        on a network failure it falls back to ``".jpg"`` so offline generation
        still succeeds.
        """
        try:
            return self._resolve_source(url, resource_id)[1]
        except Exception as e:
            print(f"  Could not resolve extension for {resource_id}: {e}; using .jpg")
            return ".jpg"

    def image_filename(self, entity_id: str, url: str, resource_id: str) -> str:
        """Return the MediaWiki filename (``{entity_id}{ext}``) for a resource.

        Uses the same extension resolution as :meth:`download_image`, so the
        ``File:`` reference always matches the uploaded file. An already
        downloaded file is authoritative and avoids any network call.
        """
        existing = self._existing_download(entity_id)
        if existing:
            return existing.name
        return f"{entity_id}{self.resolve_extension(url, resource_id)}"

    def source_url(self, url: str, resource_id: str) -> Optional[str]:
        """Return the direct URL of the original image, or ``None``.

        This is the URL the image is downloaded from (e.g. the bildindex image
        or the BADW EasyDB download URL) and is recorded in ``{{BildMeta}}`` as
        a link back to the original. Never raises.
        """
        try:
            return self._resolve_source(url, resource_id)[0]
        except Exception:
            return None

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

            image_url, ext = self._resolve_source(url, resource_id)
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
                title = image.name
                if ":" in title:  # strip the "File:"/"Datei:" namespace prefix
                    title = title.split(":", 1)[1]
                names.add(self._normalize_filename(title))
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
        return bool(self.site.images[filename].imageinfo)

    @staticmethod
    def _upload_payload(result) -> dict:
        """Return the ``upload`` payload from a ``site.upload`` result.

        Normal uploads return the payload directly, while chunked uploads
        (large files) return it wrapped under an ``"upload"`` key. This
        flattens both shapes so callers can read ``result``/``warnings``.
        """
        if isinstance(result, dict):
            return result.get("upload", result)
        return {}

    def _do_upload(self, filepath: Path, description: str, ignore: bool):
        """Issue a single ``site.upload`` call and return its raw result."""
        with open(filepath, "rb") as f:
            return self.site.upload(
                file=f,
                filename=filepath.name,
                description=description,
                ignore=ignore,
            )

    def upload_image(
        self,
        filepath: Path,
        description: str = "",
        license_info: str = "",
        rights_holders: list | None = None,
        originators: list | None = None,
        source_url: str | None = None,
    ) -> bool:
        """Upload *filepath* to MediaWiki. Returns ``True`` on success.

        ``site.upload`` does **not** raise on a ``result: "Warning"`` response —
        it leaves the file stashed but unpublished and returns the warnings. The
        common case here is a ``duplicate`` warning: the image is byte-for-byte
        identical to a file already on the wiki under a different name, so
        MediaWiki refuses to publish it. Because the articles reference each
        image by its own ``{entity_id}`` filename, we re-issue the upload with
        ``ignorewarnings`` so the file is actually published and the ``File:``
        link resolves. The wiki's own ``imageinfo`` is used as the final arbiter
        of success, since chunked-upload result shapes are inconsistent.
        """
        try:
            filename = filepath.name
            if self._already_on_wiki(filename):
                print(f"  Image already exists: {filename}")
                return True

            full_description = self._build_description(
                description, license_info, rights_holders, originators, source_url
            )

            print(f"  Uploading: {filename}")
            payload = self._upload_payload(
                self._do_upload(filepath, full_description, ignore=False)
            )

            if payload.get("result") != "Success":
                warnings = payload.get("warnings", {})
                if "exists" in warnings:  # same name already present; done
                    print(f"  Image already exists: {filename}")
                    self._remember_uploaded(filename)
                    return True
                print(
                    f"  Upload of {filename} returned warnings "
                    f"({', '.join(warnings) or payload.get('result')}); forcing publish"
                )
                self._upload_payload(
                    self._do_upload(filepath, full_description, ignore=True)
                )

            # Final arbiter: confirm the file actually exists on the wiki.
            if not self.site.images[filename].imageinfo:
                print(f"  Upload did not publish {filename}")
                return False

            print(f"  Uploaded: {filename}")
            self._remember_uploaded(filename)
            time.sleep(1.0)
            return True
        except Exception as e:
            print(f"  Failed to upload {filepath}: {e}")
            return False

    def _remember_uploaded(self, filename: str) -> None:
        """Add *filename* to the cached wiki file set, if it is loaded."""
        if self._existing_filenames is not None:
            self._existing_filenames.add(self._normalize_filename(filename))


class ImageDownloader:
    """Download images locally without uploading, for debugging image handling.

    For every image associated with a TEXT entity it downloads the file into
    ``downloads/`` (reusing :class:`ImageHandler`) and writes a JSON metadata
    sidecar ``{entity_id}.json`` next to it. The sidecar records exactly what
    *would* be uploaded to MediaWiki — provider, license, description and the
    rights/originator actors — so the result can be inspected without a wiki.
    """

    def __init__(self, loader, downloads_dir: Path):
        """Initialise the downloader.

        Args:
            loader:        A loaded :class:`~deckenmalereiwiki.loader.DataLoader`.
            downloads_dir: Directory where images and sidecars are written.
        """
        self.loader = loader
        self.downloads_dir = downloads_dir
        # site is unused for downloading, so no MediaWiki connection is needed.
        self.handler = ImageHandler(site=None, downloads_dir=downloads_dir)

    def download_entity_images(self, entity: Dict) -> List[Dict]:
        """Download every image for *entity* and write metadata sidecars.

        Returns the list of metadata dicts that were written.
        """
        written: List[Dict] = []
        for name_entity_id, resource in self.loader.get_entity_image_resources(
            entity["ID"]
        ):
            filepath = self.handler.download_image(
                resource["resProvider"],
                name_entity_id,
                resource["ID"],
            )
            metadata = self._build_metadata(name_entity_id, resource, filepath)
            self._write_metadata(name_entity_id, metadata)
            written.append(metadata)
        return written

    def _build_metadata(
        self, name_entity_id: str, resource: Dict, filepath: Optional[Path]
    ) -> Dict:
        """Assemble the metadata sidecar contents for one image."""
        resource_id = resource["ID"]
        license_info = resource.get("resLicense", "")
        return {
            "entity_id": name_entity_id,
            "resource_id": resource_id,
            "provider": resource.get("resProvider", ""),
            "license": license_info,
            "is_cc": ImageHandler._is_cc_license(license_info),
            "description": resource.get("appellation", ""),
            "rights_holders": self.loader.get_resource_actors(
                resource_id, "RIGHTS_HOLDERS"
            ),
            "originators": self.loader.get_resource_actors(resource_id, "ORIGINATORS"),
            "source_url": self.handler.source_url(
                resource.get("resProvider", ""), resource_id
            ),
            "downloaded": filepath is not None,
            "image_file": filepath.name if filepath else None,
        }

    def _write_metadata(self, name_entity_id: str, metadata: Dict) -> Path:
        """Write *metadata* to ``{name_entity_id}.json`` in the downloads dir."""
        path = self.downloads_dir / f"{name_entity_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        return path
