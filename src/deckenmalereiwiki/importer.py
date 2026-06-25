"""
MediaWiki importer for DeckenmalereiWiki.
Uploads articles and images to a MediaWiki instance via the API.
"""

from pathlib import Path
from typing import Dict, Optional

import pywikibot
from pywikibot.site import APISite

from .loader import DataLoader
from .generator import ArticleGenerator
from .image_handler import ImageHandler
from .wikitext import sanitize_wikitext
from .importer_pages import PageImportMixin, PROTECTED_CATEGORY
from .importer_categories import (
    CategoryImportMixin,
    ROOT_CATEGORY,
    AUTHOR_ROOT_CATEGORY,
    LOCATION_ROOT_CATEGORY,
    STATE_ROOT_CATEGORY,
    MODULE_ROOT_CATEGORY,
)
from .importer_images import EntityImageImportMixin

__all__ = [
    "MediaWikiImporter",
    "sanitize_wikitext",
    "PROTECTED_CATEGORY",
    "ROOT_CATEGORY",
    "AUTHOR_ROOT_CATEGORY",
    "LOCATION_ROOT_CATEGORY",
    "STATE_ROOT_CATEGORY",
    "MODULE_ROOT_CATEGORY",
]


class MediaWikiImporter(PageImportMixin, CategoryImportMixin, EntityImageImportMixin):
    """Imports articles and images to a MediaWiki instance.

    Connection details (wiki URL, credentials, throttling) come from pywikibot's
    configuration: the ``deckenmalerei`` family file plus ``user-config.py`` /
    ``user-password.cfg``. pywikibot handles write throttling, ``maxlag`` and
    retries on transient errors for us.

    The page/template, category and per-entity image publishing methods live in
    :class:`~deckenmalereiwiki.importer_pages.PageImportMixin`,
    :class:`~deckenmalereiwiki.importer_categories.CategoryImportMixin` and
    :class:`~deckenmalereiwiki.importer_images.EntityImageImportMixin`; this
    class wires them together and drives the overall import.
    """

    def __init__(
        self,
        enable_images: bool = True,
        max_articles: int = 50000,
        site: Optional[APISite] = None,
    ):
        """Initialise the MediaWiki connection.

        Args:
            enable_images: Download and upload images when ``True``.
            max_articles:  Maximum number of articles to process.
            site:          Optional pre-built pywikibot site; defaults to
                           :func:`pywikibot.Site` (resolved from user-config).
        """
        self.enable_images = enable_images
        self.max_articles = max_articles

        self.site = site or pywikibot.Site()

        self.downloads_dir = Path("downloads")
        self.downloads_dir.mkdir(exist_ok=True)

        self.image_handler = ImageHandler(self.site, self.downloads_dir)

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(self) -> bool:
        """Log in to MediaWiki. Returns ``True`` on success."""
        try:
            self.site.login()
            print(f"Logged in as {self.site.username()}")
            return True
        except Exception as e:
            print(f"Login failed: {e}")
            return False

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

        self.import_templates()

        print(f"\n=== Importing {len(articles)} articles from {folder}/ ===")
        self.import_articles(articles)

    def import_from_loader(self, loader: DataLoader):
        """Import articles and images from a loaded :class:`DataLoader` instance.

        Args:
            loader: A :class:`~deckenmalereiwiki.loader.DataLoader` with data already loaded.
        """
        generator = ArticleGenerator(loader)
        print("Starting import process...")

        self.import_templates()

        text_entities = loader.get_text_entities()[: self.max_articles]
        print(
            f"Processing {len(text_entities)} articles (max_articles={self.max_articles})"
        )

        if self.enable_images:
            print(f"\n=== Processing images for {len(text_entities)} articles ===")
            self.image_handler.load_existing_filenames()
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
