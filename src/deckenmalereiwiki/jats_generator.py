"""
JATS XML article generator for DeckenmalereiWiki.

The JATS counterpart of :mod:`~deckenmalereiwiki.generator`: it reuses the same
:class:`~deckenmalereiwiki.loader.DataLoader` data and the same article
structure (front matter, body sections, figures, citations, bibliography) but
emits `JATS <https://jats.nlm.nih.gov/>`_ XML instead of MediaWiki wikitext.

The tagging style mirrors the target system's JATS dialect, taken from the
reference sample ``102976.xml`` (JATS Journal Publishing DTD 1.3). The notable
conventions copied from it:

* ``<article xml:lang="…">`` with a DOCTYPE and **no** root namespace; the
  ``xmlns:xlink`` namespace is declared inline on each ``<ext-link>``/
  ``<graphic>`` that needs it.
* Footnotes via ``<back><fn-group><fn id><label>N</label><p>…</p></fn>`` with
  inline ``<xref ref-type="fn" rid="…">N</xref>`` markers.
* ``<italic toggle="yes">``, ``<contrib contrib-type="aut">`` with a
  ``<name name-style="western">`` (surname/given-names), and figures rendered as
  ``<fig id><label><caption><p><graphic mimetype… specific-use="screen"/>``.
* Three-space indentation and ``id`` attributes on ``<sec>``/``<p>``/``<abstract>``.

Differences from the reference sample are documented inline at each call site
and summarised in the module's accompanying notes.
"""

import re
from itertools import count
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape, quoteattr

from .loader import DataLoader
from .jats_converter import JatsConverter, XLINK_NS
from .citations import parse_citations
from .strukturdaten import load_wikidata_mapping
from .artikel_modern import get_author_names, _modification_year
from .image_handler import ImageHandler
from .generator import title_to_filename

#: Three-space indentation unit, matching the reference sample.
IND = "   "

#: File-extension → MIME type for ``<graphic mimetype>``.
_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".gif": "image/gif",
}

#: DOCTYPE copied verbatim from the reference sample (JATS Publishing 1.3).
_DOCTYPE = (
    '<!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal Publishing DTD '
    'v1.3 20210610//EN" "https://jats.nlm.nih.gov/publishing/1.3/'
    'JATS-journalpublishing1-3-mathml3.dtd">'
)


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
    # Small helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _indent(block: str, level: int) -> str:
        """Indent every non-empty line of *block* by *level* units."""
        pad = IND * level
        return "\n".join(pad + line if line else line for line in block.split("\n"))

    # ------------------------------------------------------------------
    # Front matter
    # ------------------------------------------------------------------

    def _contrib_group(self, text_entity: Dict, level: int) -> List[str]:
        """Render ``<contrib-group>`` from the entity's authors.

        Author appellations are stored "Surname, Given"; that maps onto the
        sample's ``<name name-style="western"><surname>/<given-names>``. Names
        without a comma fall back to ``<string-name>``.
        """
        names = get_author_names(self.loader, text_entity)
        if not names:
            return []
        pad = IND * level
        out = [f"{pad}<contrib-group>"]
        for name in names:
            out.append(f'{pad}{IND}<contrib contrib-type="aut">')
            if "," in name:
                surname, given = (p.strip() for p in name.split(",", 1))
                out.append(f'{pad}{IND * 2}<name name-style="western">')
                out.append(f"{pad}{IND * 3}<surname>{escape(surname)}</surname>")
                if given:
                    out.append(
                        f"{pad}{IND * 3}<given-names>{escape(given)}</given-names>"
                    )
                out.append(f"{pad}{IND * 2}</name>")
            else:
                out.append(f"{pad}{IND * 2}<string-name>{escape(name)}</string-name>")
            out.append(f"{pad}{IND}</contrib>")
        out.append(f"{pad}</contrib-group>")
        return out

    def _front(self, text_entity: Dict) -> List[str]:
        """Build ``<front>`` (id, title, authors, date, abstract).

        Differences from the reference sample: there is no ``<journal-meta>``,
        ``<article-categories>``, ``<kwd-group>``, ``<permissions>`` or
        page/volume metadata (no source data for those); the article id is the
        Deckenmalerei UUID (``pub-id-type="other"``) rather than a DOI; and the
        publication date carries only ``<year>`` (the source has no full date).
        """
        title = text_entity.get("appellation") or f"Untitled {text_entity['ID']}"
        out = [
            f"{IND}<front>",
            f"{IND * 2}<article-meta>",
            f'{IND * 3}<article-id pub-id-type="other">{escape(text_entity["ID"])}</article-id>',
            f"{IND * 3}<title-group>",
            f"{IND * 4}<article-title>{escape(title)}</article-title>",
            f"{IND * 3}</title-group>",
        ]
        out.extend(self._contrib_group(text_entity, level=3))

        year = _modification_year(text_entity)
        if year:
            out.append(f"{IND * 3}<pub-date>")
            out.append(f"{IND * 4}<year>{escape(year)}</year>")
            out.append(f"{IND * 3}</pub-date>")

        short_text = text_entity.get("shortText")
        if short_text:
            body = self.converter.convert(short_text)
            out.append(f"{IND * 3}<abstract>")
            out.append(f"{IND * 4}<title><bold>Zusammenfassung</bold></title>")
            if body:
                out.append(self._indent(body, level=4))
            out.append(f"{IND * 3}</abstract>")

        out.append(f"{IND * 2}</article-meta>")
        out.append(f"{IND}</front>")
        return out

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------

    def _graphic_href(self, entity_id: str, resource: Dict) -> str:
        """Return the image filename for an uploaded *resource*."""
        return self.image_handler.image_filename(
            entity_id, resource.get("resProvider", ""), resource["ID"]
        )

    def _fig(
        self, entity_id: str, resource: Dict, fig_num: int, level: int
    ) -> List[str]:
        """Render a single ``<fig>`` for *resource*.

        External (source-link-only) providers have no downloadable binary, so
        instead of a ``<graphic>`` the figure carries the original link inside
        the caption. (The reference sample only shows uploaded ``<graphic>``
        figures; this is a Deckenmalerei-specific accommodation.)
        """
        pad = IND * level
        caption = resource.get("appellation", "")
        provider = resource.get("resProvider", "")
        external = self.image_handler.is_external(provider)

        out = [f'{pad}<fig id="fig_{fig_num}" position="float">']
        out.append(f"{pad}{IND}<label>[Abb. {fig_num}]</label>")

        if external:
            url = self.image_handler.source_url(provider, resource["ID"]) or ""
            link = (
                f'<ext-link xmlns:xlink="{XLINK_NS}" xlink:href={quoteattr(url)} '
                f'ext-link-type="uri" xlink:type="simple">{escape(url)}</ext-link>'
            )
            cap = escape(caption) + " " if caption else ""
            out.append(f"{pad}{IND}<caption>")
            out.append(f"{pad}{IND * 2}<p>{cap}(Quelle: {link})</p>")
            out.append(f"{pad}{IND}</caption>")
            out.append(f"{pad}</fig>")
            return out

        href = self._graphic_href(entity_id, resource)
        if caption:
            out.append(f"{pad}{IND}<caption>")
            out.append(f"{pad}{IND * 2}<p>{escape(caption)}</p>")
            out.append(f"{pad}{IND}</caption>")
        mimetype = _MIME.get(Path(href).suffix.lower())
        mime_attr = f' mimetype="{mimetype}"' if mimetype else ""
        out.append(
            f'{pad}{IND}<graphic xmlns:xlink="{XLINK_NS}"{mime_attr} '
            f'position="float" specific-use="screen" xlink:href={quoteattr(href)}/>'
        )
        out.append(f"{pad}</fig>")
        return out

    def _figures(
        self, resources: List[tuple], fig_counter: count, level: int
    ) -> List[str]:
        """Render *resources* as consecutive ``<fig>`` siblings."""
        out: List[str] = []
        for entity_id, resource in resources:
            out.extend(self._fig(entity_id, resource, next(fig_counter), level))
        return out

    # ------------------------------------------------------------------
    # Article body + back
    # ------------------------------------------------------------------

    def generate_article(self, text_entity: Dict) -> str:
        """Generate a complete JATS XML article for *text_entity*."""
        fig_counter = count(1)

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

        # Footnotes are numbered sequentially in order of first appearance in
        # the body text, mirroring the reference sample's <fn-group>.
        fn_registry: Dict[str, Tuple[int, str]] = {}
        fn_order: List[str] = []

        def footnote(canonical_name: str) -> Tuple[int, str]:
            if canonical_name not in fn_registry:
                number = len(fn_order) + 1
                fn_registry[canonical_name] = (number, f"fn{number}")
                fn_order.append(canonical_name)
            return fn_registry[canonical_name]

        def replace_refs(text: str, part_id: str) -> str:
            def repl(match):
                num = match.group(1)
                name = ref_name_mapping.get(f"{part_id}_{num}", f"{part_id}_{num}")
                if name not in deduplicated_citations:
                    return match.group(0)
                number, fn_id = footnote(name)
                return f'<xref ref-type="fn" rid="{fn_id}">{number}</xref>'

            return re.sub(r"(?<!^)\[(\d+)\]", repl, text, flags=re.MULTILINE)

        # --- Body ---
        body = [f"{IND}<body>"]

        lead_entity_id, lead = self.loader.get_lead_resource_via_documents(
            text_entity["ID"]
        )
        if lead and lead.get("resProvider"):
            body.extend(self._figures([(lead_entity_id, lead)], fig_counter, level=2))

        for part in text_parts:
            body.append(f"{IND * 2}<sec>")

            documented_id = self.loader.get_documented_entity_id(part["ID"])
            if documented_id:
                qid = self.wikidata_mapping.get(documented_id)
                body.extend(self._strukturdaten(documented_id, qid, level=3))

            appellation = part.get("appellation", "")
            if appellation:
                body.append(f"{IND * 3}<title>{escape(appellation)}</title>")

            part_lead_entity_id, part_lead = (
                self.loader.get_lead_resource_via_documents(part["ID"])
            )
            resources: List[tuple] = []
            if part_lead and part_lead.get("resProvider"):
                resources.append((part_lead_entity_id, part_lead))
            for img in self.loader.get_images(part["ID"]):
                resources.append((img["ID"], img))
            body.extend(self._figures(resources, fig_counter, level=3))

            text = replace_refs(part_texts[part["ID"]], part["ID"])
            converted = self.converter.convert(text)
            if converted:
                body.append(self._indent(converted, level=3))

            body.append(f"{IND * 2}</sec>")
        body.append(f"{IND}</body>")

        back = self._back(text_entity, deduplicated_citations, fn_registry, fn_order)

        out = [
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
            _DOCTYPE,
            '<article xml:lang="de">',
        ]
        out.extend(self._front(text_entity))
        out.extend(body)
        out.extend(back)
        out.append("</article>")
        return self._assign_ids("\n".join(out))

    def _strukturdaten(
        self, entity_id: str, qid: Optional[str], level: int
    ) -> List[str]:
        """Render structural data as a section-level ``<custom-meta-group>``.

        This has no equivalent in the reference sample: it is a
        Deckenmalerei-specific extension carrying the source entity UUID and the
        linked Wikidata QID. ``<custom-meta>`` is valid JATS within ``<sec-meta>``.
        """
        pad = IND * level
        out = [
            f"{pad}<sec-meta>",
            f"{pad}{IND}<custom-meta-group>",
            f"{pad}{IND * 2}<custom-meta>",
            f"{pad}{IND * 3}<meta-name>entity_id</meta-name>",
            f"{pad}{IND * 3}<meta-value>{escape(entity_id)}</meta-value>",
            f"{pad}{IND * 2}</custom-meta>",
        ]
        if qid:
            out.extend(
                [
                    f"{pad}{IND * 2}<custom-meta>",
                    f"{pad}{IND * 3}<meta-name>wikidata_qid</meta-name>",
                    f"{pad}{IND * 3}<meta-value>{escape(qid)}</meta-value>",
                    f"{pad}{IND * 2}</custom-meta>",
                ]
            )
        out.append(f"{pad}{IND}</custom-meta-group>")
        out.append(f"{pad}</sec-meta>")
        return out

    def _back(
        self,
        text_entity: Dict,
        deduplicated_citations: Dict[str, str],
        fn_registry: Dict[str, Tuple[int, str]],
        fn_order: List[str],
    ) -> List[str]:
        """Build ``<back>`` with the footnote group and bibliography list."""
        sections: List[str] = []

        if fn_order:
            sections.append(f"{IND * 2}<fn-group>")
            for canonical_name in fn_order:
                number, fn_id = fn_registry[canonical_name]
                content = self.converter.convert_inline(
                    deduplicated_citations[canonical_name]
                )
                sections.append(f'{IND * 3}<fn id="{fn_id}">')
                sections.append(f"{IND * 4}<label>{number}</label>")
                sections.append(f"{IND * 4}<p>{content}</p>")
                sections.append(f"{IND * 3}</fn>")
            sections.append(f"{IND * 2}</fn-group>")

        bibliography = text_entity.get("bibliography")
        if bibliography:
            # The bibliography is newline-separated reference strings. The
            # reference sample has no bibliography list; JATS' idiomatic home for
            # one is <ref-list>/<mixed-citation>, used here.
            entries = [
                self.converter.convert_inline(line)
                for line in bibliography.split("\n")
                if line.strip()
            ]
            sections.append(f"{IND * 2}<ref-list>")
            sections.append(f"{IND * 3}<title>Bibliographie</title>")
            for i, entry in enumerate(entries, start=1):
                sections.append(f'{IND * 3}<ref id="bib{i}">')
                sections.append(f"{IND * 4}<mixed-citation>{entry}</mixed-citation>")
                sections.append(f"{IND * 3}</ref>")
            sections.append(f"{IND * 2}</ref-list>")

        if not sections:
            return []
        return [f"{IND}<back>", *sections, f"{IND}</back>"]

    @staticmethod
    def _assign_ids(xml: str) -> str:
        """Add sequential ``id="dN"`` to ``<sec>``/``<p>``/``<abstract>`` tags.

        Mirrors the reference sample, where these elements carry auto-generated
        ids (``d3e…``). ``<fig>`` and ``<fn>`` keep their explicit, referenced
        ids. The lookahead avoids matching ``<sec-meta>``/``<pub-date>`` etc.
        """
        counter = count(1)
        return re.sub(
            r"<(sec|abstract|p)(?=[ >])",
            lambda m: f'<{m.group(1)} id="d{next(counter)}"',
            xml,
        )

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
