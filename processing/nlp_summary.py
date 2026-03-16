"""
nlp_summary.py — Python-native extractive summarizer for engineering email threads.
Uses sentence scoring based on term frequency and engineering keyword weighting.
No external LLM or API required.
"""

import re
from collections import Counter
from typing import Any, List, Dict


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

# Common stop words to ignore during scoring
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "don", "now", "and", "but", "or", "if", "while", "this", "that",
    "these", "those", "i", "me", "my", "we", "our", "you", "your", "he",
    "him", "his", "she", "her", "it", "its", "they", "them", "their",
    "what", "which", "who", "whom", "am", "up", "about",
}


def _tokenize(text: str) -> List[str]:
    """Split text into lowercase word tokens."""
    return re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)*", text.lower())


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences."""
    sentences = re.split(r'(?<=[.!?])\s+|\n+', text)
    return [s.strip() for s in sentences if len(s.strip()) > 15]


def _compute_word_frequencies(words: List[str]) -> Dict[str, float]:
    """Compute normalized word frequencies, excluding stop words."""
    filtered = [w for w in words if w not in STOP_WORDS and len(w) > 1]
    freq = Counter(filtered)
    if not freq:
        return {}
    max_freq = max(freq.values())
    return {word: count / max_freq for word, count in freq.items()}


def _score_sentence(sentence: str, word_freqs: Dict[str, float], boost_factor: float = 2.0) -> float:
    """Score a sentence based on word frequency and engineering keyword boost."""
    words = _tokenize(sentence)
    if not words:
        return 0.0

    score = 0.0
    for word in words:
        base_score = word_freqs.get(word, 0.0)
        if word in ENGINEERING_BOOST_WORDS:
            base_score = max(base_score, 0.3) * boost_factor
        score += base_score

    # Normalize by sentence length (prefer medium-length sentences)
    length = len(words)
    if length < 5:
        score *= 0.5  # Penalize very short sentences
    elif length > 40:
        score *= 0.8  # Slightly penalize very long sentences

    return score / max(length, 1)


def generate_extractive_summary(
    emails: List[Any],
    specs: List[Any],
    people: List[Dict],
    unresolved: List[Any],
    top_n: int = 8,
) -> str:
    """
    Generate an extractive summary from the email thread.
    Picks the top N most informative sentences based on term frequency
    and engineering keyword weighting.
    """
    if not emails:
        return "No emails were provided for summarization."

    # ── Build the full corpus ──
    all_text = "\n".join([e.body for e in emails if e.body])
    all_sentences = _split_sentences(all_text)

    if not all_sentences:
        return "Could not extract meaningful sentences from the emails."

    # ── Compute word frequencies across the entire corpus ──
    all_words = _tokenize(all_text)
    word_freqs = _compute_word_frequencies(all_words)

    # ── Score each sentence ──
    scored = [(sent, _score_sentence(sent, word_freqs)) for sent in all_sentences]
    scored.sort(key=lambda x: x[1], reverse=True)

    # ── Pick top N unique sentences ──
    seen = set()
    selected = []
    for sent, score in scored:
        # Simple dedup: skip if too similar to already selected
        sent_lower = sent.lower().strip()
        if sent_lower in seen:
            continue
        # Check for near-duplicate (>80% word overlap)
        sent_words = set(_tokenize(sent))
        is_dup = False
        for prev in selected:
            prev_words = set(_tokenize(prev))
            if len(sent_words & prev_words) / max(len(sent_words | prev_words), 1) > 0.8:
                is_dup = True
                break
        if is_dup:
            continue

        seen.add(sent_lower)
        selected.append(sent)
        if len(selected) >= top_n:
            break

    # ── Build the summary ──
    summary_parts = []

    # Header
    participant_names = [p.get("name", "Unknown") for p in people[:5]]
    companies = list(set([p.get("company", "") for p in people if p.get("company")]))

    summary_parts.append("### 🔍 Extractive Summary\n")
    summary_parts.append(
        f"Analyzed **{len(emails)} email(s)** involving **{len(people)} participant(s)**"
        + (f" from **{', '.join(companies[:3])}**." if companies else ".")
    )

    # Spec overview
    if specs:
        categories = list(set([s.category for s in specs]))
        summary_parts.append(
            f"\n**{len(specs)} engineering specification(s)** were extracted across "
            f"categories: {', '.join(categories[:6])}."
        )

    # Key sentences
    if selected:
        summary_parts.append("\n**Key statements from the thread:**\n")
        for i, sent in enumerate(selected, 1):
            # Truncate overly long sentences
            display = sent[:250] + "..." if len(sent) > 250 else sent
            summary_parts.append(f"{i}. {display}")

    # Unresolved items callout
    if unresolved:
        summary_parts.append(
            f"\n⚠️ **{len(unresolved)} unresolved item(s)** require attention or confirmation."
        )

    return "\n".join(summary_parts)
