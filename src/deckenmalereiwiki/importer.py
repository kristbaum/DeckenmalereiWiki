"""
MediaWiki importer for DeckenmalereiWiki.
Uploads articles and images to a MediaWiki instance via the API.
"""

import re
import unicodedata
from pathlib import Path
from typing import Dict, Optional

import pywikibot
from pywikibot.site import APISite

from .loader import DataLoader
from .generator import ArticleGenerator
from .image_handler import ImageHandler

# Articles of the old corpus are tagged with this category and must never be
# overwritten by the importer.
PROTECTED_CATEGORY = "CBD"

# C0 control characters MediaWiki rejects as non-normalized: everything in
# U+0000–U+001F except HT (\t), LF (\n) and CR (\r).
_DISALLOWED_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitize_wikitext(text: str) -> str:
    """Return *text* as valid wiki page content for the MediaWiki API.

    MediaWiki requires NFC-normalized Unicode without C0 control characters
    other than tab/newline/carriage return; otherwise ``page.save`` emits an
    ``invalid or non-normalized data`` API warning. This normalizes to NFC and
    drops the disallowed control characters.
    """
    return _DISALLOWED_CONTROL_RE.sub("", unicodedata.normalize("NFC", text))


class MediaWikiImporter:
    """Imports articles and images to a MediaWiki instance.

    Connection details (wiki URL, credentials, throttling) come from pywikibot's
    configuration: the ``deckenmalerei`` family file plus ``user-config.py`` /
    ``user-password.cfg``. pywikibot handles write throttling, ``maxlag`` and
    retries on transient errors for us.
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
    # Article handling
    # ------------------------------------------------------------------

    def _is_old_corpus(self, page: "pywikibot.Page") -> bool:
        """Whether *page* belongs to the protected old corpus.

        Old-corpus articles carry :data:`PROTECTED_CATEGORY` and must not be
        overwritten. New pages (and any page whose categories can't be read)
        are treated as not protected.
        """
        try:
            if not page.exists():
                return False
            return any(
                cat.title(with_ns=False) == PROTECTED_CATEGORY
                for cat in page.categories()
            )
        except Exception as e:
            print(f"  Could not read categories for {page.title()}: {e}")
            return False

    def create_or_update_page(
        self, title: str, content: str, summary: str = "Automatischer Import"
    ) -> bool:
        """Create or overwrite *title* with *content*. Returns ``True`` on success.

        Existing pages tagged with :data:`PROTECTED_CATEGORY` (the old corpus)
        are left untouched.
        """
        try:
            page = pywikibot.Page(self.site, title)
            if self._is_old_corpus(page):
                print(f"  Skipped (old corpus, Kategorie:{PROTECTED_CATEGORY}): {title}")
                return True
            page.text = sanitize_wikitext(content)
            page.save(summary=summary)
            print(f"  Updated: {title}")
            return True
        except Exception as e:
            print(f"  Failed to update {title}: {e}")
            return False

    # ------------------------------------------------------------------
    # Template handling
    # ------------------------------------------------------------------

    def import_templates(self, templates_dir: str = "templates"):
        """Upload/update every ``.wiki`` template in *templates_dir*.

        Each file is published to ``Template:<title>`` where the title is the
        filename stem with underscores turned into spaces (e.g.
        ``Infobox_Deckenmalerei.wiki`` → ``Template:Infobox Deckenmalerei``).
        """
        folder = Path(templates_dir)
        if not folder.is_dir():
            print(f"Templates folder not found: {folder}")
            return

        template_files = sorted(folder.glob("*.wiki"))
        if not template_files:
            print(f"No .wiki templates found in {folder}")
            return

        print(f"\n=== Importing {len(template_files)} templates from {folder}/ ===")
        success = 0
        for tf in template_files:
            title = f"Template:{tf.stem.replace('_', ' ')}"
            content = tf.read_text(encoding="utf-8")
            if self.create_or_update_page(title, content, summary="Vorlagen-Import"):
                success += 1
        print(f"Successfully imported {success}/{len(template_files)} templates")

    def import_articles(self, articles: Dict[str, str]):
        """Push *articles* dict ``{title: wikitext}`` to MediaWiki."""
        print(f"\nImporting {len(articles)} articles...")
        success = 0
        for title, content in articles.items():
            if self.create_or_update_page(title, content):
                success += 1
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

    def _process_entity_images(
        self, loader: DataLoader, entity: Dict, overwrite_existing: bool = False
    ):
        """Download and upload all images associated with *entity*.

        When *overwrite_existing* is ``True``, images already on the wiki keep
        their binary but have their ``{{BildMeta}}`` description page refreshed.
        """
        for name_entity_id, resource in loader.get_entity_image_resources(entity["ID"]):
            fp = self.image_handler.download_image(
                resource["resProvider"], name_entity_id, resource["ID"]
            )
            if fp:
                resource_id = resource["ID"]
                rights_holders = loader.get_resource_actors(
                    resource_id, "RIGHTS_HOLDERS"
                )
                originators = loader.get_resource_actors(resource_id, "ORIGINATORS")
                source_url = self.image_handler.source_url(
                    resource["resProvider"], resource_id
                )
                self.image_handler.upload_image(
                    fp,
                    resource.get("appellation", ""),
                    resource.get("resLicense", ""),
                    rights_holders=rights_holders,
                    originators=originators,
                    source_url=source_url,
                    overwrite_existing=overwrite_existing,
                )
