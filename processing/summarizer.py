"""
summarizer.py — Generate a comprehensive engineering summary.
Produces a professional, detail-rich report from extracted email data.
"""

from typing import Any, List, Dict
from collections import defaultdict


def generate_summary(
    emails: List[Any],
    specs: List[Any],
    people: List[Dict],
    unresolved: List[Any],
    timeline: List[Dict]
) -> str:
    """
    Generate a comprehensive, engineering-grade executive summary.
    """
    if not emails:
        return "No emails were analyzed."

    summary = []

    # ── Overview ──
    summary.append("## Executive Summary\n")

    # Thread overview
    subjects = list(set([e.subject for e in emails if e.subject]))
    subject_line = subjects[0] if len(subjects) == 1 else f"{len(subjects)} topics"
    summary.append(
        f"**Thread:** {subject_line}  \n"
        f"**Emails:** {len(emails)} &nbsp;|&nbsp; "
        f"**Participants:** {len(people)} &nbsp;|&nbsp; "
        f"**Specs Found:** {len(specs)} &nbsp;|&nbsp; "
        f"**Open Items:** {len(unresolved)}\n"
    )

    # Companies involved
    companies = list(set([p.get("company", "") for p in people if p.get("company")]))
    if companies:
        summary.append(f"**Organizations:** {', '.join(companies)}\n")

    # ── Specifications Breakdown ──
    if specs:
        summary.append("### Key Specifications\n")

        # Group by category
        by_cat = defaultdict(list)
        for s in specs:
            by_cat[s.category].append(s)

        for category, items in by_cat.items():
            entries = []
            seen = set()
            for s in items:
                subject = getattr(s, 'subject', '') or ''
                val = f"{s.value} {s.unit}".strip()
                label = f"{subject}: **{val}**" if subject else f"**{val}**"

                # Dedup
                key = f"{subject}_{val}".lower()
                if key not in seen:
                    seen.add(key)
                    entries.append(label)

            summary.append(f"- **{category}:** {' · '.join(entries)}")

        summary.append("")

    # ── Key Participants ──
    if people:
        active_people = [p for p in people if p.get("emails_sent", 0) > 0]
        if active_people:
            summary.append("### Participants\n")
            for p in sorted(active_people, key=lambda x: x.get("emails_sent", 0), reverse=True):
                name = p.get("name", "Unknown")
                company = p.get("company", "")
                role = p.get("role", "")
                sent = p.get("emails_sent", 0)
                specs_list = p.get("specs_mentioned", [])
                spec_count = len(specs_list) if isinstance(specs_list, list) else 0

                parts = [f"**{name}**"]
                if company:
                    parts.append(f"({company})")
                if role:
                    parts.append(f"— {role}")
                parts.append(f"— {sent} email(s)")
                if spec_count > 0:
                    parts.append(f", mentioned {spec_count} spec(s)")

                summary.append(f"- {' '.join(parts)}")
            summary.append("")

    # ── Unresolved / Action Items ──
    if unresolved:
        summary.append(f"### ⚠️ Action Items ({len(unresolved)})\n")
        for idx, item in enumerate(unresolved[:5], 1):
            sentence = item.sentence[:150] + "..." if len(item.sentence) > 150 else item.sentence
            flags = ', '.join(item.trigger_keywords) if item.trigger_keywords else '—'
            summary.append(
                f"{idx}. *\"{sentence}\"*  \n"
                f"   → **{item.mentioned_by}** | Flags: {flags}"
            )
        if len(unresolved) > 5:
            summary.append(f"\n... and {len(unresolved) - 5} more open items.")
        summary.append("")
    else:
        summary.append("### ✅ No Open Items\nAll items appear resolved.\n")

    # ── Timeline ──
    if timeline:
        first_date = timeline[0].get("date", "?")
        last_date = timeline[-1].get("date", "?")
        summary.append(f"### Timeline\nDiscussion spans from **{first_date}** to **{last_date}**, "
                       f"with **{len(timeline)}** engineering events logged.")

    return "\n".join(summary)
