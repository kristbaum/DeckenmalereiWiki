"""Generates the ``{{Artikel-modern}}`` citation block for an article.

This is the lightweight replacement for ``{{Infobox Deckenmalerei}}``: instead
of a detailed infobox it emits a single citation sentence and lets the template
derive the page categories (author, generic ``CbDD`` and the location parsed
from the title).
"""

import datetime
from typing import Dict

from .loader import DataLoader


def _modification_year(text_entity: Dict) -> str:
    """Return the entity's modification year as a string, or ``""`` if unknown.

    ``modificationDate`` is a millisecond epoch timestamp in the source data.
    """
    ts = text_entity.get("modificationDate")
    if not ts:
        return ""
    return str(
        datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.timezone.utc).year
    )


def generate_artikel_modern(loader: DataLoader, text_entity: Dict) -> str:
    """Build the ``{{Artikel-modern}}`` template call for *text_entity*.

    Each author is emitted as a separate numbered parameter (``AutorIn1``,
    ``AutorIn2`` …) so the template can create one category per author while
    still rendering them as a single list. ``Ort`` is the location, derived
    here as the part of the title before the first comma.
    """
    lines = ["{{Artikel-modern"]

    authors = loader.get_relations_by_type(text_entity["ID"], "AUTHORS")
    names = [
        loader.entities[rel["relTar"]]["appellation"]
        for rel in authors
        if rel.get("relTar") in loader.entities
        and loader.entities[rel["relTar"]].get("appellation")
    ]
    for i, name in enumerate(names, start=1):
        lines.append(f"| AutorIn{i} = {name}")

    appellation = text_entity.get("appellation")
    if appellation:
        lines.append(f"| Titel = {appellation}")
        ort = appellation.split(",", 1)[0].strip()
        if ort:
            lines.append(f"| Ort = {ort}")

    year = _modification_year(text_entity)
    if year:
        lines.append(f"| Jahr = {year}")

    if text_entity.get("ID"):
        lines.append(f"| ID = {text_entity['ID']}")

    lines.append("}}")
    return "\n".join(lines)
