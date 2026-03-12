"""
sentence_tagger.py — Extract engineering-relevant sentences using keyword triggers.
"""

import re
from dataclasses import dataclass
from typing import List


@dataclass
class TaggedSentence:
    """A sentence flagged as engineering-relevant."""
    sentence: str
    context: str           # sentence + 1 before + 1 after
    trigger_keywords: List[str]  # which keywords triggered the match
    is_unresolved: bool = False  # contains ?, TBD, confirm, etc.
    mentioned_by: str = ""
    mentioned_email: str = ""
    date_str: str = ""
    source_file: str = ""


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
    Extract sentences containing engineering keywords.
    For each match, includes 1 sentence before and 1 after for context.
    Also flags 'unresolved' sentences.
    """
    if not text:
        return []

    sentences = _split_sentences(text)
    tagged = []
    seen_indices = set()  # avoid tagging the same sentence twice

    for i, sentence in enumerate(sentences):
        sent_lower = sentence.lower()

        # Check for engineering keywords
        found_keywords = []
        for kw in engineering_keywords:
            if kw.lower() in sent_lower:
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

        # Check if unresolved
        is_unresolved = False
        for marker in unresolved_markers:
            if marker.lower() in sent_lower:
                is_unresolved = True
                break

        tagged.append(TaggedSentence(
            sentence=sentence,
            context=context,
            trigger_keywords=found_keywords,
            is_unresolved=is_unresolved,
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
) -> List[TaggedSentence]:
    """
    Specifically extract sentences that contain unresolved markers.
    These may or may not also contain engineering keywords.
    """
    if not text:
        return []

    sentences = _split_sentences(text)
    unresolved = []
    seen = set()

    for i, sentence in enumerate(sentences):
        sent_lower = sentence.lower()

        for marker in unresolved_markers:
            if marker.lower() in sent_lower:
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
