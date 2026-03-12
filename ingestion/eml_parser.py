"""
eml_parser.py — Parse .eml email files using Python's built-in email module.
"""

import os
import glob
import email
import email.utils
from datetime import datetime
from typing import List, Optional

from ingestion.msg_parser import EmailRecord


def _parse_address_list(header_value: str) -> List[str]:
    """Parse a comma-separated email header into a list of addresses."""
    if not header_value:
        return []
    addresses = []
    for name, addr in email.utils.getaddresses([header_value]):
        if addr:
            if name:
                addresses.append(f"{name} <{addr}>")
            else:
                addresses.append(addr)
    return addresses


def _extract_body(msg: email.message.Message) -> str:
    """Extract the plain-text body from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disp = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in content_disp:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        return payload.decode(charset, errors="replace")
                    except (LookupError, UnicodeDecodeError):
                        return payload.decode("utf-8", errors="replace")
        # Fallback: try HTML
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        return payload.decode(charset, errors="replace")
                    except (LookupError, UnicodeDecodeError):
                        return payload.decode("utf-8", errors="replace")
        return ""
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                return payload.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                return payload.decode("utf-8", errors="replace")
        return ""


def parse_eml_file(filepath: str) -> Optional[EmailRecord]:
    """Parse a single .eml file and return an EmailRecord."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            msg = email.message_from_file(f)

        # Sender
        sender_raw = msg.get("From", "")
        sender_name, sender_email_addr = email.utils.parseaddr(sender_raw)
        if not sender_name:
            sender_name = sender_email_addr.split("@")[0] if sender_email_addr else ""

        # Recipients and CC
        recipients = _parse_address_list(msg.get("To", ""))
        cc = _parse_address_list(msg.get("Cc", "") or msg.get("CC", ""))

        # Date
        email_date = None
        date_header = msg.get("Date", "")
        if date_header:
            try:
                parsed = email.utils.parsedate_to_datetime(date_header)
                email_date = parsed
            except Exception:
                for fmt in [
                    "%a, %d %b %Y %H:%M:%S %z",
                    "%d %b %Y %H:%M:%S %z",
                    "%Y-%m-%dT%H:%M:%S",
                ]:
                    try:
                        email_date = datetime.strptime(date_header.strip(), fmt)
                        break
                    except ValueError:
                        continue

        # Subject & Body
        subject = msg.get("Subject", "")
        body = _extract_body(msg)

        # Message-ID
        message_id = msg.get("Message-ID", "")
        if not message_id:
            message_id = str(hash(f"{sender_email_addr}_{subject}_{date_header}"))

        return EmailRecord(
            sender_name=sender_name,
            sender_email=sender_email_addr,
            recipients=recipients,
            cc=cc,
            date=email_date,
            subject=subject,
            body=body,
            source_file=os.path.basename(filepath),
            message_id=message_id,
        )

    except Exception as e:
        print(f"[ERROR] Failed to parse {filepath}: {e}")
        return None


def parse_eml_folder(folder_path: str) -> List[EmailRecord]:
    """Parse all .eml files in a folder and return list of EmailRecords."""
    records = []
    eml_files = glob.glob(os.path.join(folder_path, "*.eml"))

    if not eml_files:
        print(f"[INFO] No .eml files found in {folder_path}")
        return records

    print(f"[INFO] Found {len(eml_files)} .eml file(s) in {folder_path}")
    for filepath in sorted(eml_files):
        record = parse_eml_file(filepath)
        if record:
            records.append(record)
            print(f"  ✓ Parsed: {os.path.basename(filepath)}")

    return records
