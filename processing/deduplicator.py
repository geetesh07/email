"""
deduplicator.py — Remove duplicate paragraphs across forwarded email threads.
Uses two-pass approach: fast MD5 hash then Jaccard fuzzy matching.
Also strips quoted reply markers (> prefixed lines).
"""

import re
import hashlib
from typing import List, Set, Dict


def _normalize_text(text: str) -> str:
    """Normalize whitespace and case for consistent hashing."""
    # Collapse all whitespace to single spaces
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return normalized


def _hash_paragraph(paragraph: str) -> str:
    """Generate a hash for a normalized paragraph."""
    normalized = _normalize_text(paragraph)
    if len(normalized) < 10:  # Skip very short fragments
        return ""
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def _tokenize_words(text: str) -> Set[str]:
    """Extract a set of lowercase words from text."""
    return set(re.findall(r'[a-z0-9]+', text.lower()))


def _jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float:
    """Compute Jaccard similarity between two word sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / max(union, 1)


def _strip_quoted_lines(text: str) -> str:
    """
    Strip lines starting with > (email reply quotes).
    These are repeated content from previous emails in a thread.
    """
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Skip quoted lines (> prefix)
        if stripped.startswith(">"):
            continue
        # Skip lines that are just the "On ... wrote:" reply header
        if re.match(r'^On\s+.*wrote:\s*$', stripped, re.IGNORECASE):
            continue
        cleaned.append(line)

    return "\n".join(cleaned)


def deduplicate_body(
    body: str,
    seen_hashes: Set[str],
    seen_word_sets: List[Set[str]] = None,
    fuzzy_threshold: float = 0.85,
) -> str:
    """
    Remove paragraphs that have been seen before (from forwarded threads).
    Two-pass approach:
    1. Fast MD5 hash for exact matches
    2. Jaccard similarity for fuzzy matches (catches slightly modified forwards)

    Args:
        body: The email body text to deduplicate
        seen_hashes: Set of paragraph hashes seen across the entire batch.
                     This set is modified in-place to include new paragraphs.
        seen_word_sets: List of word sets for fuzzy comparison.
                        This list is modified in-place.
        fuzzy_threshold: Jaccard similarity threshold for fuzzy matching (default 0.85)

    Returns:
        Body with duplicate paragraphs removed.
    """
    if not body:
        return body

    # Initialize fuzzy matching storage if not provided
    if seen_word_sets is None:
        seen_word_sets = []

    # Strip quoted reply lines first
    body = _strip_quoted_lines(body)

    paragraphs = re.split(r"\n\s*\n", body)
    unique_paragraphs = []

    for para in paragraphs:
        para_stripped = para.strip()
        if not para_stripped:
            continue

        # Pass 1: Exact hash match
        para_hash = _hash_paragraph(para)
        if para_hash:
            if para_hash in seen_hashes:
                continue  # Exact duplicate — skip
            seen_hashes.add(para_hash)

        # Very short paragraph — keep it (greetings, single lines)
        if not para_hash:
            unique_paragraphs.append(para)
            continue

        # Pass 2: Fuzzy matching via Jaccard similarity
        para_words = _tokenize_words(para)
        if len(para_words) < 5:
            # Too short for meaningful fuzzy matching
            unique_paragraphs.append(para)
            seen_word_sets.append(para_words)
            continue

        is_fuzzy_dup = False
        for prev_words in seen_word_sets:
            if _jaccard_similarity(para_words, prev_words) >= fuzzy_threshold:
                is_fuzzy_dup = True
                break

        if not is_fuzzy_dup:
            unique_paragraphs.append(para)
            seen_word_sets.append(para_words)
        # else: skip — this paragraph is a fuzzy duplicate

    return "\n\n".join(unique_paragraphs)


def deduplicate_batch(bodies: List[str]) -> List[str]:
    """
    Deduplicate across a batch of email bodies.
    Processes emails in order (oldest first is recommended).

    Args:
        bodies: List of email body strings

    Returns:
        List of deduplicated body strings
    """
    seen_hashes: Set[str] = set()
    seen_word_sets: List[Set[str]] = []
    results = []

    for body in bodies:
        deduped = deduplicate_body(body, seen_hashes, seen_word_sets)
        results.append(deduped)

    return results
