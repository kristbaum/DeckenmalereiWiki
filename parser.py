"""
DeckenmalereiWiki Parser
Parses JSON data from sources/ to generate MediaWiki articles.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict


class DeckenmalereiParser:
    """Parser for DeckenmalereiWiki JSON data."""

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

        # Index relations by source ID for faster lookup
        for rel in self.relations:
            if rel.get("relDir") == "->":  # Only outgoing relations
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
            """Recursively collect parts and their sub-parts."""
            part_relations = self.get_relations_by_type(entity_id, "PART")
            # Sort by relOrd
            part_relations.sort(key=lambda r: r.get("relOrd", 0))

            parts = []
            for rel in part_relations:
                target_id = rel.get("relTar")
                if target_id in self.entities:
                    # Add the current part
                    parts.append(self.entities[target_id])
                    # Recursively collect sub-parts
                    sub_parts = collect_parts_recursive(target_id)
                    parts.extend(sub_parts)
            return parts

        return collect_parts_recursive(text_entity_id)

    def get_lead_resource(self, entity_id: str) -> Optional[Dict]:
        """Get the LEAD_RESOURCE for an entity."""
        lead_rels = self.get_relations_by_type(entity_id, "LEAD_RESOURCE")
        if lead_rels:
            resource_id = lead_rels[0].get("relTar")
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

    def html_to_mediawiki(self, html: str) -> str:
        """Convert HTML markup to MediaWiki syntax."""
        if not html:
            return ""

        text = html

        # Headers
        text = re.sub(r"<h1>(.*?)</h1>", r"= \1 =\n", text, flags=re.DOTALL)
        text = re.sub(r"<h2>(.*?)</h2>", r"== \1 ==\n", text, flags=re.DOTALL)
        text = re.sub(r"<h3>(.*?)</h3>", r"=== \1 ===\n", text, flags=re.DOTALL)
        text = re.sub(r"<h4>(.*?)</h4>", r"==== \1 ====\n", text, flags=re.DOTALL)

        # Bold and italic
        text = re.sub(
            r"<strong>(.*?)</strong>", r"\1", text, flags=re.DOTALL
        )  # Only gets added to headings, not needed for mediawiki
        text = re.sub(r"<b>(.*?)</b>", r"'''\1'''", text, flags=re.DOTALL)
        text = re.sub(r"<em>(.*?)</em>", r"''\1''", text, flags=re.DOTALL)
        text = re.sub(r"<i>(.*?)</i>", r"''\1''", text, flags=re.DOTALL)

        # Underline (MediaWiki doesn't have native underline, use HTML)
        # text = re.sub(r'<u>(.*?)</u>', r'<u>\1</u>', text, flags=re.DOTALL)

        # Paragraphs
        text = re.sub(r"<p>(.*?)</p>", r"\1\n\n", text, flags=re.DOTALL)

        # Line breaks
        text = re.sub(r"<br\s*/?>", "\n", text)

        # Lists
        text = re.sub(
            r"<ul>(.*?)</ul>",
            lambda m: self._convert_list(m.group(1), "*"),
            text,
            flags=re.DOTALL,
        )
        text = re.sub(
            r"<ol>(.*?)</ol>",
            lambda m: self._convert_list(m.group(1), "#"),
            text,
            flags=re.DOTALL,
        )

        # Links (basic conversion)
        text = re.sub(
            r'<a\s+href=["\']([^"\']+)["\']>(.*?)</a>',
            r"[\1 \2]",
            text,
            flags=re.DOTALL,
        )

        # Clean up excessive newlines
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def _convert_list(self, list_content: str, marker: str) -> str:
        """Convert HTML list items to MediaWiki format."""
        items = re.findall(r"<li>(.*?)</li>", list_content, flags=re.DOTALL)
        return "\n".join(f"{marker} {item.strip()}" for item in items) + "\n\n"

    def generate_infobox(self, text_entity: Dict) -> str:
        """Generate MediaWiki infobox from entity metadata."""
        infobox_lines = ["{{Infobox Deckenmalerei"]

        # Title
        if text_entity.get("appellation"):
            infobox_lines.append(f"| titel = {text_entity['appellation']}")

        # Short description
        if text_entity.get("shortText"):
            infobox_lines.append(f"| beschreibung = {text_entity['shortText']}")

        # Lead image
        lead_resource = self.get_lead_resource(text_entity["ID"])
        if lead_resource and lead_resource.get("resProvider"):
            # Extract filename from URL or use ID
            image_name = f"Deckenmalerei_{text_entity['ID']}.jpg"
            infobox_lines.append(f"| bild = {image_name}")
            if lead_resource.get("resLicense"):
                infobox_lines.append(f"| lizenz = {lead_resource['resLicense']}")

        # Related persons
        for rel_type in ["AUTHORS", "PAINTERS", "ARCHITECTS", "COMMISSIONERS"]:
            related = self.get_relations_by_type(text_entity["ID"], rel_type)
            if related:
                names = []
                for rel in related:
                    target_entity = self.entities.get(rel.get("relTar"))
                    if target_entity and target_entity.get("appellation"):
                        names.append(target_entity["appellation"])
                if names:
                    label = rel_type.lower().rstrip("s")
                    infobox_lines.append(f"| {label} = {', '.join(names)}")

        # Source ID (template will construct URL)
        if text_entity.get("ID"):
            infobox_lines.append(f"| entity_id = {text_entity['ID']}")

        infobox_lines.append("}}")
        return "\n".join(infobox_lines)

    def generate_article(self, text_entity: Dict) -> str:
        """Generate complete MediaWiki article from TEXT entity."""
        article_parts = []

        # Add infobox
        infobox = self.generate_infobox(text_entity)
        article_parts.append(infobox)
        article_parts.append("")  # Empty line after infobox

        # Add introduction from shortText if available
        if text_entity.get("shortText"):
            article_parts.append(text_entity["shortText"])
            article_parts.append("")

        # Get and combine all text parts
        text_parts = self.get_text_parts(text_entity["ID"])
        for part in text_parts:
            # Add section header from TEXT_PART appellation
            if part.get("appellation"):
                article_parts.append(f"= {part['appellation']} =")
                article_parts.append("")

            # Add lead resource image for this text part (standalone)
            part_lead_resource = self.get_lead_resource(part["ID"])
            if part_lead_resource and part_lead_resource.get("resProvider"):
                image_name = f"Deckenmalerei_{part['ID']}.jpg"
                caption = part_lead_resource.get("appellation", "")
                article_parts.append(f"[[File:{image_name}|thumb|{caption}]]")
                article_parts.append("")

            if part.get("text"):
                converted_text = self.html_to_mediawiki(part["text"])
                article_parts.append(converted_text)
                article_parts.append("")  # Empty line between sections

            # Add image gallery for this text part
            part_images = self.get_images(part["ID"])
            if part_images:
                article_parts.append("<gallery>")
                for img in part_images:
                    img_name = f"Deckenmalerei_{img['ID']}.jpg"
                    img_caption = img.get("appellation", "")
                    article_parts.append(f"File:{img_name}|{img_caption}")
                article_parts.append("</gallery>")
                article_parts.append("")

        # Add bibliography if available
        if text_entity.get("bibliography"):
            article_parts.append("== Literatur ==")
            article_parts.append(self.html_to_mediawiki(text_entity["bibliography"]))
            article_parts.append("")

        return "\n".join(article_parts)

    def generate_all_articles(
        self, max_articles: Optional[int] = None
    ) -> Dict[str, str]:
        """Generate all articles as a dictionary {title: content}.

        Args:
            max_articles: Optional limit on number of articles to generate.
        """
        articles = {}
        text_entities = self.get_text_entities()
        if max_articles:
            text_entities = text_entities[:max_articles]

        print(f"\nGenerating {len(text_entities)} articles...")
        for entity in text_entities:
            title = entity.get("appellation", f"Untitled_{entity['ID']}")
            content = self.generate_article(entity)
            articles[title] = content
            print(f"  Generated: {title}")

        return articles

    def save_articles_to_files(
        self, output_dir: str = "output", max_articles: Optional[int] = None
    ):
        """Save generated articles as individual .wiki files.

        Args:
            max_articles: Optional limit on number of articles to generate.
        """
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        articles = self.generate_all_articles(max_articles=max_articles)

        for title, content in articles.items():
            # Create safe filename
            safe_title = re.sub(r"[^\w\s-]", "", title).strip()
            safe_title = re.sub(r"[-\s]+", "_", safe_title)
            filename = output_path / f"{safe_title}.wiki"

            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)

        print(f"\nSaved {len(articles)} articles to {output_dir}/")


def main():
    """Main entry point."""
    parser = DeckenmalereiParser()
    parser.load_data()

    # Generate and save articles
    parser.save_articles_to_files()

    print("\nDone!")


if __name__ == "__main__":
    main()
