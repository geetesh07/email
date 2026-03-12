"""
report_excel.py — Generate a multi-sheet Excel workbook with extracted data.
"""

import os
import pandas as pd
from typing import List, Dict


def generate_excel_report(
    output_path: str,
    people: List[Dict],
    specs: list,
    tagged_sentences: list,
    unresolved: list,
    timeline: list,
):
    """
    Generate an Excel workbook with separate sheets for each data category.
    
    Args:
        output_path: Path to save the .xlsx file
        people: List of dicts
        specs: List of SpecRecord objects
        tagged_sentences: List of TaggedSentence objects
        unresolved: List of TaggedSentence objects
        timeline: List of dicts
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:

        # ── Sheet 1: People ──
        if people:
            df_people = pd.DataFrame(people)
            # Reorder columns if they exist
            cols = ["name", "email", "company", "role"]
            cols = [c for c in cols if c in df_people.columns]
            df_people = df_people[cols] if cols else df_people
        else:
            df_people = pd.DataFrame(columns=["name", "email", "company", "role"])
        df_people.to_excel(writer, sheet_name="People", index=False)

        # ── Sheet 2: Specifications ──
        if specs:
            spec_rows = []
            for s in specs:
                spec_rows.append({
                    "Category": s.category,
                    "Raw Match": s.raw_match,
                    "Value": s.value,
                    "Unit": s.unit,
                    "Context": s.context,
                    "Mentioned By": s.mentioned_by,
                    "Date": s.date_str,
                    "Source": s.source_file,
                })
            df_specs = pd.DataFrame(spec_rows)
        else:
            df_specs = pd.DataFrame(columns=[
                "Category", "Raw Match", "Value", "Unit",
                "Context", "Mentioned By", "Date", "Source"
            ])
        df_specs.to_excel(writer, sheet_name="Specifications", index=False)

        # ── Sheet 3: Engineering Sentences ──
        if tagged_sentences:
            sent_rows = []
            for ts in tagged_sentences:
                sent_rows.append({
                    "Sentence": ts.sentence,
                    "Context": ts.context,
                    "Keywords": ", ".join(ts.trigger_keywords),
                    "Unresolved?": "Yes" if ts.is_unresolved else "",
                    "Mentioned By": ts.mentioned_by,
                    "Date": ts.date_str,
                })
            df_sents = pd.DataFrame(sent_rows)
        else:
            df_sents = pd.DataFrame(columns=[
                "Sentence", "Context", "Keywords",
                "Unresolved?", "Mentioned By", "Date"
            ])
        df_sents.to_excel(writer, sheet_name="Eng Sentences", index=False)

        # ── Sheet 4: Unresolved Items ──
        if unresolved:
            unres_rows = []
            for u in unresolved:
                unres_rows.append({
                    "Sentence": u.sentence,
                    "Context": u.context,
                    "Trigger": ", ".join(u.trigger_keywords),
                    "Mentioned By": u.mentioned_by,
                    "Date": u.date_str,
                })
            df_unres = pd.DataFrame(unres_rows)
        else:
            df_unres = pd.DataFrame(columns=[
                "Sentence", "Context", "Trigger", "Mentioned By", "Date"
            ])
        df_unres.to_excel(writer, sheet_name="Unresolved", index=False)

        # ── Sheet 5: Timeline ──
        if timeline:
            df_timeline = pd.DataFrame(timeline)
        else:
            df_timeline = pd.DataFrame(columns=["date", "sentence", "mentioned_by"])
        df_timeline.to_excel(writer, sheet_name="Timeline", index=False)

        # ── Auto-adjust column widths ──
        for sheet_name in writer.sheets:
            ws = writer.sheets[sheet_name]
            for col_cells in ws.columns:
                max_length = 0
                col_letter = col_cells[0].column_letter
                for cell in col_cells:
                    try:
                        if cell.value:
                            max_length = max(max_length, len(str(cell.value)))
                    except Exception:
                        pass
                adjusted_width = min(max_length + 2, 60)
                ws.column_dimensions[col_letter].width = adjusted_width

    print(f"  ✓ Excel report saved: {output_path}")
    return output_path
