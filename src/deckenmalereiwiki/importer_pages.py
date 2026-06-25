"""
Page, template and article publishing for :class:`MediaWikiImporter`.
"""

from pathlib import Path
from typing import Dict

import pywikibot

from .wikitext import sanitize_wikitext

# Articles of the old corpus are tagged with this category and must never be
# overwritten by the importer.
PROTECTED_CATEGORY = "CBD"


class PageImportMixin:
    """Create/overwrite main-namespace pages, templates and articles.

    Mixed into :class:`~deckenmalereiwiki.importer.MediaWikiImporter`, which
    provides the ``self.site`` attribute these methods rely on.
    """

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
                print(
                    f"  Skipped (old corpus, Kategorie:{PROTECTED_CATEGORY}): {title}"
                )
                return True
            page.text = sanitize_wikitext(content)
            page.save(summary=summary)
            print(f"  Updated: {title}")
            return True
        except Exception as e:
            print(f"  Failed to update {title}: {e}")
            return False

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

        self.import_pages()

    def import_pages(self, pages_dir: str = "pages"):
        """Upload/update every ``.wiki`` page in *pages_dir* (main namespace).

        Unlike :meth:`import_templates` these are published under their bare
        title (filename stem, underscores → spaces) with no ``Template:``
        prefix, e.g. ``Hauptseite.wiki`` → the main page ``Hauptseite``.
        """
        folder = Path(pages_dir)
        if not folder.is_dir():
            print(f"Pages folder not found: {folder}")
            return

        page_files = sorted(folder.glob("*.wiki"))
        if not page_files:
            print(f"No .wiki pages found in {folder}")
            return

        print(f"\n=== Importing {len(page_files)} pages from {folder}/ ===")
        success = 0
        for pf in page_files:
            title = pf.stem.replace("_", " ")
            content = pf.read_text(encoding="utf-8")
            if self.create_or_update_page(title, content, summary="Seiten-Import"):
                success += 1
        print(f"Successfully imported {success}/{len(page_files)} pages")

    def import_articles(self, articles: Dict[str, str]):
        """Push *articles* dict ``{title: wikitext}`` to MediaWiki."""
        print(f"\nImporting {len(articles)} articles...")
        success = 0
        for title, content in articles.items():
            if self.create_or_update_page(title, content):
                success += 1
        print(f"\nSuccessfully imported {success}/{len(articles)} articles")
