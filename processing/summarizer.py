"""
summarizer.py — Provide an executive summary of the engineering email chain.
"""

from typing import List, Dict
from processing.spec_extractor import SpecRecord
from processing.sentence_tagger import TaggedSentence

def generate_summary(
    emails: List[object],
    specs: List[SpecRecord],
    people: List[Dict],
    unresolved: List[TaggedSentence],
    timeline: List[Dict]
) -> str:
    """
    Generate a text-based executive summary based on the extracted data.
    """
    if not emails:
        return "No emails were analyzed."

    summary = []
    
    # Overview
    summary.append("## Executive Summary\n")
    summary.append(f"This thread contains **{len(emails)} emails** exchanged between **{len(people)} participants**.")
    
    # Key Entities
    companies = list(set([p.get("company") for p in people if p.get("company")]))
    if len(companies) > 1:
        summary.append(f"The primary organizations involved appear to be: **{', '.join(companies)}**.\n")
    else:
        summary.append("\n")

    # Specifications
    if specs:
        summary.append("### Key Engineering Specifications Discussed")
        
        # Group specs by category
        specs_by_category = {}
        for s in specs:
            if s.category not in specs_by_category:
                specs_by_category[s.category] = []
            specs_by_category[s.category].append(s)
            
        for category, items in specs_by_category.items():
            # Get unique values for this category
            unique_vals = list(set([f"{i.value} {i.unit}".strip() for i in items]))
            summary.append(f"- **{category}**: {', '.join(unique_vals)}")
        summary.append("\n")

    # Unresolved Items
    if unresolved:
        summary.append("### ⚠️ Action Items & Pending Decisions")
        summary.append("The following items require confirmation or action:")
        for idx, item in enumerate(unresolved, 1):
            summary.append(f"{idx}. *\"{item.sentence}\"* (Flags: {', '.join(item.trigger_keywords)}) — Mentioned by **{item.mentioned_by}**")
        summary.append("\n")
    else:
        summary.append("### Action Items\nNo open items or pending decisions were detected.\n")

    # Timeline / Status
    if timeline:
        first_date = timeline[0].get("date", "Unknown Date")
        last_date = timeline[-1].get("date", "Unknown Date")
        summary.append("### Thread Info")
        summary.append(f"Discussion spans from **{first_date}** to **{last_date}**.")

    return "\n".join(summary)
