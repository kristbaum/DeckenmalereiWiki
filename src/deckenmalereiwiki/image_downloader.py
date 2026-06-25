"""
Local image downloading (no upload) for DeckenmalereiWiki, used for debugging
the image-handling pipeline.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from .image_handler import ImageHandler


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
            provider = resource.get("resProvider", "")
            # Source-link-only providers have no downloadable binary and the
            # generator references them via {{ExternesBild}} instead of a
            # File: page, so there is nothing to download or cache here. Their
            # resource ID is also a full URL, which is not a valid sidecar name.
            if self.handler.is_external(provider):
                print(f"  Skipping external provider: {provider}")
                continue
            filepath = self.handler.download_image(
                provider,
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
