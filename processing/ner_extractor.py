"""
ner_extractor.py — spaCy NER-based engineering specification extraction.
Uses Named Entity Recognition + dependency parsing to find specs that
regex alone would miss (natural language, ranges, separated value+unit).
Falls back gracefully if spaCy is not installed.
"""

import re
from typing import List, Optional, Tuple
from processing.spec_extractor import SpecRecord, _get_sentence_context, _extract_subject

try:
    import spacy
    _NLP = None  # lazy-loaded

    def _get_nlp():
        global _NLP
        if _NLP is None:
            try:
                _NLP = spacy.load("en_core_web_sm")
            except OSError:
                print("[WARN] spaCy model 'en_core_web_sm' not found. "
                      "Run: python -m spacy download en_core_web_sm")
                return None
        return _NLP

    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False

    def _get_nlp():
        return None


# Engineering unit mapping: token -> (category, full_unit)
UNIT_MAP = {
    # Dimensions
    "mm": ("Dimensions", "mm"), "cm": ("Dimensions", "cm"),
    "m": ("Dimensions", "m"), "inch": ("Dimensions", "inch"),
    "inches": ("Dimensions", "inches"), "in": ("Dimensions", "in"),
    "ft": ("Dimensions", "ft"), "feet": ("Dimensions", "feet"),
    # Torque
    "nm": ("Torque", "Nm"), "knm": ("Torque", "kNm"),
    # Speed
    "rpm": ("Speed/RPM", "RPM"), "rev/min": ("Speed/RPM", "rev/min"),
    # Power
    "kw": ("Power", "kW"), "mw": ("Power", "MW"),
    "hp": ("Power", "HP"), "bhp": ("Power", "bhp"),
    "w": ("Power", "W"),
    # Pressure
    "bar": ("Pressure", "bar"), "psi": ("Pressure", "psi"),
    "pa": ("Pressure", "Pa"), "kpa": ("Pressure", "kPa"),
    "mpa": ("Pressure", "MPa"), "atm": ("Pressure", "atm"),
    # Temperature
    "°c": ("Temperature", "°C"), "°f": ("Temperature", "°F"),
    "degc": ("Temperature", "degC"), "degf": ("Temperature", "degF"),
    # Voltage
    "kv": ("Voltage", "kV"), "mv": ("Voltage", "mV"),
    "v": ("Voltage", "V"), "vac": ("Voltage", "VAC"),
    "vdc": ("Voltage", "VDC"),
    # Current
    "a": ("Current", "A"), "ma": ("Current", "mA"),
    "ka": ("Current", "kA"), "amps": ("Current", "Amps"),
    # Weight
    "kg": ("Weight/Mass", "kg"), "g": ("Weight/Mass", "g"),
    "lbs": ("Weight/Mass", "lbs"), "lb": ("Weight/Mass", "lb"),
    "tonnes": ("Weight/Mass", "tonnes"), "tons": ("Weight/Mass", "tons"),
    # Tolerance
    "µm": ("Tolerance", "µm"), "micron": ("Tolerance", "micron"),
    # Surface
    "ra": ("Surface Finish", "Ra"), "rz": ("Surface Finish", "Rz"),
}

# Regex for numeric values (including ranges and ±)
NUMERIC_PATTERN = re.compile(
    r'(-?\d+(?:\.\d+)?)'                    # Single number
    r'(?:\s*[-–to/]\s*(\d+(?:\.\d+)?))?'    # Optional range end
    r'(?:\s*[±]\s*(\d+(?:\.\d+)?))?'        # Optional tolerance
)

# Words that commonly separate a number from its unit in engineering text
CONNECTOR_WORDS = {"of", "is", "are", "at", "to", "be", "approximately", "approx", "about", "around", "roughly"}


def _find_unit_near_number(doc, num_token_idx: int, window: int = 5) -> Optional[Tuple[str, str]]:
    """
    Look for an engineering unit within `window` tokens of a numeric token.
    Returns (category, unit) or None.
    """
    for offset in range(1, min(window + 1, len(doc) - num_token_idx)):
        token = doc[num_token_idx + offset]
        token_lower = token.text.lower().strip()

        # Skip connector words
        if token_lower in CONNECTOR_WORDS:
            continue

        # Check if this token is a known unit
        if token_lower in UNIT_MAP:
            return UNIT_MAP[token_lower]

        # Check combined with next token (e.g., "°" + "C")
        if offset + 1 < len(doc) - num_token_idx:
            combined = token_lower + doc[num_token_idx + offset + 1].text.lower()
            if combined in UNIT_MAP:
                return UNIT_MAP[combined]

        # Stop at sentence boundaries or non-connector non-unit words
        if token.is_punct and token.text in ".!?\n":
            break
        if not token.is_punct and token_lower not in CONNECTOR_WORDS and token_lower not in UNIT_MAP:
            # Allow one non-unit word (e.g., "30 mm diameter" — "diameter" between)
            if offset > 2:
                break

    return None


def _find_subject_via_dep(doc, num_token_idx: int) -> str:
    """
    Use dependency parsing to find what a numeric value refers to.
    Looks for the noun that governs or is governed by the number.
    """
    token = doc[num_token_idx]

    # Check head of the number
    if token.head and token.head.pos_ in ("NOUN", "PROPN"):
        return token.head.text.capitalize()

    # Check siblings (other children of the same head)
    if token.head:
        for child in token.head.children:
            if child.pos_ in ("NOUN", "PROPN") and child.i != num_token_idx:
                return child.text.capitalize()

    # Check left context for nearest noun
    for i in range(num_token_idx - 1, max(0, num_token_idx - 6), -1):
        if doc[i].pos_ in ("NOUN", "PROPN"):
            return doc[i].text.capitalize()

    return ""


def extract_specs_ner(
    text: str,
    sender_name: str = "",
    sender_email: str = "",
    date_str: str = "",
    source_file: str = "",
) -> List[SpecRecord]:
    """
    Extract engineering specs using spaCy NER + dependency parsing.
    Catches specs that regex misses (e.g., "The shaft should be at least 30 mm").
    Returns empty list if spaCy is not available.
    """
    nlp = _get_nlp()
    if nlp is None:
        return []

    specs = []
    seen = set()

    # Process text in chunks to handle large emails
    max_len = nlp.max_length
    chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]

    for chunk in chunks:
        try:
            doc = nlp(chunk)
        except Exception:
            continue

        for token in doc:
            # Look for numeric tokens
            if not token.like_num:
                continue

            # Try to find a unit near this number
            unit_info = _find_unit_near_number(doc, token.i)
            if unit_info is None:
                continue

            category, unit = unit_info
            value = token.text

            # Handle ranges: check if next token is a range separator
            raw_match = value
            if token.i + 2 < len(doc):
                next_tok = doc[token.i + 1]
                next_next = doc[token.i + 2]
                if next_tok.text in ("-", "–", "to", "/") and next_next.like_num:
                    raw_match = f"{value}{next_tok.text}{next_next.text}"
                    value = f"{value}-{next_next.text}"

            raw_match = f"{raw_match} {unit}"

            # Dedup
            key = (category, raw_match.lower())
            if key in seen:
                continue
            seen.add(key)

            # Get context and subject
            char_start = token.idx
            char_end = char_start + len(raw_match)
            context = _get_sentence_context(chunk, char_start, char_end)

            # Try dependency parsing for subject, fall back to keyword matching
            subject = _find_subject_via_dep(doc, token.i)
            if not subject:
                subject = _extract_subject(context, value)

            specs.append(SpecRecord(
                category=category,
                raw_match=raw_match,
                value=str(value),
                unit=unit,
                subject=subject,
                context=context,
                mentioned_by=sender_name,
                mentioned_email=sender_email,
                date_str=date_str,
                source_file=source_file,
            ))

    return specs


def extract_all_specs_hybrid(
    text: str,
    material_keywords: List[str],
    sender_name: str = "",
    sender_email: str = "",
    date_str: str = "",
    source_file: str = "",
) -> List[SpecRecord]:
    """
    Hybrid extraction: Regex (precision) + NER (recall).
    Merges results, deduplicating by (category, value, unit).
    """
    from processing.spec_extractor import extract_all_specs

    # Get regex results (always available)
    regex_specs = extract_all_specs(
        text, material_keywords, sender_name, sender_email, date_str, source_file
    )

    # Get NER results (only if spaCy available)
    ner_specs = extract_specs_ner(
        text, sender_name, sender_email, date_str, source_file
    )

    if not ner_specs:
        return regex_specs

    # Merge: regex results take priority, NER fills gaps
    seen = set()
    for spec in regex_specs:
        key = (spec.category, spec.value.lower(), spec.unit.lower())
        seen.add(key)

    merged = list(regex_specs)
    for spec in ner_specs:
        key = (spec.category, spec.value.lower(), spec.unit.lower())
        if key not in seen:
            seen.add(key)
            merged.append(spec)

    return merged
