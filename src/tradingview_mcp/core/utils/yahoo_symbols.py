"""Yahoo Finance symbol encoding shared by quote and history fetches."""
from __future__ import annotations

import urllib.parse


def encode_yahoo_symbol(symbol: str) -> str:
    """Percent-encode a Yahoo chart symbol while keeping ``.`` and ``^`` raw.

    ``M&M.NS`` has to become ``M%26M.NS``. Encoding the caret in ``^NSEI`` or
    the dot in ``RELIANCE.NS`` is unnecessary and has broken some proxies.
    """
    return urllib.parse.quote(symbol.strip(), safe=".^")
