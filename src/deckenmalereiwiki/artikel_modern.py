"""Generates the ``{{Artikel-modern}}`` citation block for an article.

This is the lightweight replacement for ``{{Infobox Deckenmalerei}}``: instead
of a detailed infobox it emits a single citation sentence and lets the template
derive the page categories (author, generic ``CbDD`` and the location parsed
from the title).
"""

import datetime
from typing import Dict, List, Optional

from .loader import DataLoader


def get_author_names(loader: DataLoader, text_entity: Dict) -> List[str]:
    """Return the appellations of the entity's authors (``AUTHORS`` relation).

    Authors missing from ``entities.json`` or without an appellation are
    skipped, mirroring how each author becomes its own ``AutorIn`` parameter.
    """
    authors = loader.get_relations_by_type(text_entity["ID"], "AUTHORS")
    return [
        loader.entities[rel["relTar"]]["appellation"]
        for rel in authors
        if rel.get("relTar") in loader.entities
        and loader.entities[rel["relTar"]].get("appellation")
    ]


def get_ort(text_entity: Dict) -> Optional[str]:
    """Return the location of *text_entity*: the title before the first comma.

    Returns ``None`` when the entity has no title or an empty location part.
    """
    appellation = text_entity.get("appellation")
    if not appellation:
        return None
    ort = appellation.split(",", 1)[0].strip()
    return ort or None


def get_building(loader: DataLoader, text_entity: Dict) -> Optional[Dict]:
    """Return the building documented by *text_entity*.

    A TEXT entity reaches its physical object through ``DOCUMENTS`` relations.
    Most point at an ``OBJECT_BUILDING``; a handful describe an
    ``OBJECT_ENSEMBLE`` instead. Both carry the same address, location and
    function fields (the ensemble simply lacks the building-only ones such as
    ``moduleNumber`` and ``buildingInventoryNumber``), so an ``OBJECT_BUILDING``
    is preferred but an ``OBJECT_ENSEMBLE`` is accepted as a fallback. Returns
    ``None`` when no such object is documented.
    """
    fallback: Optional[Dict] = None
    for rel in loader.get_relations_by_type(text_entity["ID"], "DOCUMENTS"):
        obj = loader.entities.get(rel.get("relTar"))
        if not obj:
            continue
        if obj.get("sType") == "OBJECT_BUILDING":
            return obj
        if obj.get("sType") == "OBJECT_ENSEMBLE" and fallback is None:
            fallback = obj
    return fallback


def _building_lines(building: Dict) -> List[str]:
    """Return the ``{{Artikel-modern}}`` parameter lines for *building*.

    Each address/location field is emitted only when present. ``functions`` is
    an array and is spread across numbered ``Funktion1``, ``Funktion2`` …
    parameters, mirroring how authors are handled.
    """
    lines: List[str] = []
    simple_params = [
        ("Bundesland", "addressState"),
        ("Gemeinde", "addressLocality"),
        ("PLZ", "addressZip"),
        ("Strasse", "addressStreet"),
        ("Lat", "locationLat"),
        ("Lng", "locationLng"),
        ("Modul", "moduleNumber"),
        ("Inventarnummer", "buildingInventoryNumber"),
    ]
    for param, key in simple_params:
        value = building.get(key)
        if value is not None and value != "":
            lines.append(f"| {param} = {value}")

    for i, function in enumerate(building.get("functions") or [], start=1):
        lines.append(f"| Funktion{i} = {function}")

    return lines


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

    Address, location and function data are read from the ``OBJECT_BUILDING``
    (or ``OBJECT_ENSEMBLE``) the text documents and passed through as further
    parameters; the template turns ``Bundesland`` and ``Modul`` into categories
    and renders ``Inventarnummer`` and an OpenStreetMap link from the
    coordinates.
    """
    lines = ["{{Artikel-modern"]

    names = get_author_names(loader, text_entity)
    for i, name in enumerate(names, start=1):
        lines.append(f"| AutorIn{i} = {name}")

    appellation = text_entity.get("appellation")
    if appellation:
        lines.append(f"| Titel = {appellation}")
        ort = get_ort(text_entity)
        if ort:
            lines.append(f"| Ort = {ort}")

    year = _modification_year(text_entity)
    if year:
        lines.append(f"| Jahr = {year}")

    if text_entity.get("ID"):
        lines.append(f"| ID = {text_entity['ID']}")

    building = get_building(loader, text_entity)
    if building:
        lines.extend(_building_lines(building))

    lines.append("}}")
    return "\n".join(lines)
