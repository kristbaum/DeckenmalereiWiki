"""
Data loading and entity queries for DeckenmalereiWiki JSON sources.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict


class DataLoader:
    """Loads and queries DeckenmalereiWiki JSON data."""

    def __init__(self, sources_dir: str = "sources"):
        self.sources_dir = Path(sources_dir)
        self.entities: Dict[str, Dict] = {}
        self.relations: List[Dict] = []
        self.resources: Dict[str, Dict] = {}
        self.relations_by_source: Dict[str, List[Dict]] = defaultdict(list)

    def load_data(self):
        """Load all JSON files from sources directory."""
        print("Loading entities...")
        with open(self.sources_dir / "entities.json", "r", encoding="utf-8") as f:
            entities_list = json.load(f)
            self.entities = {e["ID"]: e for e in entities_list}
        print(f"Loaded {len(self.entities)} entities")

        print("Loading relations...")
        with open(self.sources_dir / "relations.json", "r", encoding="utf-8") as f:
            self.relations = json.load(f)
        print(f"Loaded {len(self.relations)} relations")

        for rel in self.relations:
            if rel.get("relDir") == "->":
                self.relations_by_source[rel["ID"]].append(rel)

        print("Loading resources...")
        with open(self.sources_dir / "resources.json", "r", encoding="utf-8") as f:
            resources_list = json.load(f)
            self.resources = {r["ID"]: r for r in resources_list}
        print(f"Loaded {len(self.resources)} resources")

    def get_text_entities(self) -> List[Dict]:
        """Get all TEXT type entities."""
        return [e for e in self.entities.values() if e.get("sType") == "TEXT"]

    def get_relations_by_type(self, entity_id: str, rel_type: str) -> List[Dict]:
        """Get all outgoing relations of a specific type for an entity."""
        return [
            r
            for r in self.relations_by_source.get(entity_id, [])
            if r.get("sType") == rel_type
        ]

    def get_text_parts(self, text_entity_id: str) -> List[Dict]:
        """Get all TEXT_PART entities for a TEXT entity, ordered by relOrd.
        Recursively collects nested TEXT_PART entities."""

        def collect_parts_recursive(entity_id: str) -> List[Dict]:
            part_relations = self.get_relations_by_type(entity_id, "PART")
            part_relations.sort(key=lambda r: r.get("relOrd", 0))

            parts = []
            for rel in part_relations:
                target_id = rel.get("relTar")
                if target_id in self.entities:
                    parts.append(self.entities[target_id])
                    sub_parts = collect_parts_recursive(target_id)
                    parts.extend(sub_parts)
            return parts

        return collect_parts_recursive(text_entity_id)

    def get_lead_resource(self, entity_id: str) -> Optional[Dict]:
        """Get the LEAD_RESOURCE for an entity."""
        lead_rels = self.get_relations_by_type(entity_id, "LEAD_RESOURCE")
        if lead_rels:
            resource_id: str = lead_rels[0].get("relTar", "")
            return self.resources.get(resource_id)
        return None

    def get_images(self, entity_id: str) -> List[Dict]:
        """Get all IMAGE resources for an entity."""
        image_rels = self.get_relations_by_type(entity_id, "IMAGE")
        images = []
        for rel in image_rels:
            resource_id = rel.get("relTar")
            if resource_id in self.resources:
                images.append(self.resources[resource_id])
        return images


# Backward-compatible alias
DeckenmalereiParser = DataLoader
