"""
Standalone image download helper for DeckenmalereiWiki.
"""

from pathlib import Path
import time
from typing import Optional
from urllib.parse import urlparse

import requests

DOWNLOADS_DIR = Path("downloads")


def download_image(
    url: str,
    entity_id: str,
    resource_id: str,
    downloads_dir: Path = DOWNLOADS_DIR,
) -> Optional[Path]:
    """Download image from URL.

    Args:
        url: Base provider URL (e.g., https://bildindex.de)
        entity_id: Entity ID for filename
        resource_id: Resource ID from resources.json
        downloads_dir: Directory to save downloads into.
    """
    downloads_dir.mkdir(exist_ok=True)
    try:
        # Construct actual image URL based on provider
        if "bildindex.de" in url:
            image_url = f"https://previous.bildindex.de/bilder/{resource_id}a.jpg"
            ext = ".jpg"
        elif "deckenmalerei-bilder.badw.de" in url:
            # EasyDB: Query API first to get the actual download URL
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

            ext = ".jpg"
            time.sleep(0.5)  # Be nice to the EasyDB server
        else:
            # Fallback: try to use URL as-is
            print(f"  Unknown image provider: {url}")
            image_url = url
            ext = Path(urlparse(url).path).suffix or ".jpg"

        # Create safe filename
        filename = f"Deckenmalerei_{entity_id}{ext}"
        filepath = downloads_dir / filename

        # Skip if already downloaded
        if filepath.exists():
            print(f"  Image already downloaded: {filename}")
            return filepath

        print(f"  Downloading: {image_url}")
        response = requests.get(image_url, timeout=30, stream=True)
        response.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"  Saved: {filename}")
        time.sleep(0.2)  # Be nice to the server
        return filepath

    except Exception as e:
        print(f"  Failed to download from {url} (resource: {resource_id}): {e}")
        return None
