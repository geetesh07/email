"""
nlp_summary.py — Python-native extractive summarizer for engineering email threads.
Uses TextRank graph-based ranking + engineering keyword weighting.
Produces structured, coherent summaries with section-based output.
No external LLM or API required.
"""

import re
from collections import Counter
from typing import Any, List, Dict

from processing.textrank import select_top_sentences


# Engineering keywords get extra weight in sentence scoring
ENGINEERING_BOOST_WORDS = {
    # General engineering
    "bore", "shaft", "flange", "diameter", "length", "width", "height",
    "thickness", "clearance", "pitch", "torque", "rpm", "speed", "power",
    "pressure", "temperature", "voltage", "current", "weight", "mass",
    "tolerance", "thread", "bolt", "material", "stroke", "capacity",
    "depth", "flow", "volume", "radius", "load", "stress", "strain",
    "hardness", "tensile", "yield", "fatigue", "corrosion", "coating",
    "assembly", "machining", "casting", "forging", "welding", "drawing",
    "specification", "requirement", "approval", "confirm", "pending",
    "urgent", "deadline", "delivery", "schedule", "design", "review",
    "dimension", "mm", "cm", "inch", "kg", "nm", "kw", "bar", "psi",
    "mpa", "iso", "astm", "din", "ip", "ie", "ss316", "en8",
    # Coupling-specific
    "coupling", "hub", "spacer", "sleeve", "disc", "diaphragm", "guard",
    "interference", "keyway", "key", "setscrew", "clamping", "taper",
    "roughness", "finish", "surface", "runout", "concentricity",
    "alignment", "misalignment", "angular", "parallel", "axial",
    "rm", "mp", "ms", "rz", "rms", "rzs",
    "spider", "jaw", "insert", "element",
    "driven", "driver", "motor", "pump", "gearbox", "compressor",
}

# Decision/action keywords for identifying decision sentences
DECISION_WORDS = {
    "agreed", "decided", "confirmed", "approved", "selected", "chosen",
    "finalized", "accepted", "rejected", "cancelled", "proceed", "go ahead",
    "final", "concluded", "settled", "resolved",
}

# Pattern for sentences containing numeric specs
HAS_SPEC_PATTERN = re.compile(
    r'\d+(?:\.\d+)?\s*(?:mm|cm|m|kg|g|Nm|kW|HP|RPM|bar|psi|Pa|°|V|A|Hz)\b',
    re.IGNORECASE
)


def _tokenize(text: str) -> List[str]:
    """Split text into lowercase word tokens."""
    return re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)*", text.lower())


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences."""
    sentences = re.split(r'(?<=[.!?])\s+|\n+', text)
    return [s.strip() for s in sentences if len(s.strip()) > 15]


def _categorize_sentence(sentence: str) -> str:
    """Categorize a sentence for structured output."""
    sent_lower = sentence.lower()

    # Check for decision/action words
    for word in DECISION_WORDS:
        if word in sent_lower:
            return "decision"

    # Check for spec-containing sentences
    if HAS_SPEC_PATTERN.search(sentence):
        return "spec"

    # Check for questions/unresolved
    if "?" in sentence or "tbd" in sent_lower or "pending" in sent_lower:
        return "open_item"

    # Default: general discussion
    eng_word_count = sum(1 for w in _tokenize(sentence) if w in ENGINEERING_BOOST_WORDS)
    if eng_word_count >= 2:
        return "engineering"

    return "general"


def generate_extractive_summary(
    emails: List[Any],
    specs: List[Any],
    people: List[Dict],
    unresolved: List[Any],
    top_n: int = 10,
) -> str:
    """
    Generate a structured extractive summary from the email thread.
    Uses TextRank for sentence selection + categorization for structure.
    """
    if not emails:
        return "No emails were provided for summarization."

    # ── Build the full corpus ──
    all_text = "\n".join([e.body for e in emails if e.body])
    all_sentences = _split_sentences(all_text)

    if not all_sentences:
        return "Could not extract meaningful sentences from the emails."

    # ── Use TextRank to select top sentences ──
    selected = select_top_sentences(all_sentences, top_n=top_n)

    # ── Categorize selected sentences ──
    categorized: Dict[str, List[str]] = {
        "spec": [],
        "decision": [],
        "engineering": [],
        "open_item": [],
        "general": [],
    }
    for sent in selected:
        cat = _categorize_sentence(sent)
        categorized[cat].append(sent)

    # ── Build structured summary ──
    summary_parts = []

    # Header
    participant_names = [p.get("name", "Unknown") for p in people[:5]]
    companies = list(set([p.get("company", "") for p in people if p.get("company")]))

    summary_parts.append("### Extractive Summary\n")
    summary_parts.append(
        f"Analyzed **{len(emails)} email(s)** involving **{len(people)} participant(s)**"
        + (f" from **{', '.join(companies[:3])}**." if companies else ".")
    )

    # Spec overview
    if specs:
        categories = list(set([s.category for s in specs]))
        summary_parts.append(
            f"\n**{len(specs)} engineering specification(s)** extracted across "
            f"categories: {', '.join(categories[:6])}."
        )

    # Key specifications mentioned
    spec_sentences = categorized["spec"]
    if spec_sentences:
        summary_parts.append("\n**Key Specifications Discussed:**\n")
        for sent in spec_sentences[:4]:
            display = sent[:250] + "..." if len(sent) > 250 else sent
            summary_parts.append(f"- {display}")

    # Decisions made
    decision_sentences = categorized["decision"]
    if decision_sentences:
        summary_parts.append("\n**Decisions & Agreements:**\n")
        for sent in decision_sentences[:3]:
            display = sent[:250] + "..." if len(sent) > 250 else sent
            summary_parts.append(f"- {display}")

    # Engineering discussion
    eng_sentences = categorized["engineering"]
    if eng_sentences:
        summary_parts.append("\n**Engineering Discussion:**\n")
        for sent in eng_sentences[:3]:
            display = sent[:250] + "..." if len(sent) > 250 else sent
            summary_parts.append(f"- {display}")

    # General context (if no other categories filled)
    if not spec_sentences and not decision_sentences and not eng_sentences:
        general = categorized["general"]
        if general:
            summary_parts.append("\n**Key Statements:**\n")
            for sent in general[:4]:
                display = sent[:250] + "..." if len(sent) > 250 else sent
                summary_parts.append(f"- {display}")

    # Unresolved items callout
    if unresolved:
        summary_parts.append(
            f"\n**{len(unresolved)} unresolved item(s)** require attention or confirmation."
        )

    return "\n".join(summary_parts)
