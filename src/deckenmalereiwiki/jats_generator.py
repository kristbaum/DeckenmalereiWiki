"""
JATS XML article generator for DeckenmalereiWiki.

The JATS counterpart of :mod:`~deckenmalereiwiki.generator`: it reuses the same
:class:`~deckenmalereiwiki.loader.DataLoader` data and the same article
structure (front matter, body sections, figures, citations, bibliography) but
emits `JATS <https://jats.nlm.nih.gov/>`_ XML instead of MediaWiki wikitext.

The mapping is:

==========================  =====================================
parse pipeline (wikitext)   JATS output
==========================  =====================================
``{{Artikel-modern}}``      ``<front>`` (authors, title, year, id)
``shortText``               ``<abstract>``
text parts + headings       ``<body>`` ``<sec>``/``<title>``
``{{Strukturdaten}}``       ``<sec-meta><custom-meta-group>``
``[[File:…]]`` / galleries  ``<fig>`` / ``<fig-group>`` ``<graphic>``
``<ref>`` citations         ``<back><ref-list>`` + inline ``<xref>``
``== Bibliographie ==``     ``<back><sec sec-type="bibliography">``
==========================  =====================================
"""

import re
from pathlib import Path
from typing import Dict, List, Optional
from xml.sax.saxutils import escape, quoteattr

from .loader import DataLoader
from .jats_converter import JatsConverter
from .citations import parse_citations
from .strukturdaten import load_wikidata_mapping
from .artikel_modern import get_author_names, _modification_year
from .image_handler import ImageHandler
from .generator import title_to_filename


def _ref_rid(ref_name: str) -> str:
    """Return a valid XML id for a citation ref name."""
    return "ref-" + re.sub(r"[^\w.-]", "_", ref_name)


class JatsArticleGenerator:
    """Generates JATS XML articles from loaded source data."""

    def __init__(self, loader: DataLoader):
        self.loader = loader
        self.converter = JatsConverter()
        self.wikidata_mapping = load_wikidata_mapping(str(loader.sources_dir))
        # Same offline image handler as the wikitext generator: resolves the
        # File: names without querying any provider API.
        self.image_handler = ImageHandler(
            site=None, downloads_dir=Path("downloads"), offline=True
        )

    # ------------------------------------------------------------------
    # Image helpers
    # ------------------------------------------------------------------

    def _graphic_href(self, entity_id: str, resource: Dict) -> str:
        """Return the ``xlink:href`` for *resource*'s ``<graphic>``.

        Uploaded resources reference the resolved ``File:`` filename; external
        (source-link-only) providers reference their original source URL.
        """
        provider = resource.get("resProvider", "")
        if self.image_handler.is_external(provider):
            return self.image_handler.source_url(provider, resource["ID"]) or ""
        return self.image_handler.image_filename(entity_id, provider, resource["ID"])

    def _fig(self, entity_id: str, resource: Dict, indent: str) -> str:
        """Render a single ``<fig>`` for *resource*."""
        href = self._graphic_href(entity_id, resource)
        caption = resource.get("appellation", "")
        lines = [f"{indent}<fig>"]
        if caption:
            lines.append(
                f"{indent}  <caption><p>{escape(caption)}</p></caption>"
            )
        lines.append(f"{indent}  <graphic xlink:href={quoteattr(href)}/>")
        lines.append(f"{indent}</fig>")
        return "\n".join(lines)

    def _figures(self, resources: List[tuple], indent: str) -> List[str]:
        """Render *resources* as a single ``<fig>`` or a ``<fig-group>``."""
        if not resources:
            return []
        if len(resources) == 1:
            entity_id, resource = resources[0]
            return [self._fig(entity_id, resource, indent)]
        out = [f"{indent}<fig-group>"]
        for entity_id, resource in resources:
            out.append(self._fig(entity_id, resource, indent + "  "))
        out.append(f"{indent}</fig-group>")
        return out

    # ------------------------------------------------------------------
    # Citation helpers
    # ------------------------------------------------------------------

    def _replace_citation_xrefs(
        self,
        text: str,
        part_id: str,
        valid_refs: Dict[str, str],
        ref_name_mapping: Dict[str, str],
    ) -> str:
        """Replace ``[x]`` markers with JATS ``<xref>`` elements.

        Every occurrence points at the deduplicated reference's ``rid``; the
        bibliographic content lives once in the ``<ref-list>`` in ``<back>``.
        """

        def replace(match):
            num = match.group(1)
            original = f"{part_id}_{num}"
            name = ref_name_mapping.get(original, original)
            if name not in valid_refs:
                return match.group(0)
            rid = _ref_rid(name)
            return f'<xref ref-type="bibr" rid="{rid}">[{num}]</xref>'

        return re.sub(r"(?<!^)\[(\d+)\]", replace, text, flags=re.MULTILINE)

    # ------------------------------------------------------------------
    # Article
    # ------------------------------------------------------------------

    def _front(self, text_entity: Dict) -> List[str]:
        """Build the ``<front>`` element (title, authors, date, id, abstract)."""
        title = text_entity.get("appellation") or f"Untitled {text_entity['ID']}"
        out = [
            "  <front>",
            "    <article-meta>",
            f"      <article-id pub-id-type=\"other\">{escape(text_entity['ID'])}</article-id>",
            "      <title-group>",
            f"        <article-title>{escape(title)}</article-title>",
            "      </title-group>",
        ]

        names = get_author_names(self.loader, text_entity)
        if names:
            out.append('      <contrib-group>')
            for name in names:
                out.append('        <contrib contrib-type="author">')
                out.append(f"          <string-name>{escape(name)}</string-name>")
                out.append("        </contrib>")
            out.append("      </contrib-group>")

        year = _modification_year(text_entity)
        if year:
            out.append('      <pub-date date-type="pub">')
            out.append(f"        <year>{escape(year)}</year>")
            out.append("      </pub-date>")

        short_text = text_entity.get("shortText")
        if short_text:
            body = self.converter.convert(short_text)
            out.append("      <abstract>")
            out.append(self._indent(body, "        "))
            out.append("      </abstract>")

        out.append("    </article-meta>")
        out.append("  </front>")
        return out

    @staticmethod
    def _indent(block: str, indent: str) -> str:
        """Indent every non-empty line of *block* by *indent*."""
        return "\n".join(indent + line if line else line for line in block.split("\n"))

    def generate_article(self, text_entity: Dict) -> str:
        """Generate a complete JATS XML article for *text_entity*."""
        body: List[str] = ["  <body>"]

        # Lead image for the whole article.
        lead_entity_id, lead = self.loader.get_lead_resource_via_documents(
            text_entity["ID"]
        )
        if lead and lead.get("resProvider"):
            body.extend(self._figures([(lead_entity_id, lead)], "    "))

        # --- First pass: collect and deduplicate citations ---
        text_parts = self.loader.get_text_parts(text_entity["ID"])
        all_citations: Dict[str, str] = {}
        part_texts: Dict[str, str] = {}
        for part in text_parts:
            if part.get("text"):
                cleaned, citations = parse_citations(part["text"], part["ID"])
                part_texts[part["ID"]] = cleaned
                all_citations.update(citations)
            else:
                part_texts[part["ID"]] = ""

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

        # --- Second pass: emit body sections ---
        for part in text_parts:
            body.append("    <sec>")

            documented_id = self.loader.get_documented_entity_id(part["ID"])
            if documented_id:
                qid = self.wikidata_mapping.get(documented_id)
                body.extend(self._strukturdaten(documented_id, qid))

            appellation = part.get("appellation", "")
            if appellation:
                body.append(f"      <title>{escape(appellation)}</title>")

            # Per-part figures: lead resource first, then IMAGE resources.
            part_lead_entity_id, part_lead = self.loader.get_lead_resource_via_documents(
                part["ID"]
            )
            resources: List[tuple] = []
            if part_lead and part_lead.get("resProvider"):
                resources.append((part_lead_entity_id, part_lead))
            for img in self.loader.get_images(part["ID"]):
                resources.append((img["ID"], img))
            body.extend(self._figures(resources, "      "))

            text = self._replace_citation_xrefs(
                part_texts[part["ID"]],
                part["ID"],
                deduplicated_citations,
                ref_name_mapping,
            )
            converted = self.converter.convert(text)
            if converted:
                body.append(self._indent(converted, "      "))

            body.append("    </sec>")
        body.append("  </body>")

        back = self._back(text_entity, deduplicated_citations)

        out = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            "<article "
            'xmlns:xlink="http://www.w3.org/1999/xlink" '
            'article-type="research-article" dtd-version="1.3">',
        ]
        out.extend(self._front(text_entity))
        out.extend(body)
        out.extend(back)
        out.append("</article>")
        return "\n".join(out)

    def _strukturdaten(self, entity_id: str, qid: Optional[str]) -> List[str]:
        """Render structural data as a section-level ``<custom-meta-group>``."""
        out = [
            "      <sec-meta>",
            "        <custom-meta-group>",
            "          <custom-meta>",
            "            <meta-name>entity_id</meta-name>",
            f"            <meta-value>{escape(entity_id)}</meta-value>",
            "          </custom-meta>",
        ]
        if qid:
            out.extend(
                [
                    "          <custom-meta>",
                    "            <meta-name>wikidata_qid</meta-name>",
                    f"            <meta-value>{escape(qid)}</meta-value>",
                    "          </custom-meta>",
                ]
            )
        out.append("        </custom-meta-group>")
        out.append("      </sec-meta>")
        return out

    def _back(
        self, text_entity: Dict, deduplicated_citations: Dict[str, str]
    ) -> List[str]:
        """Build ``<back>`` with the reference list and bibliography section."""
        sections: List[str] = []

        if deduplicated_citations:
            ref_list = ["    <ref-list>", "      <title>Einzelnachweise</title>"]
            for ref_name, citation_text in deduplicated_citations.items():
                rid = _ref_rid(ref_name)
                content = self.converter.convert_inline(citation_text)
                ref_list.append(f'      <ref id="{rid}">')
                ref_list.append(f"        <mixed-citation>{content}</mixed-citation>")
                ref_list.append("      </ref>")
            ref_list.append("    </ref-list>")
            sections.extend(ref_list)

        bibliography = text_entity.get("bibliography")
        if bibliography:
            # Bibliography is newline-separated entries (matching the bullet
            # list the wikitext pipeline builds); one <list-item> per entry.
            items = [
                self.converter.convert_inline(line)
                for line in bibliography.split("\n")
                if line.strip()
            ]
            sec = [
                '    <sec sec-type="bibliography">',
                "      <title>Bibliographie</title>",
                '      <list list-type="bullet">',
            ]
            for item in items:
                sec.append(f"        <list-item><p>{item}</p></list-item>")
            sec.append("      </list>")
            sec.append("    </sec>")
            sections.extend(sec)

        if not sections:
            return []
        return ["  <back>", *sections, "  </back>"]

    # ------------------------------------------------------------------
    # Batch generation
    # ------------------------------------------------------------------

    def save_articles_to_files(
        self, output_dir: str = "output_jats", max_articles: Optional[int] = 500000
    ):
        """Save generated articles as individual ``.xml`` files.

        Mirrors :meth:`ArticleGenerator.save_articles_to_files`: each article is
        written immediately after generation so progress survives later errors.

        Args:
            output_dir:   Directory to write files into (created if absent).
            max_articles: Optional cap on the number of articles to process.
        """
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        text_entities = self.loader.get_text_entities()
        if max_articles:
            text_entities = text_entities[:max_articles]

        print(f"\nGenerating {len(text_entities)} JATS articles...")
        saved = 0
        for entity in text_entities:
            title = entity.get("appellation", f"Untitled_{entity['ID']}")
            try:
                content = self.generate_article(entity)
            except Exception as e:
                print(f"  ERROR generating '{title}': {e}")
                continue
            safe_title = title_to_filename(title)
            with open(output_path / f"{safe_title}.xml", "w", encoding="utf-8") as f:
                f.write(content)
            saved += 1
            print(f"  Generated: {title}")

        print(f"\nSaved {saved} JATS articles to {output_dir}/")
