"""
MediaWiki Importer
Uploads articles and images to MediaWiki instance via API.
"""

import mwclient
import requests
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse
import time


class MediaWikiImporter:
    """Imports articles and images to MediaWiki."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8080,
        username: str = "admin",
        password: str = "adminpass123",
        scheme: str = "http",
        enable_images: bool = False,
        max_articles: int = 10,
    ):
        """Initialize MediaWiki connection.

        Args:
            enable_images: If True, download and upload images. Default False.
            max_articles: Maximum number of articles to process. Default 10.
        """
        self.host = f"{host}:{port}" if port != 80 else host
        self.username = username
        self.password = password
        self.scheme = scheme
        self.enable_images = enable_images
        self.max_articles = max_articles

        # Initialize mwclient site
        self.site = mwclient.Site(self.host, path="/", scheme=scheme)

        self.downloads_dir = Path("downloads")
        self.downloads_dir.mkdir(exist_ok=True)

    def login(self):
        """Login to MediaWiki."""
        try:
            self.site.login(self.username, self.password)
            print(f"Logged in as {self.username}")
            return True
        except Exception as e:
            print(f"Login failed: {e}")
            return False

    def download_image(self, url: str, entity_id: str) -> Optional[Path]:
        """Download image from URL."""
        try:
            # Create safe filename
            ext = Path(urlparse(url).path).suffix or ".jpg"
            filename = f"Deckenmalerei_{entity_id}{ext}"
            filepath = self.downloads_dir / filename

            # Skip if already downloaded
            if filepath.exists():
                print(f"  Image already downloaded: {filename}")
                return filepath

            print(f"  Downloading: {url}")
            response = requests.get(url, timeout=30, stream=True)
            response.raise_for_status()

            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f"  Saved: {filename}")
            return filepath

        except Exception as e:
            print(f"  Failed to download {url}: {e}")
            return None

    def upload_image(
        self, filepath: Path, description: str = "", license_info: str = ""
    ) -> bool:
        """Upload image to MediaWiki."""
        try:
            filename = filepath.name

            # Check if file already exists
            image = self.site.images[filename]
            if image.imageinfo:
                print(f"  Image already exists: {filename}")
                return True

            # Prepare description
            full_description = f"{description}\n\n"
            if license_info:
                full_description += f"Lizenz: {license_info}\n"

            print(f"  Uploading: {filename}")
            with open(filepath, "rb") as f:
                self.site.upload(
                    file=f,
                    filename=filename,
                    description=full_description,
                    ignore=False,
                )

            print(f"  Uploaded: {filename}")
            return True

        except Exception as e:
            print(f"  Failed to upload {filepath}: {e}")
            return False

    def create_or_update_page(
        self, title: str, content: str, summary: str = "Automatischer Import"
    ) -> bool:
        """Create or update a MediaWiki page."""
        try:
            page = self.site.pages[title]
            page.save(content, summary=summary)
            print(f"  Updated: {title}")
            return True
        except Exception as e:
            print(f"  Failed to update {title}: {e}")
            return False

    def import_articles(self, articles: Dict[str, str]):
        """Import multiple articles to MediaWiki."""
        print(f"\nImporting {len(articles)} articles...")
        success_count = 0

        for title, content in articles.items():
            if self.create_or_update_page(title, content):
                success_count += 1
            time.sleep(0.05)  # Don't be nice to the server, it's local

        print(f"\nSuccessfully imported {success_count}/{len(articles)} articles")

    def import_from_parser(self, parser):
        """Import articles and images from DeckenmalereiParser instance."""
        from parser import DeckenmalereiParser

        if not isinstance(parser, DeckenmalereiParser):
            raise ValueError("Expected DeckenmalereiParser instance")

        print("Starting import process...")

        # Get all TEXT entities (limited by max_articles)
        text_entities = parser.get_text_entities()[: self.max_articles]
        print(
            f"Processing {len(text_entities)} articles (max_articles={self.max_articles})"
        )

        # Download and upload images first (only if enabled)
        if self.enable_images:
            print(f"\n=== Processing images for {len(text_entities)} articles ===")
            for entity in text_entities:
                title = entity.get("appellation", f"Untitled_{entity['ID']}")
                print(f"\nProcessing images for: {title}")

                # Get lead resource
                lead_resource = parser.get_lead_resource(entity["ID"])
                if lead_resource and lead_resource.get("resProvider"):
                    url = lead_resource["resProvider"]
                    filepath = self.download_image(url, entity["ID"])

                    if filepath:
                        description = lead_resource.get("appellation", "")
                        license_info = lead_resource.get("resLicense", "")
                        self.upload_image(filepath, description, license_info)
        else:
            print(
                "\n=== Image processing disabled (use enable_images=True to enable) ==="
            )

        # Generate and import articles
        print("\n=== Importing articles ===")
        articles = parser.generate_all_articles(max_articles=self.max_articles)
        self.import_articles(articles)


def main():
    """Main entry point for standalone usage."""
    from parser import DeckenmalereiParser

    # Parse data
    print("Loading and parsing data...")
    parser = DeckenmalereiParser()
    parser.load_data()

    # Import to MediaWiki
    importer = MediaWikiImporter()

    if importer.login():
        importer.import_from_parser(parser)
        print("\n✓ Import complete!")
    else:
        print("\n✗ Import failed - could not login")


if __name__ == "__main__":
    main()
