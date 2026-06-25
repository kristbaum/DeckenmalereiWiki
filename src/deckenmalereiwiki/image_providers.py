"""
Provider-specific source resolution for DeckenmalereiWiki images.

Maps a resource's provider base URL to the URLs needed to fetch and cite its
image. Kept separate from the up/download mechanics in :mod:`image_handler` so
the offline ``parse`` step can resolve ``File:`` filenames without dragging in
the upload machinery.
"""

import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

# Providers we can only link to, not download from: session-based viewers (the
# Virtuelles Kupferstichkabinett of HAUM / HAB) with no derivable direct-image
# URL. Their images are referenced via the {{ExternesBild}} template instead of
# being uploaded as ``File:`` pages.
EXTERNAL_PROVIDERS = ("haum-bs.de", "diglib.hab.de")


class SourceResolver:
    """Resolve a resource's provider URL to download and citation links.

    Holds the per-resource EasyDB resolution cache so generation and download
    share a single API call. When *offline*, never makes network calls to
    resolve a resource (e.g. the BADW EasyDB API); used by the article
    generator's ``parse`` step, which resolves ``File:`` filenames purely from
    the local downloads and their ``{entity_id}.json`` metadata sidecars.
    """

    def __init__(self, offline: bool = False):
        self.offline = offline
        # Cache of EasyDB resolutions:
        #   resource_id -> (download_url, source_url, extension).
        self._easydb_cache: dict[str, tuple[Optional[str], Optional[str], str]] = {}

    @staticmethod
    def is_external(url: str) -> bool:
        """Whether *url*'s provider is referenced by link, not uploaded.

        ``True`` for the source-link-only providers (see
        :data:`EXTERNAL_PROVIDERS`): their images carry a ``source_url`` but no
        downloadable binary, so the generator emits ``{{ExternesBild}}`` rather
        than a ``File:`` reference.
        """
        return any(provider in url for provider in EXTERNAL_PROVIDERS)

    def _easydb_source(
        self, resource_id: str
    ) -> tuple[Optional[str], Optional[str], str]:
        """Resolve a BADW EasyDB resource to ``(download_url, source_url, ext)``.

        The result is cached per ``resource_id`` so generation and download
        share a single API call. ``download_url`` is ``None`` when no
        downloadable version exists (``extension`` then defaults to ``.jpg``).
        For EasyDB the source link is the same as the download URL.
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
        result = (image_url, image_url, ext)
        self._easydb_cache[resource_id] = result
        time.sleep(0.5)
        return result

    def resolve_source(
        self, url: str, resource_id: str
    ) -> tuple[Optional[str], Optional[str], str]:
        """Return ``(download_url, source_url, extension)`` for a resource.

        ``download_url`` is the URL the binary is fetched from, or ``None`` when
        the resource has no downloadable version. ``source_url`` is the link
        recorded in ``{{BildMeta}}`` back to the original; for most providers it
        equals ``download_url``, but for session-based viewers it is the
        resource's canonical landing page even though no binary can be fetched.
        """
        if "bildindex.de" in url:
            image_url = f"https://previous.bildindex.de/bilder/{resource_id}a.jpg"
            return image_url, image_url, ".jpg"
        if "deckenmalerei-bilder.badw.de" in url:
            if self.offline:
                # parse must not touch the network; the sidecar/existing file is
                # authoritative and the API extension is irrelevant here.
                return None, None, ".jpg"
            return self._easydb_source(resource_id)
        if self.is_external(url):
            # Virtuelles Kupferstichkabinett (HAUM / HAB): a session-based viewer
            # with no derivable direct-image URL, so the binary is not
            # downloaded. The resource ID is itself the canonical landing page,
            # recorded as the source link.
            return None, resource_id, ".jpg"
        print(f"  Unknown image provider: {url}")
        ext = Path(urlparse(url).path).suffix or ".jpg"
        return url, url, ext

    def resolve_extension(self, url: str, resource_id: str) -> str:
        """Best-effort file extension for a resource (e.g. ``".jpg"``).

        Prefers an already-downloaded file, then provider rules. Never raises:
        on a network failure it falls back to ``".jpg"`` so offline generation
        still succeeds.
        """
        try:
            return self.resolve_source(url, resource_id)[2]
        except Exception as e:
            print(f"  Could not resolve extension for {resource_id}: {e}; using .jpg")
            return ".jpg"

    def source_url(self, url: str, resource_id: str) -> Optional[str]:
        """Return the URL of the original image's source page, or ``None``.

        This is recorded in ``{{BildMeta}}`` as a link back to the original (the
        bildindex image, the BADW EasyDB download URL, or a viewer's landing
        page). Never raises.
        """
        try:
            return self.resolve_source(url, resource_id)[1]
        except Exception:
            return None
