"""
msg_parser.py — Parse .msg (Outlook) email files using extract-msg.
"""

import os
import glob
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

try:
    import extract_msg
except ImportError:
    extract_msg = None


@dataclass
class EmailRecord:
    """Unified email record used across all parsers."""
    sender_name: str = ""
    sender_email: str = ""
    recipients: List[str] = field(default_factory=list)
    cc: List[str] = field(default_factory=list)
    date: Optional[datetime] = None
    subject: str = ""
    body: str = ""
    source_file: str = ""
    message_id: str = ""
    attachments: List[str] = field(default_factory=list)

    @property
    def date_str(self) -> str:
        if self.date:
            return self.date.strftime("%b %d")
        return ""


def parse_msg_file(filepath: str) -> Optional[EmailRecord]:
    """Parse a single .msg file and return an EmailRecord."""
    if extract_msg is None:
        print("[WARN] extract-msg not installed. Skipping .msg files.")
        return None

    msg = None
    try:
        msg = extract_msg.Message(filepath)
        msg_sender = getattr(msg, 'sender', '') or ""
        msg_sender_email = getattr(msg, 'senderEmail', '') or getattr(msg, 'sender_email', '') or msg_sender

        # Parse sender name from "Name <email>" format
        sender_name = msg_sender
        if "<" in msg_sender:
            sender_name = msg_sender.split("<")[0].strip()

        msg_to = getattr(msg, 'to', '') or ""
        # Parse recipients
        recipients = []
        if msg_to:
            recipients = [r.strip() for r in msg_to.split(";") if r.strip()]

        # Parse CC
        msg_cc = getattr(msg, 'cc', '') or ""
        cc = []
        if msg_cc:
            cc = [c.strip() for c in msg_cc.split(";") if c.strip()]

        # Parse date
        email_date = None
        msg_date = getattr(msg, 'date', None)
        if msg_date:
            try:
                if isinstance(msg_date, datetime):
                    email_date = msg_date
                else:
                    # Try common date formats
                    for fmt in [
                        "%a, %d %b %Y %H:%M:%S %z",
                        "%d %b %Y %H:%M:%S %z",
                        "%Y-%m-%dT%H:%M:%S",
                        "%a, %d %b %Y %H:%M:%S",
                    ]:
                        try:
                            email_date = datetime.strptime(str(msg_date).strip(), fmt)
                            break
                        except ValueError:
                            continue
            except Exception:
                pass

        record = EmailRecord(
            sender_name=sender_name,
            sender_email=msg_sender_email,
            recipients=recipients,
            cc=cc,
            date=email_date,
            subject=getattr(msg, 'subject', '') or "",
            body=getattr(msg, 'body', '') or "",
            source_file=os.path.basename(filepath),
            message_id=str(hash(f"{msg_sender_email}_{getattr(msg, 'subject', '')}_{msg_date}"))
        )

        return record

    except Exception as e:
        print(f"[ERROR] Failed to parse {filepath}: {e}")
        raise
    finally:
        if msg is not None:
            try:
                msg.close()
            except Exception:
                pass


def parse_msg_folder(folder_path: str) -> List[EmailRecord]:
    """Parse all .msg files in a folder and return list of EmailRecords."""
    records = []
    msg_files = glob.glob(os.path.join(folder_path, "*.msg"))

    if not msg_files:
        print(f"[INFO] No .msg files found in {folder_path}")
        return records

    print(f"[INFO] Found {len(msg_files)} .msg file(s) in {folder_path}")
    for filepath in sorted(msg_files):
        record = parse_msg_file(filepath)
        if record:
            records.append(record)
            print(f"  ✓ Parsed: {os.path.basename(filepath)}")

    return records
