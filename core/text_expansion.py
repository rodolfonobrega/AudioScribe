"""Deterministic local snippet expansion."""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Mapping


def _fold(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip().casefold()


def expand_snippets(text: str, snippets: Iterable[Mapping[str, object]]) -> str:
    """Replace complete-word triggers, longest first, without recursion."""
    if not text:
        return text
    replacements = {}
    for item in snippets:
        if not item or not item.get("enabled", 1):
            continue
        trigger = str(item.get("trigger") or "").strip()
        replacement = str(item.get("replacement") or "").strip()
        if trigger and replacement:
            replacements[_fold(trigger)] = replacement
    if not replacements:
        return text

    escaped = sorted((re.escape(key) for key in replacements), key=len, reverse=True)
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(escaped) + r")(?!\w)", re.IGNORECASE)
    return pattern.sub(lambda match: replacements.get(_fold(match.group(0)), match.group(0)), unicodedata.normalize("NFC", text))


def dictionary_hint_words(dictionary: Iterable[Mapping[str, object]]) -> list[str]:
    return [str(item.get("word")) for item in dictionary if item.get("word")]
