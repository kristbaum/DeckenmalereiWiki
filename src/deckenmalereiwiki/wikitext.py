"""
Wikitext helpers shared by the importer.
"""

import re
import unicodedata

# C0 control characters MediaWiki rejects as non-normalized: everything in
# U+0000–U+001F except HT (\t), LF (\n) and CR (\r).
_DISALLOWED_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitize_wikitext(text: str) -> str:
    """Return *text* as valid wiki page content for the MediaWiki API.

    MediaWiki requires NFC-normalized Unicode without C0 control characters
    other than tab/newline/carriage return; otherwise ``page.save`` emits an
    ``invalid or non-normalized data`` API warning. This normalizes to NFC and
    drops the disallowed control characters.
    """
    return _DISALLOWED_CONTROL_RE.sub("", unicodedata.normalize("NFC", text))
