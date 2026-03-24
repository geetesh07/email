"""
eml_parser.py — Parse .eml email files using Python's built-in email module.
Includes HTML-to-text conversion, attachment metadata extraction,
and robust encoding handling.
"""

import os
import re
import glob
import email
import email.utils
from datetime import datetime
from typing import List, Optional

from ingestion.msg_parser import EmailRecord

# Try importing BeautifulSoup for HTML-to-text conversion
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


def _html_to_text(html_content: str) -> str:
    """
    Convert HTML email body to clean plain text.
    Uses BeautifulSoup if available, falls back to regex stripping.
    """
    if BS4_AVAILABLE:
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            # Remove script, style, and head tags entirely
            for tag in soup(["script", "style", "head", "meta", "link"]):
                tag.decompose()
            # Get text with line breaks preserved
            text = soup.get_text(separator="\n")
        except Exception:
            text = _regex_strip_html(html_content)
    else:
        text = _regex_strip_html(html_content)

    # Clean up the result
    text = _clean_html_artifacts(text)
    return text


def _regex_strip_html(html: str) -> str:
    """Fallback HTML stripping using regex (used when BS4 is not available)."""
    # Remove script and style blocks
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Convert <br>, <p>, <div> to newlines
    html = re.sub(r'<br\s*/?\s*>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</p>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</div>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</tr>', '\n', html, flags=re.IGNORECASE)
    # Remove all remaining tags
    html = re.sub(r'<[^>]+>', '', html)
    return html


def _clean_html_artifacts(text: str) -> str:
    """Clean up common HTML entities and artifacts."""
    # HTML entities
    entity_map = {
        "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&apos;": "'", "&#39;": "'", "&#8217;": "'",
        "&#8220;": '"', "&#8221;": '"', "&#8211;": "-", "&#8212;": "—",
        "&ldquo;": '"', "&rdquo;": '"', "&lsquo;": "'", "&rsquo;": "'",
        "&mdash;": "—", "&ndash;": "-", "&hellip;": "...",
        "&bull;": "•", "&middot;": "·",
    }
    for entity, char in entity_map.items():
        text = text.replace(entity, char)

    # Numeric HTML entities: &#123; or &#x1F;
    text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)
    text = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), text)

    # Collapse excessive whitespace
    text = re.sub(r'[ \t]{3,}', '  ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


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
    """
    Extract the body from an email message.
    Prefers plain text, falls back to HTML with tag stripping.
    """
    if msg.is_multipart():
        # First pass: look for plain text
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

        # Second pass: fall back to HTML with conversion
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disp = str(part.get("Content-Disposition", ""))
            if content_type == "text/html" and "attachment" not in content_disp:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        html = payload.decode(charset, errors="replace")
                    except (LookupError, UnicodeDecodeError):
                        html = payload.decode("utf-8", errors="replace")
                    return _html_to_text(html)

        return ""
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                text = payload.decode("utf-8", errors="replace")
            # If content-type is HTML, convert it
            if msg.get_content_type() == "text/html":
                return _html_to_text(text)
            return text
        return ""


def _extract_attachments(msg: email.message.Message) -> List[str]:
    """Extract attachment filenames from an email message."""
    attachments = []
    if not msg.is_multipart():
        return attachments

    for part in msg.walk():
        content_disp = str(part.get("Content-Disposition", ""))
        if "attachment" in content_disp:
            filename = part.get_filename()
            if filename:
                attachments.append(filename)
            else:
                content_type = part.get_content_type()
                if content_type not in ("text/plain", "text/html", "multipart/mixed",
                                         "multipart/alternative", "multipart/related"):
                    attachments.append(f"[unnamed {content_type}]")

    return attachments


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

        # Attachments
        attachments = _extract_attachments(msg)

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
            attachments=attachments,
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
