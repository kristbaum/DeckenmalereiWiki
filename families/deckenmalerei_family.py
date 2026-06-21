"""Pywikibot family file for the Deckenmalerei (CbDD) MediaWiki instance.

Registered from ``user-config.py`` via ``register_families_folder('families')``.
The MediaWiki API/scripts live at the domain root (``/api.php``), matching the
former mwclient ``path="/"`` configuration.
"""

from pywikibot import family


class Family(family.SingleSiteFamily):
    name = "deckenmalerei"
    domain = "localhost:8080"

    def protocol(self, code):
        return "http"

    def scriptpath(self, code):
        # MediaWiki scripts (api.php / index.php) are served from the root.
        return ""
