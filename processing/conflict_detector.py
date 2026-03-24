"""
conflict_detector.py — Detect conflicting specifications in email threads.
When two people mention different values for the same spec subject+category,
this flags it as a conflict that needs resolution.
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple
from collections import defaultdict


@dataclass
class ConflictRecord:
    """A detected conflict between two specifications."""
    category: str         # e.g., "Dimensions"
    subject: str          # e.g., "bore"
    spec_a_value: str     # First value
    spec_a_unit: str
    spec_a_by: str        # Who mentioned it
    spec_a_date: str      # When
    spec_b_value: str     # Conflicting value
    spec_b_unit: str
    spec_b_by: str
    spec_b_date: str
    severity: str = "medium"  # "high", "medium", "low"


def _normalize_value(value: str) -> str:
    """Normalize a spec value for comparison."""
    try:
        return str(float(value.replace(",", "")))
    except (ValueError, TypeError):
        return value.strip().lower()


def detect_conflicts(specs: list) -> List[ConflictRecord]:
    """
    Detect conflicting specifications — same subject+category but different values.

    Args:
        specs: List of SpecRecord objects

    Returns:
        List of ConflictRecord objects
    """
    if not specs:
        return []

    # Group specs by (subject, category)
    groups: Dict[Tuple[str, str], list] = defaultdict(list)
    for spec in specs:
        subject = getattr(spec, "subject", "").strip().lower()
        if not subject:
            continue
        key = (subject, spec.category)
        groups[key].append(spec)

    conflicts = []
    seen_conflicts = set()

    for (subject, category), group_specs in groups.items():
        if len(group_specs) < 2:
            continue

        # Compare all pairs
        for i in range(len(group_specs)):
            for j in range(i + 1, len(group_specs)):
                spec_a = group_specs[i]
                spec_b = group_specs[j]

                val_a = _normalize_value(spec_a.value)
                val_b = _normalize_value(spec_b.value)

                # Skip if values are the same (not a conflict)
                if val_a == val_b:
                    continue

                # Skip if units don't match (different measurements entirely)
                unit_a = (spec_a.unit or "").strip().lower()
                unit_b = (spec_b.unit or "").strip().lower()
                if unit_a and unit_b and unit_a != unit_b:
                    continue  # Different units = different spec types

                # Dedup conflicts
                conflict_key = tuple(sorted([
                    f"{val_a}_{spec_a.mentioned_by}",
                    f"{val_b}_{spec_b.mentioned_by}"
                ]))
                if conflict_key in seen_conflicts:
                    continue
                seen_conflicts.add(conflict_key)

                # Determine severity
                severity = "medium"
                try:
                    num_a = float(val_a)
                    num_b = float(val_b)
                    pct_diff = abs(num_a - num_b) / max(abs(num_a), abs(num_b), 1) * 100
                    if pct_diff > 20:
                        severity = "high"
                    elif pct_diff < 5:
                        severity = "low"
                except (ValueError, TypeError):
                    severity = "medium"

                conflicts.append(ConflictRecord(
                    category=category,
                    subject=subject.capitalize(),
                    spec_a_value=spec_a.value,
                    spec_a_unit=spec_a.unit or "",
                    spec_a_by=spec_a.mentioned_by,
                    spec_a_date=spec_a.date_str,
                    spec_b_value=spec_b.value,
                    spec_b_unit=spec_b.unit or "",
                    spec_b_by=spec_b.mentioned_by,
                    spec_b_date=spec_b.date_str,
                    severity=severity,
                ))

    # Sort: high severity first
    severity_order = {"high": 0, "medium": 1, "low": 2}
    conflicts.sort(key=lambda c: severity_order.get(c.severity, 1))

    return conflicts


def format_conflicts_summary(conflicts: List[ConflictRecord]) -> str:
    """Format conflicts as a readable summary for reports."""
    if not conflicts:
        return "No specification conflicts detected."

    lines = [f"### ⚡ {len(conflicts)} Specification Conflict(s) Detected\n"]

    for i, c in enumerate(conflicts, 1):
        severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(c.severity, "⚪")
        lines.append(
            f"{i}. {severity_icon} **{c.subject}** ({c.category}): "
            f"**{c.spec_a_value} {c.spec_a_unit}** ({c.spec_a_by}) "
            f"vs **{c.spec_b_value} {c.spec_b_unit}** ({c.spec_b_by})"
        )

    return "\n".join(lines)
