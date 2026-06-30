"""
HTML-to-JATS conversion.

The JATS counterpart of :mod:`~deckenmalereiwiki.converter`: it turns the HTML
fragments stored in the source data into JATS body markup with all character
data correctly XML-escaped.

The tagging style follows the target system's JATS dialect (see the reference
sample ``102976.xml``): ``<italic toggle="yes">``, and ``<ext-link>`` carrying
its own inline ``xmlns:xlink`` declaration plus ``ext-link-type``/``xlink:type``
attributes. An HTML parser is used (rather than regex) to guarantee well-formed,
escaped output. ``<xref>`` tags (inserted upstream for footnote/figure
references, see :mod:`~deckenmalereiwiki.jats_generator`) are passed through
verbatim so inline references survive the conversion.
"""

import re
from html.parser import HTMLParser
from xml.sax.saxutils import escape, quoteattr

XLINK_NS = "http://www.w3.org/1999/xlink"


class _JatsBuilder(HTMLParser):
    """Streaming HTML parser that emits block-level JATS XML."""

    #: HTML inline tags mapped to their (open, close) JATS markup.
    INLINE = {
        "b": ("<bold>", "</bold>"),
        "strong": ("<bold>", "</bold>"),
        "i": ('<italic toggle="yes">', "</italic>"),
        "em": ('<italic toggle="yes">', "</italic>"),
        "u": ("<underline>", "</underline>"),
        "ins": ("<underline>", "</underline>"),
    }
    #: Bold-producing tags. Suppressed inside headings, whose own bold rendering
    #: already covers them (mirrors the MediaWiki converter).
    BOLD = {"b", "strong"}
    HEADERS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []  # finished block-level XML
        # Parallel to ``blocks`` but typed: ``("block", xml)`` for ordinary
        # block-level XML and ``("heading", text)`` for HTML headings. Lets the
        # generator turn in-text headings into nested ``<sec>`` elements (see
        # ``JatsConverter.convert_blocks``).
        self.struct: list[tuple[str, str]] = []
        self.buffer: list[str] = []  # current inline content
        self.list_type: str | None = None  # 'bullet' or 'order'
        self.items: list[str] = []  # accumulated <list> item contents
        self.in_header = False  # suppress redundant bold inside headings

    # -- helpers -------------------------------------------------------
    def _flush_paragraph(self) -> None:
        """Emit any buffered inline content as a ``<p>`` block."""
        content = "".join(self.buffer).strip()
        self.buffer = []
        if content:
            block = f"<p>{content}</p>"
            self.blocks.append(block)
            self.struct.append(("block", block))

    # -- HTMLParser hooks ---------------------------------------------
    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self._flush_paragraph()
        elif tag in self.INLINE:
            if tag in self.BOLD and self.in_header:
                return  # heading is already bold; skip redundant <bold>
            self.buffer.append(self.INLINE[tag][0])
        elif tag in self.HEADERS:
            self._flush_paragraph()
            self.in_header = True
            self.buffer = []  # collect the heading's inline content on its own
        elif tag == "br":
            self.buffer.append("<break/>")
        elif tag in ("ul", "ol"):
            self._flush_paragraph()
            self.list_type = "bullet" if tag == "ul" else "order"
            self.items = []
        elif tag == "li":
            self.buffer = []
        elif tag == "a":
            href = dict(attrs).get("href", "")
            self.buffer.append(
                f'<ext-link xmlns:xlink="{XLINK_NS}" xlink:href={quoteattr(href)} '
                'ext-link-type="uri" xlink:type="simple">'
            )
        elif tag == "xref":
            # Reference markers are pre-rendered as JATS; pass through verbatim.
            attr_str = "".join(f" {k}={quoteattr(v or '')}" for k, v in attrs)
            self.buffer.append(f"<xref{attr_str}>")

    def handle_startendtag(self, tag, attrs):
        if tag in ("br", "xref"):
            self.handle_starttag(tag, attrs)
            if tag == "xref":
                self.buffer.append("</xref>")

    def handle_endtag(self, tag):
        if tag == "p":
            self._flush_paragraph()
        elif tag in self.INLINE:
            if tag in self.BOLD and self.in_header:
                return  # matching suppressed open tag inside heading
            self.buffer.append(self.INLINE[tag][1])
        elif tag in self.HEADERS:
            content = "".join(self.buffer).strip()
            self.buffer = []
            self.in_header = False
            if content:
                # ``convert()`` keeps rendering headings as a bold paragraph for
                # backwards compatibility; ``struct`` records them as headings so
                # ``convert_blocks`` callers can promote them to ``<sec>``.
                self.blocks.append(f"<p><bold>{content}</bold></p>")
                self.struct.append(("heading", content))
        elif tag == "a":
            self.buffer.append("</ext-link>")
        elif tag == "xref":
            self.buffer.append("</xref>")
        elif tag == "li":
            content = "".join(self.buffer).strip()
            self.buffer = []
            if content:
                self.items.append(content)
        elif tag in ("ul", "ol"):
            if self.items:
                parts = [f'<list list-type="{self.list_type}">']
                parts.extend(
                    f"<list-item><p>{item}</p></list-item>" for item in self.items
                )
                parts.append("</list>")
                block = "".join(parts)
                self.blocks.append(block)
                self.struct.append(("block", block))
            self.list_type = None
            self.items = []

    def handle_data(self, data):
        self.buffer.append(escape(data))

    def result(self) -> str:
        """Return the accumulated blocks, flushing any trailing content."""
        self._flush_paragraph()
        return "\n".join(self.blocks)


class JatsConverter:
    """Converts HTML markup to JATS XML."""

    def convert(self, html: str) -> str:
        """Convert *html* to block-level JATS markup (``<p>``, ``<list>`` …)."""
        if not html:
            return ""
        builder = _JatsBuilder()
        builder.feed(html.replace("­", ""))  # strip soft hyphens
        builder.close()
        return builder.result()

    def convert_blocks(self, html: str) -> list[tuple[str, str]]:
        """Convert *html* to a typed list of block-level entries.

        Each entry is ``("block", xml)`` for an ordinary block (``<p>``,
        ``<list>`` …) or ``("heading", text)`` for an HTML heading. Callers use
        this to promote in-text headings into nested ``<sec>`` elements while
        ``convert`` keeps emitting headings as bold paragraphs.
        """
        if not html:
            return []
        builder = _JatsBuilder()
        builder.feed(html.replace("­", ""))  # strip soft hyphens
        builder.close()
        builder._flush_paragraph()  # flush any trailing inline content
        return builder.struct

    def convert_inline(self, html: str) -> str:
        """Convert *html* to inline JATS markup (no block ``<p>`` wrappers).

        Used for contexts such as ``<fn>``/``<mixed-citation>`` content. Block
        breaks collapse to spaces.
        """
        blocks = self.convert(html)
        inline = re.sub(r"</?p\b[^>]*>", "", blocks)
        inline = re.sub(r"\s*\n\s*", " ", inline)
        return inline.strip()


# Convenience alias for standalone use
def html_to_jats(html: str) -> str:
    """Module-level shortcut for ``JatsConverter().convert(html)``."""
    return JatsConverter().convert(html)
