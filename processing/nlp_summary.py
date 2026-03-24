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
    top_n: int = 5,
) -> str:
    """
    Generate a structured Executive Summary.
    Uses structured extracted data (specs, action items) rather than purely
    extractive fragmented sentences to ensure high-quality English output.
    """
    if not emails:
        return "No emails were provided for summarization."

    # ── Header ──
    companies = list(set([p.get("company", "") for p in people if p.get("company") and p.get("company") != "Unknown"]))
    
    summary_parts = []
    summary_parts.append("### Executive Engineering Summary\n")
    
    company_str = f" across {len(companies)} organization(s) ({', '.join(companies[:3])})" if companies else ""
    summary_parts.append(
        f"This thread contains **{len(emails)} emails** actively discussing engineering specifications "
        f"with **{len(people)} participants**{company_str}."
    )

    # ── Key Specifications ──
    if specs:
        summary_parts.append("\n**📐 Finalized / Proposed Specifications:**")
        
        # Group specs by category
        from collections import defaultdict
        spec_groups = defaultdict(list)
        for s in specs:
            spec_groups[s.category].append(s)
            
        for cat, items in list(spec_groups.items())[:6]: # Show top 6 categories
            # Gather unique values for this category
            unique_vals = list({f"{s.value} {s.unit}".strip() for s in items if s.value})
            if not unique_vals:
                continue
            
            val_str = " | ".join(unique_vals)
            summary_parts.append(f"- **{cat}:** {val_str}")

    # ── Decisions & Central Statements ──
    # We still use TextRank just to find 1-2 central sentences that have decision words
    all_text = "\n".join([e.body for e in emails if e.body])
    all_sentences = _split_sentences(all_text)
    
    if all_sentences:
        selected = select_top_sentences(all_sentences, top_n=top_n*2)
        decision_sentences = [s for s in selected if _categorize_sentence(s) == "decision"]
        
        if decision_sentences:
            summary_parts.append("\n**🤝 Key Agreements & Statements:**")
            # Clean up the sentences a bit (remove > quotes, strip whitespace)
            for sent in decision_sentences[:2]:
                clean_sent = re.sub(r'^[>\s]+', '', sent)
                display = clean_sent[:200] + "..." if len(clean_sent) > 200 else clean_sent
                summary_parts.append(f"- \"{display}\"")

    # ── Action Items ──
    if unresolved:
        summary_parts.append("\n**⏳ Pending Action Items & Questions:**")
        
        # unresolved items are typically objects with .sentence and .mentioned_by
        for u in unresolved[:3]:
            # Clean up the sentence
            clean_q = re.sub(r'^[>\s]+', '', u.sentence)
            sender = getattr(u, 'mentioned_by', 'Unknown') or 'Unknown'
            summary_parts.append(f"- {clean_q} *(Asked by {sender})*")
            
        if len(unresolved) > 3:
            summary_parts.append(f"- *...and {len(unresolved) - 3} more unresolved item(s).*")
            
    if not specs and not unresolved and not decision_sentences:
        summary_parts.append("\n*No specific engineering parameters or action items were identified in this thread.*")

    return "\n".join(summary_parts)
