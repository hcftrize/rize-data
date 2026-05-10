"""Fuzzy matching for /rizeby canton — handles accents, spacing, partials."""
import unicodedata
import re
from rapidfuzz import fuzz, process


def normalize(s: str) -> str:
    """Lowercase, strip accents, remove punctuation, collapse spaces."""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def find_entity(query: str, entities: list[dict]) -> dict | None:
    """
    Find best matching entity from the list.
    Returns entity dict or None if no good match.
    """
    q = normalize(query)
    if not q:
        return None

    # Build normalized name → entity map
    norm_map = {}
    for e in entities:
        name = e.get("name") or e.get("id") or ""
        norm_map[normalize(name)] = e

    # Exact match first
    if q in norm_map:
        return norm_map[q]

    # Starts-with match (e.g. "axa" → "axa im")
    for norm_name, entity in norm_map.items():
        if norm_name.startswith(q) or q.startswith(norm_name):
            return entity

    # Fuzzy match — score > 65
    names = list(norm_map.keys())
    result = process.extractOne(q, names, scorer=fuzz.token_sort_ratio)
    if result and result[1] >= 65:
        return norm_map[result[0]]

    # Word overlap — at least one full word matches
    q_words = set(q.split())
    for norm_name, entity in norm_map.items():
        name_words = set(norm_name.split())
        if q_words & name_words:  # intersection
            return entity

    return None
