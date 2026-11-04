"""Shared tokenizer for routing and retrieval.

Stems are only a trailing "s" on longer words, so "notes" meets "note"
without pulling in a real stemmer.
"""

from __future__ import annotations

import re

STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "from",
        "with",
        "by",
        "is",
        "are",
        "be",
        "that",
        "this",
        "it",
        "as",
        "at",
        "into",
        "until",
        "per",
        "its",
        "their",
        "we",
        "do",
        "does",
        "did",
        "what",
        "when",
        "where",
        "who",
        "how",
        "why",
        "which",
        "about",
        "over",
        "after",
        "before",
        "any",
        "than",
        "then",
        "not",
        "no",
        "yes",
        "if",
        "so",
        "but",
        "can",
        "may",
        "our",
        "your",
        "you",
        "they",
        "them",
        "was",
        "were",
        "will",
        "just",
        "only",
        "also",
        "up",
        "down",
    }
)


def words(text: str) -> list[str]:
    found: list[str] = []
    for raw in re.findall(r"[a-z0-9]+", text.lower()):
        if raw in STOP or len(raw) < 2:
            continue
        found.append(raw)
    return found


def lexemes(text: str) -> set[str]:
    out: set[str] = set()
    for word in words(text):
        out.add(word)
        if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
            out.add(word[:-1])
    return out
