"""Small text helpers shared by sources and enrichers (no extra dependencies)."""

from __future__ import annotations

import html
import re

_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_BLOCK = re.compile(r"</(p|div|li|tr|h[1-6]|section|article)>", re.I)
_BR = re.compile(r"<br\s*/?>", re.I)
_TAG = re.compile(r"<[^>]+>")
_BLANKS = re.compile(r"\n{3,}")
_SPACES = re.compile(r"[ \t]{2,}")


def html_to_text(raw: str) -> str:
    """Good-enough HTML → text. Job descriptions are simple markup."""
    text = _SCRIPT.sub(" ", raw or "")
    text = _BR.sub("\n", text)
    text = _BLOCK.sub("\n", text)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    text = _SPACES.sub(" ", text)
    return _BLANKS.sub("\n\n", text).strip()


def truncate(text: str, max_chars: int) -> str:
    """Trim on a word boundary — keeps prompt cost predictable."""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    space = cut.rfind(" ")
    return (cut[:space] if space > max_chars * 0.8 else cut).rstrip() + " …"
