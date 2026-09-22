"""Proofreading pipeline for the CbDD texts.

Importing this package puts the project's ``src/`` on ``sys.path``, so the
modules below can use ``deckenmalereiwiki.loader`` and
``deckenmalereiwiki.citations`` even though the checker lives outside the
package.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

