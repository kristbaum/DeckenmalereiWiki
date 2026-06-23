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
            self.blocks.append(f"<p>{content}</p>")

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
            self.buffer.append("<bold>")
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
            self.buffer.append("</bold>")
            self.in_header = False
            self._flush_paragraph()
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
                self.blocks.append("".join(parts))
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
