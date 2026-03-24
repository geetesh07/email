"""
sentence_tagger.py — Extract engineering-relevant sentences using keyword triggers.
Uses word-boundary matching to avoid false positives (e.g., "bore" won't match "bored").
Smart unresolved detection: questions flagged only if they contain engineering context.
"""

import re
from dataclasses import dataclass
from typing import List, Dict


@dataclass
class TaggedSentence:
    """A sentence flagged as engineering-relevant."""
    sentence: str
    context: str           # sentence + 1 before + 1 after
    trigger_keywords: List[str]  # which keywords triggered the match
    is_unresolved: bool = False  # contains ?, TBD, confirm, etc.
    confidence: float = 0.0     # confidence score (0.0 - 1.0)
    mentioned_by: str = ""
    mentioned_email: str = ""
    date_str: str = ""
    source_file: str = ""


# Pre-compiled word boundary patterns cache (built lazily)
_word_boundary_cache: Dict[str, re.Pattern] = {}


def _matches_word_boundary(keyword: str, text: str) -> bool:
    """
    Check if keyword appears in text as a whole word (word-boundary match).
    Prevents 'bore' from matching 'bored', 'key' from matching 'keyboard', etc.
    """
    if keyword not in _word_boundary_cache:
        # For multi-word keywords (e.g., "disc coupling"), match the phrase
        escaped = re.escape(keyword)
        _word_boundary_cache[keyword] = re.compile(
            r'\b' + escaped + r'\b', re.IGNORECASE
        )
    return bool(_word_boundary_cache[keyword].search(text))


# Patterns indicating a numeric/engineering value is present in a sentence
HAS_NUMERIC_VALUE = re.compile(r'\d+(?:\.\d+)?\s*(?:mm|cm|m|kg|g|Nm|kW|HP|RPM|bar|psi|Pa|°|V|A|Hz)\b', re.IGNORECASE)
HAS_ANY_NUMBER = re.compile(r'\b\d+(?:\.\d+)?\b')

# Greetings and pleasantries that contain "?" but aren't engineering questions
GREETING_PATTERNS = re.compile(
    r'^\s*(?:how are you|hope you are|how\'s it going|how do you do|'
    r'how have you been|good morning|good afternoon|good evening|'
    r'hi |hello |hey |dear |greetings|thanks|thank you|'
    r'hope this finds you|hope this email|how was your)',
    re.IGNORECASE,
)


def _compute_confidence(sentence: str, found_keywords: List[str]) -> float:
    """
    Compute a confidence score for how likely a sentence is genuinely
    engineering-relevant (0.0 - 1.0).
    """
    score = 0.0

    # Base score: number of engineering keywords found
    kw_count = len(found_keywords)
    score += min(kw_count * 0.2, 0.4)  # max 0.4 from keywords

    # Bonus: sentence contains a numeric value with unit
    if HAS_NUMERIC_VALUE.search(sentence):
        score += 0.35

    # Bonus: sentence contains any number at all
    elif HAS_ANY_NUMBER.search(sentence):
        score += 0.15

    # Bonus: multi-word keywords are more specific → higher confidence
    multi_word_kw = [kw for kw in found_keywords if ' ' in kw]
    if multi_word_kw:
        score += 0.1

    # Length penalty: very short sentences are less likely to be meaningful
    word_count = len(sentence.split())
    if word_count < 4:
        score *= 0.5
    elif word_count > 5:
        score += 0.05

    return min(score, 1.0)


def _split_sentences(text: str) -> List[str]:
    """
    Split text into sentences using punctuation and newline boundaries.
    Handles common abbreviations to avoid false splits.
    """
    # Protect common abbreviations from being split
    protected = text
    abbrevs = [
        "Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Sr.", "Jr.",
        "vs.", "etc.", "approx.", "i.e.", "e.g.", "Fig.", "fig.",
        "No.", "no.", "Ref.", "ref.", "Rev.", "rev.",
        "N.m", "lbf.ft",
    ]
    placeholders = {}
    for i, abbr in enumerate(abbrevs):
        placeholder = f"__ABBR{i}__"
        placeholders[placeholder] = abbr
        protected = protected.replace(abbr, placeholder)

    # Split on sentence-ending punctuation
    raw_sentences = re.split(r"(?<=[.!?])\s+|\n+", protected)

    # Restore abbreviations
    sentences = []
    for sent in raw_sentences:
        for placeholder, original in placeholders.items():
            sent = sent.replace(placeholder, original)
        sent = sent.strip()
        if sent:
            sentences.append(sent)

    return sentences


def _is_engineering_question(sentence: str, engineering_keywords: List[str]) -> bool:
    """
    Check if a question sentence is actually about engineering.
    Returns True only if the question contains an engineering keyword.
    This prevents "How are you?" from being flagged as unresolved.
    """
    for kw in engineering_keywords:
        if _matches_word_boundary(kw, sentence):
            return True
    return False


def tag_sentences(
    text: str,
    engineering_keywords: List[str],
    unresolved_markers: List[str],
    sender_name: str = "",
    sender_email: str = "",
    date_str: str = "",
    source_file: str = "",
) -> List[TaggedSentence]:
    """
    Extract sentences containing engineering keywords using word-boundary matching.
    For each match, includes 1 sentence before and 1 after for context.
    Also flags 'unresolved' sentences with smart question detection.
    """
    if not text:
        return []

    sentences = _split_sentences(text)
    tagged = []
    seen_indices = set()  # avoid tagging the same sentence twice

    for i, sentence in enumerate(sentences):
        # Check for engineering keywords using WORD-BOUNDARY matching
        found_keywords = []
        for kw in engineering_keywords:
            if _matches_word_boundary(kw, sentence):
                found_keywords.append(kw)

        if not found_keywords:
            continue

        if i in seen_indices:
            continue
        seen_indices.add(i)

        # Build context window: 1 before + current + 1 after
        context_parts = []
        if i > 0:
            context_parts.append(sentences[i - 1])
        context_parts.append(sentence)
        if i < len(sentences) - 1:
            context_parts.append(sentences[i + 1])
        context = " ".join(context_parts)

        # Compute confidence score
        confidence = _compute_confidence(sentence, found_keywords)

        # Check if unresolved — using smart detection
        is_unresolved = False
        sent_lower = sentence.lower()
        for marker in unresolved_markers:
            marker_lower = marker.lower()

            # Special handling for "?" — only flag if it's an engineering question
            if marker_lower == "?":
                if "?" in sentence and not GREETING_PATTERNS.search(sentence):
                    if _is_engineering_question(sentence, engineering_keywords):
                        is_unresolved = True
                        break
            else:
                # For text markers, use word-boundary matching
                if _matches_word_boundary(marker, sentence):
                    is_unresolved = True
                    break

        tagged.append(TaggedSentence(
            sentence=sentence,
            context=context,
            trigger_keywords=found_keywords,
            is_unresolved=is_unresolved,
            confidence=confidence,
            mentioned_by=sender_name,
            mentioned_email=sender_email,
            date_str=date_str,
            source_file=source_file,
        ))

    return tagged


def extract_unresolved(
    text: str,
    unresolved_markers: List[str],
    sender_name: str = "",
    sender_email: str = "",
    date_str: str = "",
    source_file: str = "",
    engineering_keywords: List[str] = None,  # type: ignore[assignment]
) -> List[TaggedSentence]:
    """
    Specifically extract sentences that contain unresolved markers.
    For "?" markers, only flags sentences that contain engineering keywords
    (prevents "How are you?" from being flagged).
    """
    if not text:
        return []

    # Default engineering keywords for question filtering
    if engineering_keywords is None:
        engineering_keywords = [
            "torque", "rpm", "speed", "load", "pressure", "bore", "shaft",
            "diameter", "dimension", "material", "tolerance", "coupling",
            "temperature", "voltage", "current", "power", "weight",
            "delivery", "drawing", "specification", "approval",
        ]

    sentences = _split_sentences(text)
    unresolved = []
    seen = set()

    for i, sentence in enumerate(sentences):
        sent_lower = sentence.lower()

        for marker in unresolved_markers:
            marker_lower = marker.lower()

            # Special handling for "?" — smart question detection
            if marker_lower == "?":
                if "?" not in sentence:
                    continue
                # Skip greetings / pleasantries
                if GREETING_PATTERNS.search(sentence):
                    continue
                # Only flag questions with engineering context
                if not _is_engineering_question(sentence, engineering_keywords):
                    continue
            else:
                # For text markers, use word-boundary matching
                if not _matches_word_boundary(marker, sentence):
                    continue

            if i in seen:
                break
            seen.add(i)

            # Build context
            context_parts = []
            if i > 0:
                context_parts.append(sentences[i - 1])
            context_parts.append(sentence)
            if i < len(sentences) - 1:
                context_parts.append(sentences[i + 1])
            context = " ".join(context_parts)

            unresolved.append(TaggedSentence(
                sentence=sentence,
                context=context,
                trigger_keywords=[marker],
                is_unresolved=True,
                mentioned_by=sender_name,
                mentioned_email=sender_email,
                date_str=date_str,
                source_file=source_file,
            ))
            break  # one marker is enough to flag it

    return unresolved
