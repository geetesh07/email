"""
deduplicator.py — Remove duplicate paragraphs across forwarded email threads.
"""

import re
import hashlib
from typing import List, Set


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


def deduplicate_body(body: str, seen_hashes: Set[str]) -> str:
    """
    Remove paragraphs that have been seen before (from forwarded threads).
    
    Args:
        body: The email body text to deduplicate
        seen_hashes: Set of paragraph hashes seen across the entire batch.
                     This set is modified in-place to include new paragraphs.
    
    Returns:
        Body with duplicate paragraphs removed.
    """
    if not body:
        return body

    paragraphs = re.split(r"\n\s*\n", body)
    unique_paragraphs = []

    for para in paragraphs:
        para_hash = _hash_paragraph(para)
        if not para_hash:
            # Very short paragraph — keep it (likely a greeting or single line)
            unique_paragraphs.append(para)
            continue

        if para_hash not in seen_hashes:
            seen_hashes.add(para_hash)
            unique_paragraphs.append(para)
        # else: skip — this paragraph was already seen

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
    results = []

    for body in bodies:
        deduped = deduplicate_body(body, seen_hashes)
        results.append(deduped)

    return results
