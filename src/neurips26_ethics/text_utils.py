"""Text helpers for normalization and similarity scoring."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "their",
    "this",
    "to",
    "toward",
    "via",
    "with",
}


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", value.lower()).strip()


def tokenize(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-zA-Z0-9]+", value.lower()) if token]


def important_terms(value: str, *, limit: int) -> list[str]:
    seen: list[str] = []
    for token in tokenize(value):
        if len(token) <= 2 or token in STOPWORDS:
            continue
        if token not in seen:
            seen.append(token)
        if len(seen) >= limit:
            break
    return seen


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def normalize_author(author: str) -> str:
    parts = [token for token in re.findall(r"[a-zA-Z]+", author.lower()) if token]
    if not parts:
        return ""
    return parts[-1]
