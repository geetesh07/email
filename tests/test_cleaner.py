import pytest
from processing.cleaner import clean_email_body

def test_clean_html_entities():
    dirty_text = "The length is 40&nbsp;mm and the width is 20&amp;mm."
    cleaned = clean_email_body(dirty_text)
    assert "40 mm" in cleaned
    assert "20&mm" in cleaned

def test_clean_urls():
    dirty_text = "Check the specs here: https://example.com/specs?id=123"
    cleaned = clean_email_body(dirty_text)
    assert "https://example.com" not in cleaned

def test_clean_phone_numbers():
    dirty_text = "Call me at +1 (555) 123-4567 or 555.987.6543 for details."
    cleaned = clean_email_body(dirty_text)
    assert "+1 (555)" not in cleaned
    assert "555.987" not in cleaned

def test_clean_disclaimers():
    dirty_text = "CONFIDENTIALITY NOTICE: This email and any attachments are confidential."
    cleaned = clean_email_body(dirty_text)
    assert "CONFIDENTIALITY NOTICE" not in cleaned

def test_clean_calendar_invites():
    dirty_text = "This is a test.\nWhen: Monday, October 24, 2023 10:00 AM\nWhere: WebEx\nOrganizer: John Doe\n"
    cleaned = clean_email_body(dirty_text)
    assert "This is a test." in cleaned
    assert "When: Monday" not in cleaned

def test_clean_outlook_separators():
    dirty_text = "Good job.\n________________________________\nFrom: Alice\nSent: Today\n"
    cleaned = clean_email_body(dirty_text)
    assert "Good job." in cleaned
    assert "________________________________" not in cleaned

def test_clean_salesforce_refs():
    dirty_text = "Please review. Ref: MSG-123456"
    cleaned = clean_email_body(dirty_text)
    assert "Please review." in cleaned
    assert "MSG-123456" not in cleaned
