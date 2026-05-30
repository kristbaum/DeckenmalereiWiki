"""
Generator for the {{Strukturdaten}} MediaWiki template.
"""

import csv
from pathlib import Path
from typing import Optional


def load_wikidata_mapping(sources_dir: str = "sources") -> dict:
    """Return a UUID → Wikidata QID mapping loaded from query.csv."""
    mapping = {}
    csv_path = Path(sources_dir) / "query.csv"
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            item_url = row.get("item", "")
            uuid = row.get("deckenmalerei_eu_ID", "").strip()
            if item_url and uuid:
                qid = item_url.rstrip("/").split("/")[-1]
                mapping[uuid] = qid
    return mapping


def generate_strukturdaten(
    deckenmalerei_eu_id: str,
    wikidata_qid: Optional[str] = None,
) -> str:
    """Return the ``{{Strukturdaten}}`` wikitext for a section."""
    params = [f"deckenmalerei.eu_id={deckenmalerei_eu_id}"]
    if wikidata_qid:
        params.append(f"wikidata_qid={wikidata_qid}")
    return "{{Strukturdaten|" + "|".join(params) + "}}"
