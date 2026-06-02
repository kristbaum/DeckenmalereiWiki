"""
HTML-to-MediaWiki conversion.
"""

import re


class HtmlConverter:
    """Converts HTML markup to MediaWiki wikitext syntax."""

    def convert(self, html: str) -> str:
        """Convert *html* to MediaWiki syntax."""
        if not html:
            return ""

        text = html

        def replace_header(m):
            eq = "=" * min(int(m.group(1)) + 1, 6)
            return f"{eq} {m.group(2)} {eq}\n"

        text = re.sub(r"<h([1-6])>(.*?)</h\1>", replace_header, text, flags=re.DOTALL)

        # Bold and italic
        text = re.sub(
            r"<strong>(.*?)</strong>", r"\1", text, flags=re.DOTALL
        )  # Only gets added to headings, not needed for mediawiki
        text = re.sub(r"<b>(.*?)</b>", r"'''\1'''", text, flags=re.DOTALL)
        text = re.sub(r"<em>(.*?)</em>", r"''\1''", text, flags=re.DOTALL)
        text = re.sub(r"<i>(.*?)</i>", r"''\1''", text, flags=re.DOTALL)

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

    @staticmethod
    def _convert_list(list_content: str, marker: str) -> str:
        """Convert HTML list items to MediaWiki format."""
        items = re.findall(r"<li>(.*?)</li>", list_content, flags=re.DOTALL)
        return "\n".join(f"{marker} {item.strip()}" for item in items) + "\n\n"


# Convenience alias for standalone use
def html_to_mediawiki(html: str) -> str:
    """Module-level shortcut for ``HtmlConverter().convert(html)``."""
    return HtmlConverter().convert(html)
