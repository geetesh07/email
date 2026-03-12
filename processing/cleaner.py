"""
cleaner.py — Strip signatures, disclaimers, and forwarded headers from email bodies.
"""

import re
from typing import List


def _build_signature_patterns(markers: List[str]) -> List[re.Pattern]:
    """Build regex patterns from signature marker strings."""
    patterns = []
    for marker in markers:
        # Escape the marker for regex and make it match at line start
        escaped = re.escape(marker)
        patterns.append(re.compile(
            rf"^\s*{escaped}", re.IGNORECASE | re.MULTILINE
        ))
    return patterns


# Common phone patterns (often appear in signatures)
PHONE_PATTERN = re.compile(
    r"^\s*(?:Tel|Phone|Mobile|Cell|Mob|Fax|Ph|T|M|F)\s*[:.]\s*[\+\d\(\)\-\s]{7,}",
    re.IGNORECASE | re.MULTILINE,
)

# Forwarded message header pattern
FORWARDED_PATTERNS = [
    re.compile(r"-{3,}\s*Forwarded message\s*-{3,}", re.IGNORECASE),
    re.compile(r"-{3,}\s*Original Message\s*-{3,}", re.IGNORECASE),
    re.compile(r"^From:\s+.*\nSent:\s+.*\nTo:\s+.*\nSubject:\s+", re.MULTILINE),
    re.compile(r"^On\s+.*wrote:\s*$", re.MULTILINE),
]


def strip_signature(body: str, signature_markers: List[str]) -> str:
    """
    Remove signature block from email body.
    Finds the LAST occurrence of a signature marker and truncates there.
    """
    if not body:
        return body

    lines = body.split("\n")
    sig_patterns = _build_signature_patterns(signature_markers)

    # Scan from the bottom up to find the signature start
    # Only look in the last 30% of the email (signatures are at the end)
    cutoff_start = max(0, int(len(lines) * 0.5))

    best_cut = len(lines)

    for i in range(len(lines) - 1, cutoff_start - 1, -1):
        line = lines[i]
        for pattern in sig_patterns:
            if pattern.search(line):
                best_cut = i
                break
        # Also check for phone patterns in signature area
        if PHONE_PATTERN.search(line) and i > cutoff_start:
            # Only cut here if we haven't found a better marker above
            if best_cut == len(lines):
                best_cut = i

    if best_cut < len(lines):
        return "\n".join(lines[:best_cut]).rstrip()

    return body


def strip_disclaimer(body: str, disclaimer_phrases: List[str]) -> str:
    """
    Remove disclaimer blocks from email body.
    Looks for paragraphs containing known disclaimer phrases and removes them.
    """
    if not body or not disclaimer_phrases:
        return body

    paragraphs = re.split(r"\n\s*\n", body)
    clean_paragraphs = []

    for para in paragraphs:
        para_lower = para.lower()
        is_disclaimer = False
        for phrase in disclaimer_phrases:
            if phrase.lower() in para_lower:
                is_disclaimer = True
                break
        if not is_disclaimer:
            clean_paragraphs.append(para)

    return "\n\n".join(clean_paragraphs)


def strip_forwarded_headers(body: str) -> str:
    """Remove forwarded message headers but keep the forwarded content."""
    if not body:
        return body

    for pattern in FORWARDED_PATTERNS:
        body = pattern.sub("", body)

    # Clean up excessive blank lines left behind
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def clean_email_body(
    body: str,
    signature_markers: List[str],
    disclaimer_phrases: List[str],
) -> str:
    """
    Full cleaning pipeline for an email body:
    1. Strip forwarded headers
    2. Strip disclaimer paragraphs
    3. Strip signature block
    4. Normalize whitespace
    """
    if not body:
        return ""

    cleaned = strip_forwarded_headers(body)
    cleaned = strip_disclaimer(cleaned, disclaimer_phrases)
    cleaned = strip_signature(cleaned, signature_markers)

    # Normalize: collapse 3+ newlines to 2, strip trailing whitespace per line
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    lines = [line.rstrip() for line in cleaned.split("\n")]
    cleaned = "\n".join(lines).strip()

    return cleaned
