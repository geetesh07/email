"""
cleaner.py — Strip signatures, disclaimers, Salesforce refs, and forwarded headers from email bodies.
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

# Bare phone number pattern (not prefixed with a label)
BARE_PHONE_PATTERN = re.compile(
    r"^\s*[\+]?\d[\d\s\-\(\)]{8,}\s*$"
)

# Email address pattern
EMAIL_ADDR_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# URL / website / LinkedIn pattern
URL_PATTERN = re.compile(
    r"(?:https?://|www\.)\S+|linkedin\.com\S*|twitter\.com\S*|facebook\.com\S*",
    re.IGNORECASE,
)

# Address-like patterns (street, road, sector, PIN codes, zip codes)
ADDRESS_PATTERN = re.compile(
    r"\b(?:street|road|rd|avenue|ave|sector|plot|lane|block|floor|suite|"
    r"building|bldg|pin|zip)\b|\b\d{5,6}\b",
    re.IGNORECASE,
)

# Role/title keywords that often appear in signatures
SIGNATURE_ROLE_KEYWORDS = {
    "engineer", "manager", "director", "sales", "purchase", "procurement",
    "technical", "design", "project", "head", "lead", "chief", "senior",
    "junior", "executive", "officer", "consultant", "specialist",
    "supervisor", "coordinator", "vp", "ceo", "cto", "coo", "md", "gm",
    "asst", "assistant", "dept", "department",
}

# Forwarded message header patterns
# Forwarded message header patterns
FORWARDED_PATTERNS = [
    re.compile(r"-{3,}\s*Forwarded message\s*-{3,}", re.IGNORECASE),
    re.compile(r"-{3,}\s*Original Message\s*-{3,}", re.IGNORECASE),
    re.compile(r"^From:\s+.*\nSent:\s+.*\nTo:\s+.*\nSubject:\s+", re.MULTILINE),
    re.compile(r"^On\s+.*wrote:\s*$", re.MULTILINE),
    # Outlook/Exchange separator lines
    re.compile(r"^_{10,}$", re.MULTILINE),
    re.compile(r"^-{10,}$", re.MULTILINE),
    re.compile(r"^={10,}$", re.MULTILINE),
]

# Calendar invite block patterns
CALENDAR_PATTERNS = [
    re.compile(
        r"^(?:When|Where|Organizer|Required|Optional):\s+.*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    re.compile(r"^─{5,}$", re.MULTILINE),  # Unicode box-drawing separators
]

# Auto-reply footer patterns
AUTO_REPLY_PATTERNS = [
    re.compile(r"This is an automatic(?:ally generated)? (?:reply|message|response)", re.IGNORECASE),
    re.compile(r"I (?:am|will be) (?:currently )?(?:out of (?:the )?office|on leave|unavailable)", re.IGNORECASE),
    re.compile(r"^Sent from (?:my )?\w+", re.MULTILINE | re.IGNORECASE),
]

# ═══════════════════════════════════════════════════════════════
#  SALESFORCE REFERENCE PATTERNS
# ═══════════════════════════════════════════════════════════════

# Salesforce threading refs: ref:_00DXXXX._XXXXX:ref
SF_REF_THREAD = re.compile(
    r"ref:_[a-zA-Z0-9]+\._[a-zA-Z0-9]+:ref",
    re.IGNORECASE,
)

# Bracket-enclosed refs: [ ref:00012345 ] or [ref:XXXXX]
SF_REF_BRACKET = re.compile(
    r"\[\s*ref:\s*[a-zA-Z0-9_.\-]+\s*\]",
    re.IGNORECASE,
)

# Salesforce record IDs (15 or 18 char alphanumeric starting with known prefixes)
SF_RECORD_ID = re.compile(
    r"\b[a-zA-Z0-9]{15}(?:[a-zA-Z0-9]{3})?\b"
)

# Case/ref number patterns: Case#00012345, Case: 00012345, Ref: 00012345
SF_CASE_REF = re.compile(
    r"(?:Case|Ref|Reference|Ticket|Opp|Opportunity)\s*[#:.\-]\s*\d{5,}",
    re.IGNORECASE,
)

# Lines that are purely SF source file markers from our ingestion
SF_SOURCE_LINE = re.compile(
    r"^\s*SF-(?:Case|Opp)-.*$",
    re.IGNORECASE | re.MULTILINE,
)


def _line_is_signature_signal(line: str) -> str:
    """
    Check if a line looks like a signature element.
    Returns signal type string or empty string.
    """
    stripped = line.strip()
    if not stripped:
        return ""

    # Phone with label
    if PHONE_PATTERN.match(line):
        return "phone"

    # Bare phone number
    if BARE_PHONE_PATTERN.match(line):
        return "phone"

    # Line is just an email address
    if EMAIL_ADDR_PATTERN.fullmatch(stripped):
        return "email"

    # Line contains a URL
    if URL_PATTERN.search(stripped):
        return "url"

    # Line contains address patterns
    if ADDRESS_PATTERN.search(stripped):
        # Only if the line is short (addresses in signatures tend to be compact)
        if len(stripped) < 120:
            return "address"

    # Line looks like a job title (short line with role keyword)
    stripped_lower = stripped.lower()
    if len(stripped) < 80:
        for role in SIGNATURE_ROLE_KEYWORDS:
            if re.search(r'\b' + re.escape(role) + r'\b', stripped_lower):
                return "role"

    return ""


def strip_signature(body: str, signature_markers: List[str]) -> str:
    """
    Remove signature block from email body.
    Uses two-pass detection:
    1. Traditional marker-based detection (Best regards, --, etc.)
    2. Multi-signal heuristic: If 3+ signature signals found in consecutive
       lines near the bottom, treat that as a signature block.
    """
    if not body:
        return body

    lines = body.split("\n")
    sig_patterns = _build_signature_patterns(signature_markers)

    # ── Pass 1: Traditional marker-based scan ──
    # Only look in the last 50% of the email
    cutoff_start = max(0, int(len(lines) * 0.5))
    best_cut = len(lines)

    for i in range(len(lines) - 1, cutoff_start - 1, -1):
        line = lines[i]
        for pattern in sig_patterns:
            if pattern.search(line):
                best_cut = i
                break
        # Also check for labeled phone patterns in signature area
        if PHONE_PATTERN.search(line) and i > cutoff_start:
            if best_cut == len(lines):
                best_cut = i

    if best_cut < len(lines):
        lines = lines[:best_cut]

    # ── Pass 2: Multi-signal heuristic ──
    # Scan the last 15 lines for signature-like signals
    scan_start = max(0, len(lines) - 15)
    signals = []  # list of (line_index, signal_type)

    for i in range(scan_start, len(lines)):
        sig = _line_is_signature_signal(lines[i])
        if sig:
            signals.append((i, sig))

    # If 3+ different signal types found, cut at the first signal
    if len(signals) >= 3:
        signal_types = set(s[1] for s in signals)
        if len(signal_types) >= 2:
            first_signal_idx = signals[0][0]
            lines = lines[:first_signal_idx]

    # ── Pass 3: Hard cutoff — strip trailing non-engineering lines ──
    # If the last 8+ lines have no substance, trim them
    if len(lines) > 10:
        trailing_empty = 0
        for i in range(len(lines) - 1, max(0, len(lines) - 10) - 1, -1):
            stripped = lines[i].strip()
            if not stripped or len(stripped) < 5:
                trailing_empty += 1
            else:
                break
        if trailing_empty >= 5:
            lines = lines[:len(lines) - trailing_empty]

    return "\n".join(lines).rstrip()


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


def strip_salesforce_refs(body: str) -> str:
    """
    Remove Salesforce reference numbers and threading identifiers from email body.
    These cause false-positive spec extraction (case numbers matched as dimensions, etc.).
    """
    if not body:
        return body

    # Remove SF threading refs: ref:_00DXXXX._XXXXX:ref
    body = SF_REF_THREAD.sub("", body)

    # Remove bracket-enclosed refs: [ ref:00012345 ]
    body = SF_REF_BRACKET.sub("", body)

    # Remove Case/Ref/Ticket number lines: Case#00012345
    body = SF_CASE_REF.sub("", body)

    # Remove SF source markers
    body = SF_SOURCE_LINE.sub("", body)

    return body


def strip_calendar_blocks(body: str) -> str:
    """Remove calendar invitation blocks from email body."""
    if not body:
        return body
    for pattern in CALENDAR_PATTERNS:
        body = pattern.sub("", body)
    return body


def strip_auto_replies(body: str) -> str:
    """Remove auto-reply/out-of-office footer text."""
    if not body:
        return body
    for pattern in AUTO_REPLY_PATTERNS:
        body = pattern.sub("", body)
    return body


def clean_email_body(
    body: str,
    signature_markers: List[str],
    disclaimer_phrases: List[str],
) -> str:
    """
    Full cleaning pipeline for an email body:
    1. Strip forwarded headers
    2. Strip Salesforce reference numbers
    3. Strip calendar blocks
    4. Strip auto-reply footers
    5. Strip disclaimer paragraphs
    6. Strip signature block (multi-signal)
    7. Normalize whitespace
    """
    if not body:
        return ""

    cleaned = strip_forwarded_headers(body)
    cleaned = strip_salesforce_refs(cleaned)
    cleaned = strip_calendar_blocks(cleaned)
    cleaned = strip_auto_replies(cleaned)
    cleaned = strip_disclaimer(cleaned, disclaimer_phrases)
    cleaned = strip_signature(cleaned, signature_markers)

    # Normalize: collapse 3+ newlines to 2, strip trailing whitespace per line
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    lines = [line.rstrip() for line in cleaned.split("\n")]
    cleaned = "\n".join(lines).strip()

    return cleaned

