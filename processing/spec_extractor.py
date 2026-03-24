"""
spec_extractor.py — Regex rule engine for extracting engineering specifications.
Includes pre-extraction filtering to remove Salesforce refs, phone numbers,
and post-extraction validation to reject false positives.
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
    subject: str = ""      # what the spec refers to (e.g. "bore", "shaft")
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
    # ── Coupling Style / Model ──
    (
        "Coupling Style",
        re.compile(
            r"\b((?:RMS|RZS|RM|RZ|MP|MS)\s*\d{2,4}(?:\s*[A-Z]{0,3})?)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Roughness / Surface Finish ──
    (
        "Surface Finish",
        re.compile(
            r"(\d+(?:\.\d+)?)\s*(Ra|Rz|µm|RMS|rms|micro[\s-]?inch)",
            re.IGNORECASE,
        ),
    ),
    # ── Interference / Fit ──
    (
        "Fit/Interference",
        re.compile(
            r"([HhKkMmNnPpRrSsTtUu]\d{1,2}\s*/\s*[a-z]\d{1,2}|(?:H7|H6|H8|k6|m6|n6|p6|js6|g6|f7|e8)\b)",
            re.IGNORECASE,
        ),
    ),
    # ── Bore / Hub Bore (coupling specific) ──
    (
        "Hub Bore",
        re.compile(
            r"(?:hub|bore|coupling)\s*(?:bore|diameter|dia|size)?\s*(?:[:=]|is|of)?\s*(\d+(?:\.\d+)?)\s*(mm|inch|in)?",
            re.IGNORECASE,
        ),
    ),
]


# ═══════════════════════════════════════════════════════════════
#  SKIP PATTERNS — Things that look like specs but aren't
# ═══════════════════════════════════════════════════════════════

# Phone number patterns (with or without labels)
SKIP_PHONE = re.compile(
    r"(?:Tel|Phone|Mobile|Cell|Mob|Fax|Ph|T|M|F)\s*[:.]"
    r"\s*[\+\d\(\)\-\s]{7,}"
    r"|[\+]?\d[\d\s\-\(\)]{8,}",
    re.IGNORECASE,
)

# Salesforce / CRM reference patterns
SKIP_SF_REFS = re.compile(
    r"ref:_[a-zA-Z0-9]+\._[a-zA-Z0-9]+:ref"  # SF threading ref
    r"|\[\s*ref:\s*[a-zA-Z0-9_.\-]+\s*\]"      # [ref:XXXX]
    r"|(?:Case|Ref|Reference|Ticket|Opp)\s*[#:.\-]\s*\d{5,}"  # Case#00012345
    r"|SF-(?:Case|Opp)-\S+",                    # SF-Case-00012345
    re.IGNORECASE,
)

# Standalone large numbers (5+ digits, no unit nearby) — likely IDs not specs
SKIP_STANDALONE_ID = re.compile(r"\b\d{8,}\b")

# PIN codes / postal codes (5-6 digit numbers preceded by PIN/zip context)
SKIP_PIN_CODE = re.compile(
    r"(?:pin|zip|postal)\s*[:.\-]?\s*\d{5,6}"
    r"|\b\d{6}\b(?=\s*(?:india|us|uk|$))",
    re.IGNORECASE,
)

# Context words that indicate a number is a reference, not a spec
REFERENCE_CONTEXT_WORDS = {
    "case", "reference", "ref", "ticket", "opportunity", "record",
    "order", "invoice", "po", "purchase order", "quotation", "quote",
    "enquiry", "inquiry", "id", "number", "no.",
}


def _pre_filter_text(text: str) -> str:
    """
    Remove known non-spec patterns from text BEFORE regex extraction runs.
    This prevents SF refs, phone numbers, and IDs from being matched as specs.
    """
    if not text:
        return text

    # Remove SF reference patterns
    text = SKIP_SF_REFS.sub("", text)

    # Remove standalone phone number lines
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip lines that are purely phone numbers
        if stripped and re.match(r'^[\+\d\(\)\-\s]{7,}$', stripped):
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def _is_false_positive(category: str, raw_match: str, value: str,
                        unit: str, context: str) -> bool:
    """
    Check if an extracted spec is actually a false positive.
    Returns True if the spec should be rejected.
    """
    context_lower = context.lower()
    value_str = str(value).strip()

    # Reject if the context contains reference/ticket/case words near the value
    for ref_word in REFERENCE_CONTEXT_WORDS:
        if ref_word in context_lower:
            # Check proximity: ref word should be within 50 chars of the value
            ref_idx = context_lower.find(ref_word)
            val_idx = context_lower.find(value_str.lower())
            if ref_idx != -1 and val_idx != -1 and abs(ref_idx - val_idx) < 50:
                return True

    # Reject standalone numbers with 5+ digits and no unit (likely IDs)
    if not unit and value_str.isdigit() and len(value_str) >= 5:
        return True

    # Reject if the raw match looks like a phone number
    if SKIP_PHONE.search(raw_match):
        return True

    # Reject PIN/postal codes
    if SKIP_PIN_CODE.search(context):
        if value_str.isdigit() and 5 <= len(value_str) <= 6:
            return True

    return False


SUBJECT_KEYWORDS = [
    # General engineering
    "bore", "shaft", "flange", "diameter", "length", "width", "height",
    "thickness", "clearance", "pitch", "head", "weight", "mass", "pressure",
    "temperature", "voltage", "current", "torque", "speed", "power",
    "tolerance", "thread", "bolt", "material", "stroke", "capacity", "depth",
    "flow", "volume", "radius",
    # Coupling-specific
    "coupling", "hub", "spacer", "sleeve", "disc", "diaphragm", "guard",
    "interference", "keyway", "key", "setscrew", "clamping", "taper",
    "roughness", "finish", "surface", "runout", "concentricity",
    "alignment", "misalignment", "angular", "parallel", "axial",
    "rubber", "element", "insert", "spider", "jaw",
    "driven", "driver", "motor", "pump", "gearbox", "compressor",
]


def _extract_subject(context: str, match_value: str) -> str:
    """Find the most likely subject in the context sentence for the matched value."""
    if not context:
        return ""
        
    context_lower = context.lower()
    found_subjects = []
    
    for kw in SUBJECT_KEYWORDS:
        idx = context_lower.find(kw)
        if idx != -1:
            found_subjects.append((idx, kw))
            
    if not found_subjects:
        return ""
        
    value_idx = context_lower.find(match_value.lower())
    if value_idx != -1:
        # Sort by absolute distance to the value
        found_subjects.sort(key=lambda x: abs(x[0] - value_idx))
    else:
        # Fallback to sorting by appearance
        found_subjects.sort()
        
    return found_subjects[0][1].capitalize()


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
    Includes pre-filtering to remove SF refs and post-validation to reject
    false positives like phone numbers, case IDs, and postal codes.
    """
    # Pre-filter: remove known non-spec patterns before extraction
    filtered_text = _pre_filter_text(text)

    specs = []
    seen_matches = set()  # avoid duplicate matches within the same email

    for category, pattern in SPEC_PATTERNS:
        for match in pattern.finditer(filtered_text):
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

            context = _get_sentence_context(filtered_text, match.start(), match.end())
            subject = _extract_subject(context, str(value))

            # Post-extraction validation: reject false positives
            if _is_false_positive(category, raw, str(value), unit, context):
                continue

            specs.append(SpecRecord(
                category=category,
                raw_match=raw,
                value=str(value),
                unit=unit or "",
                subject=subject,
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
            subject = _extract_subject(context, material)

            specs.append(SpecRecord(
                category="Material",
                raw_match=material,
                value=material,
                unit="",
                subject=subject,
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
