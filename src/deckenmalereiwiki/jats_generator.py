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

#: DOCTYPE for JATS Journal Publishing DTD 1.4. The publisher's review asked us
#: to emit 1.4-conformant files from the start (notably for ``<kwd>``).
_DOCTYPE = (
    '<!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal Publishing DTD '
    'v1.4 20241031//EN" "https://jats.nlm.nih.gov/publishing/1.4/'
    'JATS-journalpublishing1-4-mathml3.dtd">'
)

#: Controlled-vocabulary descriptors for ``<kwd>`` term identifiers. Each tuple
#: is ``(vocab, vocab-identifier, term-base-URL)``; a concrete identifier is the
#: term base with the source id/QID/GND number appended.
_VOCAB_DECKENMALEREI = (
    "deckenmalerei.eu",
    "https://deckenmalerei.eu",
    "https://www.deckenmalerei.eu/",
)
_VOCAB_WIKIDATA = (
    "Wikidata",
    "http://www.wikidata.org",
    "http://www.wikidata.org/entity/",
)
_VOCAB_GND = (
    "GND",
    "https://d-nb.info/standards/elementset/gnd#",
    "https://d-nb.info/gnd/",
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

    @staticmethod
    def _kwd(vocab: Tuple[str, str, str], term: str, level: int) -> str:
        """Render a single ``<kwd>`` controlled-vocabulary term identifier.

        *vocab* is one of the ``_VOCAB_*`` tuples; *term* is the bare id/QID/GND
        number appended to the vocabulary's term-base URL.
        """
        name, vocab_id, term_base = vocab
        term_uri = term_base + term
        return (
            f'{IND * level}<kwd vocab="{name}" vocab-identifier="{vocab_id}" '
            f"vocab-term-identifier={quoteattr(term_uri)}/>"
        )

    # ------------------------------------------------------------------
    # Journal metadata
    # ------------------------------------------------------------------

    def _journal_meta(self, level: int) -> List[str]:
        """Render the static ``<journal-meta>`` block.

        The data is the same for every CbDD article, so it is hard-coded here.
        ISSN and the homepage URLs are not yet assigned; they are emitted as
        visible placeholders and flagged with TODOs below.
        """
        pad = IND * level
        return [
            f"{pad}<journal-meta>",
            f'{pad}{IND}<journal-id journal-id-type="publisher-id">CbDD</journal-id>',
            f"{pad}{IND}<journal-title-group>",
            f"{pad}{IND * 2}<journal-title>Corpus der barocken Deckenmalerei "
            "in Deutschland</journal-title>",
            f"{pad}{IND}</journal-title-group>",
            # TODO: ISSN eintragen, sobald sie beantragt/zugeteilt ist.
            f'{pad}{IND}<issn pub-type="epub">####-####</issn>',
            f"{pad}{IND}<publisher>",
            f"{pad}{IND * 2}<publisher-name>arthistoricum.net - eJournals"
            "</publisher-name>",
            f"{pad}{IND * 2}<publisher-loc>Heidelberg</publisher-loc>",
            f"{pad}{IND}</publisher>",
            # TODO: finale CbDD-Homepage-URLs (de/en) eintragen.
            f'{pad}{IND}<self-uri xlink:href="https://####" xml:lang="de">Homepage '
            "des Corpus der barocken Deckenmalerei in Deutschland (CbDD)</self-uri>",
            f'{pad}{IND}<self-uri xlink:href="https://####" xml:lang="en">Homepage '
            "of the Corpus der barocken Deckenmalerei in Deutschland (CbDD)</self-uri>",
            f"{pad}</journal-meta>",
        ]

    def _permissions(self, year: str, level: int) -> List[str]:
        """Render the CC BY-SA 4.0 ``<permissions>`` block.

        The licence text is fixed; only the copyright year varies per article.
        """
        pad = IND * level
        yr = escape(year) if year else ""
        cc = "https://creativecommons.org/licenses/by-sa/4.0/"
        out = [
            f"{pad}<permissions>",
            f"{pad}{IND}<copyright-statement>Text © {yr} by the author(s)."
            "</copyright-statement>",
        ]
        if year:
            out.append(f"{pad}{IND}<copyright-year>{yr}</copyright-year>")
        out.extend(
            [
                f'{pad}{IND}<license license-type="open-access" '
                f'xlink:href="{cc}" xml:lang="de">',
                f'{pad}{IND * 2}<license-p><inline-graphic xlink:href="by-sa.svg"/>'
                "Diese Publikation ist unter der Creative Commons Lizenz 4.0 "
                "(CC BY-SA 4.0) veröffentlicht. Der Umschlagentwurf unterliegt der "
                "Creative-Commons-Lizenz CC BY-ND 4.0.</license-p>",
                f"{pad}{IND}</license>",
                f'{pad}{IND}<license license-type="open-access" '
                f'xlink:href="{cc}" xml:lang="en">',
                f'{pad}{IND * 2}<license-p><inline-graphic xlink:href="by-sa.svg"/>'
                "This journal article is published under the Creative Commons "
                "License 4.0 (CC BY-SA 4.0). The cover is subject to the Creative "
                "Commons License CC BY-ND 4.0.</license-p>",
                f"{pad}{IND}</license>",
                f"{pad}</permissions>",
            ]
        )
        return out

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
        """Build ``<front>`` (journal-meta, id, title, authors, date, abstract).

        Notes on the metadata that has no per-article source data yet and is
        emitted with TODO placeholders for the publisher to fill in:

        * the DOI (assigned manually in the publisher's OJS once the article is
          created) — emitted as ``pub-id-type="doi"`` with a ``###`` placeholder;
        * the optional front cover (``<supplementary-material>``);
        * ISSN and homepage URLs (in ``<journal-meta>``).

        The Deckenmalerei UUID is no longer the ``<article-id>`` but a
        controlled-vocabulary ``<kwd>`` in the article-level ``<kwd-group>``.
        """
        title = text_entity.get("appellation") or f"Untitled {text_entity['ID']}"
        year = _modification_year(text_entity)

        out = [f"{IND}<front>"]
        out.extend(self._journal_meta(level=2))
        out.append(f"{IND * 2}<article-meta>")
        # TODO: DOI aus dem OJS eintragen. Er wird dort beim Anlegen des
        # Beitrags generiert (manueller Redaktionsschritt beim Verlag).
        out.append(f'{IND * 3}<article-id pub-id-type="doi">https://doi.org/###</article-id>')
        out.append(f"{IND * 3}<title-group>")
        out.append(f"{IND * 4}<article-title>{escape(title)}</article-title>")
        out.append(f"{IND * 3}</title-group>")
        out.extend(self._contrib_group(text_entity, level=3))

        if year:
            out.append(f"{IND * 3}<pub-date>")
            out.append(f"{IND * 4}<year>{escape(year)}</year>")
            out.append(f"{IND * 3}</pub-date>")

        # TODO: optionales Front-Cover einbinden, sobald eine Cover-Datei
        # vorliegt, z. B.:
        # <supplementary-material content-type="front_cover" xlink:href="cover.jpg"
        #     position="float" orientation="portrait"/>

        out.extend(self._permissions(year, level=3))

        short_text = text_entity.get("shortText")
        if short_text:
            body = self.converter.convert(short_text)
            out.append(f"{IND * 3}<abstract>")
            out.append(f"{IND * 4}<title><bold>Zusammenfassung</bold></title>")
            if body:
                out.append(self._indent(body, level=4))
            out.append(f"{IND * 3}</abstract>")

        # The Deckenmalerei UUID of the article moves here as a <kwd>.
        out.append(f"{IND * 3}<kwd-group>")
        out.append(self._kwd(_VOCAB_DECKENMALEREI, text_entity["ID"], level=4))
        out.append(f"{IND * 3}</kwd-group>")

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

        # TEXT_PART entities carry a ``_depth`` (1 = top level, 2 = nested …);
        # parts deeper than their predecessor are nested inside it, so a
        # text-less parent like "Malerei" becomes the enclosing <sec> of its
        # children (e.g. "Die Wandmalerei im Vestibül"). ``open_depths`` is the
        # stack of currently open section depths.
        open_depths: List[int] = []
        for part in text_parts:
            depth = part.get("_depth", 1)
            while open_depths and open_depths[-1] >= depth:
                body.append(f"{IND * (1 + len(open_depths))}</sec>")
                open_depths.pop()
            sec_level = 2 + len(open_depths)
            content_level = sec_level + 1
            body.append(f"{IND * sec_level}<sec>")
            open_depths.append(depth)

            documented_id = self.loader.get_documented_entity_id(part["ID"])
            if documented_id:
                qid = self.wikidata_mapping.get(documented_id)
                body.extend(self._sec_meta(documented_id, qid, level=content_level))

            appellation = part.get("appellation", "")
            if appellation:
                body.append(
                    f"{IND * content_level}<title>{escape(appellation)}</title>"
                )

            part_lead_entity_id, part_lead = (
                self.loader.get_lead_resource_via_documents(part["ID"])
            )
            resources: List[tuple] = []
            if part_lead and part_lead.get("resProvider"):
                resources.append((part_lead_entity_id, part_lead))
            for img in self.loader.get_images(part["ID"]):
                resources.append((img["ID"], img))
            body.extend(self._figures(resources, fig_counter, level=content_level))

            text = replace_refs(part_texts[part["ID"]], part["ID"])
            blocks = self.converter.convert_blocks(text)
            body.extend(self._render_part_blocks(blocks, content_level))

        while open_depths:
            body.append(f"{IND * (1 + len(open_depths))}</sec>")
            open_depths.pop()
        body.append(f"{IND}</body>")

        back = self._back(text_entity, deduplicated_citations, fn_registry, fn_order)

        out = [
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
            _DOCTYPE,
            '<article xml:lang="de" xmlns:xlink="http://www.w3.org/1999/xlink">',
        ]
        out.extend(self._front(text_entity))
        out.extend(body)
        out.extend(back)
        out.append("</article>")
        return self._assign_ids("\n".join(out))

    def _sec_meta(
        self, entity_id: str, qid: Optional[str], level: int
    ) -> List[str]:
        """Render structural data as a section-level ``<kwd-group>``.

        Per the publisher's review the source entity UUID, the linked Wikidata
        QID and (when available) the GND number are emitted as controlled
        ``<kwd>`` term identifiers inside ``<sec-meta>`` rather than as the
        former ``<custom-meta-group>``. The GND number comes from the documented
        entity's ``normdata.gnd``.
        """
        pad = IND * level
        out = [f"{pad}<sec-meta>", f"{pad}{IND}<kwd-group>"]
        out.append(self._kwd(_VOCAB_DECKENMALEREI, entity_id, level + 2))
        if qid:
            out.append(self._kwd(_VOCAB_WIKIDATA, qid, level + 2))
        entity = self.loader.entities.get(entity_id) or {}
        gnd = (entity.get("normdata") or {}).get("gnd")
        if gnd:
            out.append(self._kwd(_VOCAB_GND, gnd, level + 2))
        out.append(f"{pad}{IND}</kwd-group>")
        out.append(f"{pad}</sec-meta>")
        return out

    def _render_part_blocks(
        self, blocks: List[Tuple[str, str]], level: int
    ) -> List[str]:
        """Render a TEXT_PART's converted *blocks* at indentation *level*.

        Ordinary blocks are emitted directly. An in-text heading (originally an
        HTML ``<h*>``, e.g. "Die Erstfassung") opens a nested ``<sec>`` whose
        ``<title>`` carries the heading text; the blocks that follow it belong to
        that subsection until the next heading. This satisfies the review note
        that such headings "müsste in ein /sec geschachtelt werden".
        """
        out: List[str] = []
        sub_open = False
        for kind, payload in blocks:
            if kind == "heading":
                if sub_open:
                    out.append(f"{IND * level}</sec>")
                out.append(f"{IND * level}<sec>")
                out.append(f"{IND * (level + 1)}<title><bold>{payload}</bold></title>")
                sub_open = True
            else:
                out.append(self._indent(payload, level + 1 if sub_open else level))
        if sub_open:
            out.append(f"{IND * level}</sec>")
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
            sections.extend(self._bibliography(bibliography, level=2))

        if not sections:
            return []
        return [f"{IND}<back>", *sections, f"{IND}</back>"]

    #: Separates the short citation (Sigle) from the full reference in a
    #: bibliography line, e.g. ``"Ahlers, Restaurierung, 2000. – Ahlers, …"``.
    _SIGLE_SEP = ". – "

    def _bibliography(self, bibliography: str, level: int) -> List[str]:
        """Render the article bibliography as a nested ``<ref-list>``.

        Per the publisher's review the bibliography is wrapped in an outer
        ``<ref-list><title>Bibliographie</title>`` containing one inner
        ``<ref-list>`` per heading line (e.g. "Literatur:"). Each reference is
        split on ``". – "`` into a ``<label>`` (the Sigle, kept for later
        string-matching/linking) and a ``<mixed-citation>`` with the full text;
        lines without that separator are treated as the inner list's heading.
        """
        pad = IND * level
        out = [f"{pad}<ref-list>", f"{pad}{IND}<title>Bibliographie</title>"]

        inner_open = False
        ref_counter = count(1)

        def open_inner(title: Optional[str]) -> None:
            nonlocal inner_open
            if inner_open:
                out.append(f"{pad}{IND}</ref-list>")
            out.append(f"{pad}{IND}<ref-list>")
            if title:
                out.append(f"{pad}{IND * 2}<title>{escape(title)}</title>")
            inner_open = True

        for line in bibliography.split("\n"):
            line = line.strip()
            if not line:
                continue
            if self._SIGLE_SEP in line:
                if not inner_open:
                    open_inner(None)
                sigle, _, full = line.partition(self._SIGLE_SEP)
                label = self.converter.convert_inline(sigle.strip())
                citation = self.converter.convert_inline(full.strip())
                i = next(ref_counter)
                out.append(f'{pad}{IND * 2}<ref id="bib{i}">')
                out.append(f"{pad}{IND * 3}<label>{label}</label>")
                out.append(
                    f"{pad}{IND * 3}<mixed-citation>{citation}</mixed-citation>"
                )
                out.append(f"{pad}{IND * 2}</ref>")
            else:
                # A line without a Sigle separator heads a new inner list
                # (e.g. "Literatur:", "Quellen:").
                open_inner(self.converter.convert_inline(line))

        if inner_open:
            out.append(f"{pad}{IND}</ref-list>")
        out.append(f"{pad}</ref-list>")
        return out

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
