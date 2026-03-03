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

        # Headers
        text = re.sub(r"<h1>(.*?)</h1>", r"== \1 ==\n", text, flags=re.DOTALL)
        text = re.sub(r"<h2>(.*?)</h2>", r"=== \1 ===\n", text, flags=re.DOTALL)
        text = re.sub(r"<h3>(.*?)</h3>", r"==== \1 ====\n", text, flags=re.DOTALL)
        text = re.sub(r"<h4>(.*?)</h4>", r"===== \1 =====\n", text, flags=re.DOTALL)

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
