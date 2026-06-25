"""
Category-page creation for :class:`MediaWikiImporter`.
"""

from typing import Dict

import pywikibot

from .loader import DataLoader
from .wikitext import sanitize_wikitext
from .artikel_modern import get_author_names, get_building, get_ort

# Static category that every modern article is filed under (see the
# ``{{Artikel-modern}}`` template). Created once by ``import-categories``.
ROOT_CATEGORY = "CbDD"

# Root categories that group the per-author, per-location, per-state and
# per-module categories so the wiki stays navigable. All are themselves filed
# under ``ROOT_CATEGORY``.
AUTHOR_ROOT_CATEGORY = "AutorInnen"
LOCATION_ROOT_CATEGORY = "Ort"
STATE_ROOT_CATEGORY = "Bundesländer"
MODULE_ROOT_CATEGORY = "Module"


class CategoryImportMixin:
    """Create the category pages the ``{{Artikel-modern}}`` template relies on.

    Mixed into :class:`~deckenmalereiwiki.importer.MediaWikiImporter`, which
    provides the ``self.site`` attribute these methods rely on.
    """

    def create_category_if_missing(self, name: str, content: str = "") -> bool:
        """Create ``Kategorie:<name>`` with *content* unless it already exists.

        Returns ``True`` when a new page is created. Existing category pages are
        left untouched so manually curated descriptions are never clobbered.
        """
        try:
            page = pywikibot.Page(self.site, name, ns=14)
            if page.exists():
                print(f"  Exists, skipped: {page.title()}")
                return False
            page.text = sanitize_wikitext(content)
            page.save(summary="Kategorie-Import")
            print(f"  Created: {page.title()}")
            return True
        except Exception as e:
            print(f"  Failed to create category {name}: {e}")
            return False

    def collect_category_names(self, loader: DataLoader) -> Dict[str, str]:
        """Return ``{category_name: page_content}`` for every required category.

        Gathers the static :data:`ROOT_CATEGORY` and the
        :data:`AUTHOR_ROOT_CATEGORY`, :data:`LOCATION_ROOT_CATEGORY`,
        :data:`STATE_ROOT_CATEGORY` and :data:`MODULE_ROOT_CATEGORY` group
        categories, plus one category per author, location, federal state and
        module across all TEXT entities. These mirror the categories the
        ``{{Artikel-modern}}`` template files each article under. Per-author
        categories are filed under ``AutorInnen``, per-location under ``Ort``,
        per-state under ``Bundesländer`` and per-module under ``Module``; all
        groups (and the descriptive root) sit under ``CbDD`` so the wiki stays
        navigable.
        """
        under_root = f"[[Kategorie:{ROOT_CATEGORY}]]"
        categories: Dict[str, str] = {
            ROOT_CATEGORY: (
                "Artikel des Corpus der barocken Deckenmalerei in Deutschland (CbDD)."
            ),
            AUTHOR_ROOT_CATEGORY: (
                "AutorInnen von Artikeln des Corpus der barocken Deckenmalerei "
                "in Deutschland.\n" + under_root
            ),
            LOCATION_ROOT_CATEGORY: (
                "Orte der im Corpus der barocken Deckenmalerei in Deutschland "
                "behandelten Werke.\n" + under_root
            ),
            STATE_ROOT_CATEGORY: (
                "Bundesländer der im Corpus der barocken Deckenmalerei in "
                "Deutschland behandelten Werke.\n" + under_root
            ),
            MODULE_ROOT_CATEGORY: (
                "Module des Corpus der barocken Deckenmalerei in Deutschland.\n"
                + under_root
            ),
        }
        under_authors = f"[[Kategorie:{AUTHOR_ROOT_CATEGORY}]]"
        under_locations = f"[[Kategorie:{LOCATION_ROOT_CATEGORY}]]"
        under_states = f"[[Kategorie:{STATE_ROOT_CATEGORY}]]"
        under_modules = f"[[Kategorie:{MODULE_ROOT_CATEGORY}]]"
        for entity in loader.get_text_entities():
            for author in get_author_names(loader, entity):
                categories.setdefault(author, under_authors)
            ort = get_ort(entity)
            if ort:
                categories.setdefault(ort, under_locations)
            building = get_building(loader, entity)
            if building:
                state = building.get("addressState")
                if state:
                    categories.setdefault(state, under_states)
                module = building.get("moduleNumber")
                if module is not None and module != "":
                    categories.setdefault(f"Modul {module}", under_modules)
        return categories

    def import_categories(self, loader: DataLoader) -> None:
        """Create all category pages derived from *loader* that are missing."""
        categories = self.collect_category_names(loader)
        print(f"\n=== Creating up to {len(categories)} categories ===")
        created = 0
        for name, content in sorted(categories.items()):
            if self.create_category_if_missing(name, content):
                created += 1
        print(f"\nCreated {created} new categories ({len(categories)} total)")
