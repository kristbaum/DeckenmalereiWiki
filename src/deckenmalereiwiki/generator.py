"""
Article and infobox generator for DeckenmalereiWiki.
Combines DataLoader, HtmlConverter, and citation helpers to produce
ready-to-import MediaWiki wikitext.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

from .loader import DataLoader
from .converter import HtmlConverter
from .citations import parse_citations, replace_citation_refs


class ArticleGenerator:
    """Generates MediaWiki articles from loaded source data."""

    def __init__(self, loader: DataLoader):
        self.loader = loader
        self.converter = HtmlConverter()

    # ------------------------------------------------------------------
    # Infobox
    # ------------------------------------------------------------------

    def generate_infobox(self, text_entity: Dict) -> str:
        """Build the ``{{Infobox Deckenmalerei}}`` wikitext block."""
        lines = ["{{Infobox Deckenmalerei"]

        if text_entity.get("appellation"):
            lines.append(f"| titel = {text_entity['appellation']}")

        if text_entity.get("shortText"):
            lines.append(f"| beschreibung = {text_entity['shortText']}")

        lead_resource = self.loader.get_lead_resource(text_entity["ID"])
        if lead_resource and lead_resource.get("resProvider"):
            image_name = f"Deckenmalerei_{text_entity['ID']}.jpg"
            lines.append(f"| bild = {image_name}")
            if lead_resource.get("resLicense"):
                lines.append(f"| lizenz = {lead_resource['resLicense']}")

        for rel_type in ["AUTHORS", "PAINTERS", "ARCHITECTS", "COMMISSIONERS"]:
            related = self.loader.get_relations_by_type(text_entity["ID"], rel_type)
            if related:
                names = [
                    self.loader.entities[rel["relTar"]]["appellation"]
                    for rel in related
                    if rel.get("relTar") in self.loader.entities
                    and self.loader.entities[rel["relTar"]].get("appellation")
                ]
                if names:
                    label = rel_type.lower().rstrip("s")
                    lines.append(f"| {label} = {', '.join(names)}")

        if text_entity.get("ID"):
            lines.append(f"| entity_id = {text_entity['ID']}")

        lines.append("}}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Article
    # ------------------------------------------------------------------

    def generate_article(self, text_entity: Dict) -> str:
        """Generate a complete MediaWiki article for *text_entity*."""
        parts_out: List[str] = []

        parts_out.append(self.generate_infobox(text_entity))
        parts_out.append("")

        if text_entity.get("shortText"):
            parts_out.append(text_entity["shortText"])
            parts_out.append("")

        # --- First pass: collect citations from all text parts ---
        text_parts = self.loader.get_text_parts(text_entity["ID"])
        all_citations: Dict[str, str] = {}
        part_texts: Dict[str, str] = {}

        for part in text_parts:
            if part.get("text"):
                cleaned, citations = parse_citations(part["text"], part["ID"])
                part_texts[part["ID"]] = cleaned
                all_citations.update(citations)

        # Deduplicate citations by content; map duplicates to canonical name
        citation_text_to_name: Dict[str, str] = {}
        ref_name_mapping: Dict[str, str] = {}

        for ref_name, citation_text in all_citations.items():
            if citation_text in citation_text_to_name:
                ref_name_mapping[ref_name] = citation_text_to_name[citation_text]
            else:
                citation_text_to_name[citation_text] = ref_name
                ref_name_mapping[ref_name] = ref_name

        deduplicated_citations = {
            canonical: text for text, canonical in citation_text_to_name.items()
        }

        # --- Second pass: emit article sections ---
        used_refs: Dict[str, bool] = {}

        for part in text_parts:
            if part.get("appellation"):
                parts_out.append(f"== {part['appellation']} ==")
                parts_out.append("")

            part_lead = self.loader.get_lead_resource(part["ID"])
            if part_lead and part_lead.get("resProvider"):
                image_name = f"Deckenmalerei_{part['ID']}.jpg"
                caption = part_lead.get("appellation", "")
                parts_out.append(f"[[File:{image_name}|thumb|{caption}]]")
                parts_out.append("")

            if part.get("text") and part["ID"] in part_texts:
                text = replace_citation_refs(
                    part_texts[part["ID"]],
                    part["ID"],
                    deduplicated_citations,
                    used_refs,
                    ref_name_mapping,
                )
                parts_out.append(self.converter.convert(text))
                parts_out.append("")

            part_images = self.loader.get_images(part["ID"])
            if part_images:
                parts_out.append("<gallery>")
                for img in part_images:
                    img_name = f"Deckenmalerei_{img['ID']}.jpg"
                    parts_out.append(f"File:{img_name}|{img.get('appellation', '')}")
                parts_out.append("</gallery>")
                parts_out.append("")

        if text_entity.get("bibliography"):
            parts_out.append("== Bibliographie ==")
            bibliography_text = self.converter.convert(text_entity["bibliography"])
            # Add bullet points before each non-empty line
            lines = bibliography_text.split("\n")
            bulleted_lines = ["* " + line if line.strip() else line for line in lines]
            parts_out.append("\n".join(bulleted_lines))
            parts_out.append("")

        return "\n".join(parts_out)

    # ------------------------------------------------------------------
    # Batch generation
    # ------------------------------------------------------------------

    def generate_all_articles(
        self, max_articles: Optional[int] = None
    ) -> Dict[str, str]:
        """Generate all (or up to *max_articles*) articles.

        Returns:
            ``{title: wikitext}`` mapping.
        """
        text_entities = self.loader.get_text_entities()
        if max_articles:
            text_entities = text_entities[:max_articles]

        print(f"\nGenerating {len(text_entities)} articles...")
        articles: Dict[str, str] = {}
        for entity in text_entities:
            title = entity.get("appellation", f"Untitled_{entity['ID']}")
            articles[title] = self.generate_article(entity)
            print(f"  Generated: {title}")

        return articles

    def save_articles_to_files(
        self, output_dir: str = "output", max_articles: Optional[int] = 10
    ):
        """Save generated articles as individual ``.wiki`` files.

        Args:
            output_dir:   Directory to write files into (created if absent).
            max_articles: Optional cap on the number of articles to process.
        """
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        articles = self.generate_all_articles(max_articles=max_articles)

        for title, content in articles.items():
            safe_title = re.sub(r"[^\w\s,\-]", "", title).strip()
            safe_title = re.sub(r"[-\s]+", "_", safe_title)
            with open(output_path / f"{safe_title}.wiki", "w", encoding="utf-8") as f:
                f.write(content)

        print(f"\nSaved {len(articles)} articles to {output_dir}/")
