"""
main.py — CLI entry point for the Engineering Email Intelligence Tool.

Usage:
    python main.py --input-dir ./tests/sample_emails --output-dir ./output --format all
    python main.py --input-dir ./emails --format docx
    python main.py --sf-case 00012345 --output-dir ./output --format xlsx
"""

import argparse
import os
import sys
import re
import yaml
from typing import List, Dict, Set

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ingestion.msg_parser import EmailRecord, parse_msg_folder
from ingestion.eml_parser import parse_eml_folder
from ingestion.salesforce import connect_salesforce, pull_emails_by_case, pull_emails_by_opportunity
from processing.cleaner import clean_email_body
from processing.deduplicator import deduplicate_body
from processing.spec_extractor import extract_all_specs, SpecRecord
from processing.sentence_tagger import tag_sentences, extract_unresolved, TaggedSentence
from output.report_docx import generate_docx_report
from output.report_excel import generate_excel_report
from output.report_html import generate_html_report


# ═══════════════════════════════════════════════════════════════
#  PEOPLE MAPPER (Module 4)
# ═══════════════════════════════════════════════════════════════

def _extract_email_address(addr_str: str) -> str:
    """Extract just the email address from 'Name <email>' format."""
    match = re.search(r"<([^>]+)>", addr_str)
    if match:
        return match.group(1).lower()
    if "@" in addr_str:
        return addr_str.strip().lower()
    return ""


def _extract_name_from_address(addr_str: str) -> str:
    """Extract name from 'Name <email>' format."""
    if "<" in addr_str:
        name = addr_str.split("<")[0].strip().strip('"').strip("'")
        if name:
            return name
    # Fallback: derive from email
    email_addr = _extract_email_address(addr_str)
    if email_addr:
        local = email_addr.split("@")[0]
        # Convert "first.last" or "first_last" to "First Last"
        return " ".join(part.capitalize() for part in re.split(r"[._]", local))
    return addr_str.strip()


def _extract_company(email_addr: str) -> str:
    """Extract company name from email domain."""
    if "@" not in email_addr:
        return ""
    domain = email_addr.split("@")[1].lower()
    # Remove common email providers
    common_providers = {
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
        "live.com", "aol.com", "icloud.com", "mail.com",
    }
    if domain in common_providers:
        return domain.split(".")[0].capitalize()
    # Use domain minus TLD
    parts = domain.split(".")
    if len(parts) >= 2:
        return parts[-2].capitalize()
    return domain.capitalize()


def _detect_role(signature_text: str, role_keywords: List[str]) -> str:
    """Try to detect role/title from a person's email content."""
    if not signature_text:
        return ""
    sig_lower = signature_text.lower()
    for kw in role_keywords:
        if kw.lower() in sig_lower:
            # Try to extract the full title line
            for line in signature_text.split("\n"):
                if kw.lower() in line.lower():
                    cleaned = line.strip().strip("-|:").strip()
                    if len(cleaned) < 80:
                        return cleaned
            return kw.capitalize()
    return ""


def build_people_table(
    emails: List[EmailRecord],
    specs_by_email: Dict[str, List[SpecRecord]],
    role_keywords: List[str],
) -> List[Dict]:
    """
    Build a people table from email records.
    Returns list of dicts: {name, email, company, role, emails_sent, specs_mentioned}
    """
    people_map: Dict[str, Dict] = {}  # keyed by email address

    for record in emails:
        # Process sender
        sender_addr = _extract_email_address(record.sender_email) or record.sender_email.lower()
        if sender_addr and sender_addr not in people_map:
            people_map[sender_addr] = {
                "name": record.sender_name or _extract_name_from_address(record.sender_email),
                "email": sender_addr,
                "company": _extract_company(sender_addr),
                "role": _detect_role(record.body, role_keywords),
                "emails_sent": 0,
                "specs_mentioned": [],
            }
        if sender_addr:
            people_map[sender_addr]["emails_sent"] = \
                people_map[sender_addr].get("emails_sent", 0) + 1

            # Add specs mentioned by this person
            person_specs = specs_by_email.get(record.message_id, [])
            for spec in person_specs:
                people_map[sender_addr]["specs_mentioned"].append(spec.raw_match)

        # Process recipients and CC (just add them as people, not senders)
        all_addrs = record.recipients + record.cc
        for addr in all_addrs:
            addr_email = _extract_email_address(addr) or addr.lower()
            if addr_email and addr_email not in people_map:
                people_map[addr_email] = {
                    "name": _extract_name_from_address(addr),
                    "email": addr_email,
                    "company": _extract_company(addr_email),
                    "role": "",
                    "emails_sent": 0,
                    "specs_mentioned": [],
                }

    return list(people_map.values())


# ═══════════════════════════════════════════════════════════════
#  TIMELINE BUILDER
# ═══════════════════════════════════════════════════════════════

def build_timeline(
    specs: List[SpecRecord],
    tagged: List[TaggedSentence],
) -> List[Dict]:
    """Build a timeline of engineering events sorted by date."""
    events = []

    for s in specs:
        if s.date_str:
            events.append({
                "date": s.date_str,
                "sentence": f"[{s.category}] {s.raw_match}",
                "mentioned_by": s.mentioned_by,
            })

    for t in tagged:
        if t.date_str and t.is_unresolved:
            events.append({
                "date": t.date_str,
                "sentence": t.sentence[:120],
                "mentioned_by": t.mentioned_by,
            })

    # Sort by date string (works for "Mon DD" format)
    events.sort(key=lambda x: x.get("date", ""))
    return events


# ═══════════════════════════════════════════════════════════════
#  MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    default_config = {
        "signature_markers": ["--", "Best regards", "Regards", "Sincerely"],
        "disclaimer_phrases": ["this email is confidential", "intended recipient"],
        "materials": ["SS316", "EN8", "mild steel", "aluminium 6061"],
        "engineering_keywords": ["torque", "RPM", "speed", "load", "pressure", "temperature"],
        "unresolved_markers": ["?", "confirm", "TBD", "pending", "to be decided"],
        "role_keywords": ["engineer", "manager", "sales", "director"],
        "salesforce": {},
    }

    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            try:
                loaded = yaml.safe_load(f) or {}
                default_config.update(loaded)
            except yaml.YAMLError as e:
                print(f"[WARN] Failed to parse config: {e}. Using defaults.")
    else:
        print(f"[INFO] Config file not found at {config_path}. Using defaults.")

    return default_config


def run_pipeline(args):
    """Main processing pipeline."""
    print("=" * 60)
    print("  Engineering Email Intelligence Tool")
    print("=" * 60)

    # Load config
    config_path = args.config or os.path.join(os.path.dirname(__file__), "config.yaml")
    config = load_config(config_path)

    # ── Step 1: Ingest emails ──
    print("\n▶ STEP 1: Ingesting emails...")
    all_emails: List[EmailRecord] = []

    if args.input_dir:
        input_dir = os.path.abspath(args.input_dir)
        if not os.path.isdir(input_dir):
            print(f"[ERROR] Input directory not found: {input_dir}")
            sys.exit(1)

        # Parse .msg files
        all_emails.extend(parse_msg_folder(input_dir))
        # Parse .eml files
        all_emails.extend(parse_eml_folder(input_dir))

    # Salesforce pull
    if args.sf_case or args.sf_opportunity:
        sf = connect_salesforce(config)
        if sf:
            if args.sf_case:
                all_emails.extend(pull_emails_by_case(sf, args.sf_case))
            if args.sf_opportunity:
                all_emails.extend(pull_emails_by_opportunity(sf, args.sf_opportunity))

    if not all_emails:
        print("[WARN] No emails found to process.")
        sys.exit(0)

    # Sort by date
    all_emails.sort(key=lambda e: e.date or __import__("datetime").datetime.min)
    print(f"  Total emails ingested: {len(all_emails)}")

    # ── Step 2: Clean emails ──
    print("\n▶ STEP 2: Cleaning email bodies...")
    for record in all_emails:
        record.body = clean_email_body(
            record.body,
            config.get("signature_markers", []),
            config.get("disclaimer_phrases", []),
        )
    print(f"  Cleaned {len(all_emails)} email(s).")

    # ── Step 3: Deduplicate ──
    print("\n▶ STEP 3: Deduplicating forwarded content...")
    seen_hashes: Set[str] = set()
    for record in all_emails:
        record.body = deduplicate_body(record.body, seen_hashes)
    print(f"  Unique paragraph hashes tracked: {len(seen_hashes)}")

    # ── Step 4: Extract Specs ──
    print("\n▶ STEP 4: Extracting engineering specifications...")
    all_specs: List[SpecRecord] = []
    specs_by_email: Dict[str, List[SpecRecord]] = {}

    for record in all_emails:
        email_specs = extract_all_specs(
            text=record.body,
            material_keywords=config.get("materials", []),
            sender_name=record.sender_name,
            sender_email=record.sender_email,
            date_str=record.date_str,
            source_file=record.source_file,
        )
        all_specs.extend(email_specs)
        specs_by_email[record.message_id] = email_specs

    print(f"  Extracted {len(all_specs)} specification(s).")

    # ── Step 5: Tag Sentences ──
    print("\n▶ STEP 5: Tagging engineering sentences...")
    all_tagged: List[TaggedSentence] = []
    all_unresolved: List[TaggedSentence] = []

    for record in all_emails:
        tagged = tag_sentences(
            text=record.body,
            engineering_keywords=config.get("engineering_keywords", []),
            unresolved_markers=config.get("unresolved_markers", []),
            sender_name=record.sender_name,
            sender_email=record.sender_email,
            date_str=record.date_str,
            source_file=record.source_file,
        )
        all_tagged.extend(tagged)

        unresolved = extract_unresolved(
            text=record.body,
            unresolved_markers=config.get("unresolved_markers", []),
            sender_name=record.sender_name,
            sender_email=record.sender_email,
            date_str=record.date_str,
            source_file=record.source_file,
            engineering_keywords=config.get("engineering_keywords", []),
        )
        all_unresolved.extend(unresolved)

    print(f"  Tagged {len(all_tagged)} engineering sentence(s).")
    print(f"  Found {len(all_unresolved)} unresolved item(s).")

    # ── Step 6: Build People Table ──
    print("\n▶ STEP 6: Building people table...")
    people = build_people_table(
        all_emails, specs_by_email, config.get("role_keywords", [])
    )
    print(f"  Identified {len(people)} person(s).")

    # ── Step 7: Build Timeline ──
    print("\n▶ STEP 7: Building timeline...")
    timeline = build_timeline(all_specs, all_tagged)
    print(f"  Timeline events: {len(timeline)}")

    # ── Step 8: Generate Reports ──
    print("\n▶ STEP 8: Generating reports...")
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    fmt = args.format.lower()
    generated = []

    if fmt in ("docx", "all"):
        path = os.path.join(output_dir, "report.docx")
        generate_docx_report(path, people, all_specs, all_tagged, all_unresolved, timeline)
        generated.append(path)

    if fmt in ("xlsx", "excel", "all"):
        path = os.path.join(output_dir, "report.xlsx")
        generate_excel_report(path, people, all_specs, all_tagged, all_unresolved, timeline)
        generated.append(path)

    if fmt in ("html", "all"):
        path = os.path.join(output_dir, "report.html")
        generate_html_report(path, people, all_specs, all_tagged, all_unresolved, timeline)
        generated.append(path)

    # ── Done ──
    print("\n" + "=" * 60)
    print("  ✅ DONE!")
    print(f"  Reports generated: {len(generated)}")
    for p in generated:
        print(f"    → {p}")
    print("=" * 60)

    return generated


def main():
    parser = argparse.ArgumentParser(
        description="Engineering Email Intelligence Tool — Extract specs from engineering emails.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --input-dir ./tests/sample_emails --output-dir ./output --format all
  python main.py --input-dir ./emails --format docx
  python main.py --sf-case 00012345 --output-dir ./output --format xlsx
        """,
    )

    parser.add_argument(
        "--input-dir", "-i",
        help="Directory containing .msg and/or .eml email files",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./output",
        help="Directory to save generated reports (default: ./output)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["docx", "xlsx", "excel", "html", "all"],
        default="all",
        help="Output format (default: all)",
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to config.yaml (default: ./config.yaml)",
    )
    parser.add_argument(
        "--sf-case",
        help="Salesforce Case number to pull emails from",
    )
    parser.add_argument(
        "--sf-opportunity",
        help="Salesforce Opportunity name to pull emails from",
    )

    args = parser.parse_args()

    if not args.input_dir and not args.sf_case and not args.sf_opportunity:
        parser.error("At least one of --input-dir, --sf-case, or --sf-opportunity is required.")

    run_pipeline(args)


if __name__ == "__main__":
    main()
