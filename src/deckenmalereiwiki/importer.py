"""
MediaWiki importer for DeckenmalereiWiki.
Uploads articles and images to a MediaWiki instance via the API.
"""

import time
from pathlib import Path
from typing import Dict, Optional

import mwclient

from .loader import DataLoader
from .generator import ArticleGenerator
from .image_handler import ImageHandler


class MediaWikiImporter:
    """Imports articles and images to a MediaWiki instance."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8080,
        username: str = "admin",
        password: str = "adminpass123",
        scheme: str = "http",
        enable_images: bool = True,
        max_articles: int = 2,
    ):
        """Initialise the MediaWiki connection.

        Args:
            host:          Hostname of the MediaWiki server.
            port:          Port number (default 8080).
            username:      Admin username.
            password:      Admin password.
            scheme:        ``"http"`` or ``"https"``.
            enable_images: Download and upload images when ``True``.
            max_articles:  Maximum number of articles to process.
        """
        self.host = f"{host}:{port}" if port != 80 else host
        self.username = username
        self.password = password
        self.scheme = scheme
        self.enable_images = enable_images
        self.max_articles = max_articles

        self.site = mwclient.Site(self.host, path="/", scheme=scheme)

        self.downloads_dir = Path("downloads")
        self.downloads_dir.mkdir(exist_ok=True)

        self.image_handler = ImageHandler(self.site, self.downloads_dir)

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(self) -> bool:
        """Log in to MediaWiki. Returns ``True`` on success."""
        try:
            self.site.login(self.username, self.password)
            print(f"Logged in as {self.username}")
            return True
        except Exception as e:
            print(f"Login failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Article handling
    # ------------------------------------------------------------------

    def create_or_update_page(
        self, title: str, content: str, summary: str = "Automatischer Import"
    ) -> bool:
        """Create or overwrite *title* with *content*. Returns ``True`` on success."""
        try:
            page = self.site.pages[title]
            page.edit(content, summary=summary)
            print(f"  Updated: {title}")
            return True
        except Exception as e:
            print(f"  Failed to update {title}: {e}")
            return False

    def import_articles(self, articles: Dict[str, str]):
        """Push *articles* dict ``{title: wikitext}`` to MediaWiki."""
        print(f"\nImporting {len(articles)} articles...")
        success = 0
        for title, content in articles.items():
            if self.create_or_update_page(title, content):
                success += 1
            time.sleep(0.05)
        print(f"\nSuccessfully imported {success}/{len(articles)} articles")

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def import_from_output_folder(self, output_dir: str = "output"):
        """Import pre-generated ``.wiki`` files from *output_dir*.

        Reads every ``.wiki`` file in the folder, derives the page title
        from the filename (underscores → spaces, extension stripped), and
        uploads it to MediaWiki.

        Args:
            output_dir: Path to the folder containing ``.wiki`` files.
        """
        folder = Path(output_dir)
        if not folder.is_dir():
            print(f"Output folder not found: {folder}")
            return

        wiki_files = sorted(folder.glob("*.wiki"))
        if not wiki_files:
            print(f"No .wiki files found in {folder}")
            return

        articles: Dict[str, str] = {}
        for wf in wiki_files[: self.max_articles] if self.max_articles else wiki_files:
            title = wf.stem.replace("_", " ")
            articles[title] = wf.read_text(encoding="utf-8")

        print(f"\n=== Importing {len(articles)} articles from {folder}/ ===")
        self.import_articles(articles)

    def import_from_loader(self, loader: DataLoader):
        """Import articles and images from a loaded :class:`DataLoader` instance.

        Args:
            loader: A :class:`~deckenmalereiwiki.loader.DataLoader` with data already loaded.
        """
        generator = ArticleGenerator(loader)
        print("Starting import process...")

        text_entities = loader.get_text_entities()[: self.max_articles]
        print(
            f"Processing {len(text_entities)} articles (max_articles={self.max_articles})"
        )

        if self.enable_images:
            print(f"\n=== Processing images for {len(text_entities)} articles ===")
            for entity in text_entities:
                title = entity.get("appellation", f"Untitled_{entity['ID']}")
                print(f"\nProcessing images for: {title}")
                self._process_entity_images(loader, entity)
        else:
            print(
                "\n=== Image processing disabled (use enable_images=True to enable) ==="
            )

        print("\n=== Importing articles ===")
        articles = generator.generate_all_articles(max_articles=self.max_articles)
        self.import_articles(articles)

    def _process_entity_images(self, loader: DataLoader, entity: Dict):
        """Download and upload all images associated with *entity*."""

        def _handle(resource: Optional[Dict], name_entity_id: str):
            if resource and resource.get("resProvider"):
                fp = self.image_handler.download_image(
                    resource["resProvider"], name_entity_id, resource["ID"]
                )
                if fp:
                    self.image_handler.upload_image(
                        fp,
                        resource.get("appellation", ""),
                        resource.get("resLicense", ""),
                    )

        _handle(loader.get_lead_resource(entity["ID"]), entity["ID"])

        for part in loader.get_text_parts(entity["ID"]):
            _handle(loader.get_lead_resource(part["ID"]), part["ID"])
            for img in loader.get_images(part["ID"]):
                _handle(img if img.get("resProvider") else None, img["ID"])
