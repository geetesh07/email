"""
spec_extractor.py — Regex rule engine for extracting engineering specifications.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Dict


@dataclass
class SpecRecord:
    """A single extracted specification."""
    category: str          # e.g. "Torque", "Dimensions", "Temperature"
    raw_match: str         # exact text matched, e.g. "450 Nm"
    value: str             # numeric value, e.g. "450"
    unit: str              # unit string, e.g. "Nm"
    context: str = ""      # surrounding sentence
    mentioned_by: str = "" # who mentioned it
    mentioned_email: str = ""
    date_str: str = ""     # when it was mentioned
    source_file: str = ""


# ═══════════════════════════════════════════════════════════════
#  SPEC PATTERNS  — Each tuple: (category_name, compiled_regex)
# ═══════════════════════════════════════════════════════════════

SPEC_PATTERNS: List[tuple] = [
    # ── Dimensions ──
    (
        "Dimensions",
        re.compile(
            r"(\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?)\s*"
            r"(mm|cm|m|inch|inches|in|ft|feet|\")",
            re.IGNORECASE,
        ),
    ),
    # ── Torque ──
    (
        "Torque",
        re.compile(
            r"(\d+(?:\.\d+)?)\s*(Nm|N\.m|kNm|lb[\-\s]?ft|lbf\.ft|oz[\-\s]?in)",
            re.IGNORECASE,
        ),
    ),
    # ── Speed / RPM ──
    (
        "Speed/RPM",
        re.compile(
            r"(\d+(?:\.\d+)?)\s*(RPM|rpm|r/min|rad/s|rev/min)",
            re.IGNORECASE,
        ),
    ),
    # ── Power ──
    (
        "Power",
        re.compile(
            r"(\d+(?:\.\d+)?)\s*(kW|MW|HP|hp|bhp|W(?![a-zA-Z]))",
            re.IGNORECASE,
        ),
    ),
    # ── Pressure ──
    (
        "Pressure",
        re.compile(
            r"(\d+(?:\.\d+)?)\s*(bar|psi|Pa|kPa|MPa|atm)",
            re.IGNORECASE,
        ),
    ),
    # ── Temperature ──
    (
        "Temperature",
        re.compile(
            r"(-?\d+(?:\.\d+)?)\s*(°C|°F|degC|degF|deg\s*C|deg\s*F|\bK\b)",
            re.IGNORECASE,
        ),
    ),
    # ── Voltage ──
    (
        "Voltage",
        re.compile(
            r"(\d+(?:\.\d+)?)\s*(kV|mV|VAC|VDC|V(?![a-zA-Z]))",
            re.IGNORECASE,
        ),
    ),
    # ── Current ──
    (
        "Current",
        re.compile(
            r"(\d+(?:\.\d+)?)\s*(mA|kA|Amps?|A(?![a-zA-Z]))",
            re.IGNORECASE,
        ),
    ),
    # ── Weight / Mass ──
    (
        "Weight/Mass",
        re.compile(
            r"(\d+(?:\.\d+)?)\s*(kg|g(?!a)|lbs?|ton(?:ne)?s?)",
            re.IGNORECASE,
        ),
    ),
    # ── Tolerance ──
    (
        "Tolerance",
        re.compile(
            r"([±]\s*\d+(?:\.\d+)?|[+]\s*/\s*[-]\s*\d+(?:\.\d+)?)\s*(mm|%|µm|micron)",
            re.IGNORECASE,
        ),
    ),
    # ── Thread / Bolt ──
    (
        "Thread/Bolt",
        re.compile(
            r"(M\d+(?:\s*[×x]\s*\d+(?:\.\d+)?)?)",
            re.IGNORECASE,
        ),
    ),
    # ── Standards ──
    (
        "Standards",
        re.compile(
            r"(IS\s*\d+|ISO\s*\d+|ASTM\s*[A-Z]\d+|IP\s*\d+|NEMA\s*\d+|IEC\s*\d+|DIN\s*\d+|BS\s*\d+|EN\s*\d+)",
            re.IGNORECASE,
        ),
    ),
    # ── IP Rating ──
    (
        "IP Rating",
        re.compile(
            r"(IP\s*\d{2}(?:[A-Z])?)",
            re.IGNORECASE,
        ),
    ),
    # ── Efficiency Class ──
    (
        "Efficiency Class",
        re.compile(
            r"(IE[1-4]|EFF[1-3])",
            re.IGNORECASE,
        ),
    ),
]


def _get_sentence_context(text: str, match_start: int, match_end: int) -> str:
    """Extract the sentence containing or surrounding the match."""
    # Find sentence boundaries (rough: split on ., !, ?, newline)
    sentences = re.split(r"(?<=[.!?\n])\s+", text)
    pos = 0
    for sentence in sentences:
        sent_start = text.find(sentence, pos)
        if sent_start == -1:
            pos += len(sentence)
            continue
        sent_end = sent_start + len(sentence)
        if sent_start <= match_start < sent_end:
            return sentence.strip()
        pos = sent_end
    # Fallback: return a window around the match
    window = 100
    start = max(0, match_start - window)
    end = min(len(text), match_end + window)
    return text[start:end].strip()


def extract_specs_regex(
    text: str,
    sender_name: str = "",
    sender_email: str = "",
    date_str: str = "",
    source_file: str = "",
) -> List[SpecRecord]:
    """
    Run all regex patterns against the email text and return SpecRecords.
    """
    specs = []
    seen_matches = set()  # avoid duplicate matches within the same email

    for category, pattern in SPEC_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(0).strip()

            # Skip if we've already captured this exact match in this email
            match_key = (category, raw.lower())
            if match_key in seen_matches:
                continue
            seen_matches.add(match_key)

            # Extract value and unit
            groups = match.groups()
            value = groups[0] if groups else raw
            unit = groups[1] if len(groups) > 1 else ""

            # Handle Thread/Bolt special case (unit is empty)
            if category == "Thread/Bolt":
                value = raw
                unit = ""

            context = _get_sentence_context(text, match.start(), match.end())

            specs.append(SpecRecord(
                category=category,
                raw_match=raw,
                value=str(value),
                unit=unit or "",
                context=context,
                mentioned_by=sender_name,
                mentioned_email=sender_email,
                date_str=date_str,
                source_file=source_file,
            ))

    return specs


def extract_materials(
    text: str,
    material_keywords: List[str],
    sender_name: str = "",
    sender_email: str = "",
    date_str: str = "",
    source_file: str = "",
) -> List[SpecRecord]:
    """
    Extract material mentions from text using keyword matching.
    """
    specs = []
    text_lower = text.lower()
    seen = set()

    for material in material_keywords:
        mat_lower = material.lower()
        if mat_lower in text_lower and mat_lower not in seen:
            seen.add(mat_lower)

            # Find the position for context
            idx = text_lower.find(mat_lower)
            context = _get_sentence_context(text, idx, idx + len(material))

            specs.append(SpecRecord(
                category="Material",
                raw_match=material,
                value=material,
                unit="",
                context=context,
                mentioned_by=sender_name,
                mentioned_email=sender_email,
                date_str=date_str,
                source_file=source_file,
            ))

    return specs


def extract_all_specs(
    text: str,
    material_keywords: List[str],
    sender_name: str = "",
    sender_email: str = "",
    date_str: str = "",
    source_file: str = "",
) -> List[SpecRecord]:
    """
    Combined extraction: regex patterns + material keywords.
    """
    specs = extract_specs_regex(
        text, sender_name, sender_email, date_str, source_file
    )
    specs += extract_materials(
        text, material_keywords, sender_name, sender_email, date_str, source_file
    )
    return specs
