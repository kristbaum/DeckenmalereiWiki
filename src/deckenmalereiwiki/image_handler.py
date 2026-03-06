"""
Image download and upload handling for DeckenmalereiWiki.
"""

import time
from pathlib import Path
from typing import Optional
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

    def download_image(
        self, url: str, entity_id: str, resource_id: str
    ) -> Optional[Path]:
        """Download an image from *url* and save it locally.

        Args:
            url:         Provider base URL (used to determine download strategy).
            entity_id:   Entity ID used in the output filename.
            resource_id: Resource ID from resources.json.

        Returns:
            Local :class:`~pathlib.Path` of the downloaded file, or ``None``.
        """
        try:
            # Check if already downloaded (any extension) before making network calls
            existing = next(self.downloads_dir.glob(f"{entity_id}.*"), None)
            if existing:
                print(f"  Image already downloaded: {existing.name}")
                return existing

            if "bildindex.de" in url:
                image_url = f"https://previous.bildindex.de/bilder/{resource_id}a.jpg"
                ext = ".jpg"
            elif "deckenmalerei-bilder.badw.de" in url:
                print(f"  Querying EasyDB API for resource {resource_id}...")
                api_url = f"https://deckenmalerei-bilder.badw.de/api/v1/objects/uuid/{resource_id}"
                api_response = requests.get(api_url, timeout=30)
                api_response.raise_for_status()
                api_data = api_response.json()
                versions = (
                    api_data.get("assets", {}).get("datei", [{}])[0].get("versions", {})
                )
                for quality in ("full", "huge", "preview"):
                    v = versions.get(quality, {})
                    if v.get("_download_allowed"):
                        image_url = v["download_url"]
                        break
                else:
                    print(f"  No downloadable version found for {resource_id}")
                    return None
                ext = Path(urlparse(image_url).path).suffix or ".jpg"
                time.sleep(0.5)
            else:
                print(f"  Unknown image provider: {url}")
                image_url = url
                ext = Path(urlparse(url).path).suffix or ".jpg"

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

    def upload_image(
        self,
        filepath: Path,
        description: str = "",
        license_info: str = "",
        rights_holders: list | None = None,
        originators: list | None = None,
    ) -> bool:
        """Upload *filepath* to MediaWiki. Returns ``True`` on success."""
        try:
            filename = filepath.name
            image = self.site.images[filename]
            if image.imageinfo:
                print(f"  Image already exists: {filename}")
                return True

            parts = []
            if description:
                parts.append(description)
            if originators:
                parts.append("Urheber: " + ", ".join(originators))
            if rights_holders:
                parts.append("Rechteinhaber: " + ", ".join(rights_holders))
            if license_info:
                parts.append(f"Lizenz: {license_info}")
            full_description = "\n".join(parts)

            print(f"  Uploading: {filename}")
            with open(filepath, "rb") as f:
                self.site.upload(
                    file=f,
                    filename=filename,
                    description=full_description,
                    ignore=False,
                )
            print(f"  Uploaded: {filename}")
            time.sleep(1.0)
            return True
        except Exception as e:
            print(f"  Failed to upload {filepath}: {e}")
            return False
