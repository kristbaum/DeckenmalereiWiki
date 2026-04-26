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

    def get_lead_resource_via_documents(
        self, entity_id: str
    ) -> tuple[str, Optional[Dict]]:
        """Return ``(name_entity_id, resource)`` for the lead resource.

        Tries the LEAD_RESOURCE relation directly on *entity_id* first; if
        absent, follows DOCUMENTS to the first OBJECT_* entity that carries a
        LEAD_RESOURCE.  ``name_entity_id`` is the entity whose ID should be
        used as the MediaWiki filename (``{name_entity_id}.jpg``).
        """
        lead = self.get_lead_resource(entity_id)
        if lead:
            return entity_id, lead
        for doc_rel in self.get_relations_by_type(entity_id, "DOCUMENTS"):
            object_id = doc_rel.get("relTar")
            if object_id:
                lead = self.get_lead_resource(object_id)
                if lead:
                    return object_id, lead
        return entity_id, None

    def get_images(self, entity_id: str) -> List[Dict]:
        """Get all IMAGE resources for an entity.

        IMAGE relations are stored on OBJECT_* entities, not directly on TEXT or
        TEXT_PART entities.  This method follows the DOCUMENTS relation from
        *entity_id* to the linked OBJECT_* entities and then collects every
        IMAGE resource attached to those objects.
        """
        seen: set = set()
        images = []
        # Follow DOCUMENTS relations to reach the underlying OBJECT_* entities
        document_rels = self.get_relations_by_type(entity_id, "DOCUMENTS")
        for doc_rel in document_rels:
            object_id = doc_rel.get("relTar")
            if not object_id:
                continue
            image_rels = self.get_relations_by_type(object_id, "IMAGE")
            for rel in image_rels:
                resource_id = rel.get("relTar")
                if resource_id in self.resources and resource_id not in seen:
                    seen.add(resource_id)
                    images.append(self.resources[resource_id])
        return images

    def get_resource_actors(self, resource_id: str, rel_type: str) -> List[str]:
        """Return a list of entity appellations linked to *resource_id* via *rel_type*.

        Args:
            resource_id: The ID of a resource (from resources.json).
            rel_type:    Relation type to follow, e.g. ``'RIGHTS_HOLDERS'`` or
                         ``'ORIGINATORS'``.

        Returns:
            List of appellation strings; falls back to the raw entity ID when
            the entity is not found in the loaded set.
        """
        result = []
        for rel in self.get_relations_by_type(resource_id, rel_type):
            target_id = rel.get("relTar", "")
            entity = self.entities.get(target_id)
            if entity and entity.get("appellation"):
                result.append(entity["appellation"])
        return result
