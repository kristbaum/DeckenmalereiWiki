"""Generates the ``{{Infobox Deckenmalerei}}`` wikitext block."""

from typing import Dict

from .loader import DataLoader


def generate_infobox(loader: DataLoader, text_entity: Dict) -> str:
    lines = ["{{Infobox Deckenmalerei"]

    if text_entity.get("appellation"):
        lines.append(f"| titel = {text_entity['appellation']}")

    if text_entity.get("shortText"):
        lines.append(f"| beschreibung = {text_entity['shortText']}")

    lead_entity_id, lead_resource = loader.get_lead_resource_via_documents(
        text_entity["ID"]
    )
    if lead_resource and lead_resource.get("resProvider"):
        image_name = f"{lead_entity_id}.jpg"
        lines.append(f"| bild = {image_name}")
        if lead_resource.get("resLicense"):
            lines.append(f"| lizenz = {lead_resource['resLicense']}")

    for rel_type in ["AUTHORS", "PAINTERS", "ARCHITECTS", "COMMISSIONERS"]:
        related = loader.get_relations_by_type(text_entity["ID"], rel_type)
        if related:
            names = [
                loader.entities[rel["relTar"]]["appellation"]
                for rel in related
                if rel.get("relTar") in loader.entities
                and loader.entities[rel["relTar"]].get("appellation")
            ]
            if names:
                label = rel_type.lower().rstrip("s")
                lines.append(f"| {label} = {'; '.join(names)}")

    if text_entity.get("ID"):
        lines.append(f"| entity_id = {text_entity['ID']}")

    lines.append("}}")
    return "\n".join(lines)
