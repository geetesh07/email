import pytest
import os
from ingestion.msg_parser import EmailRecord
from processing.cleaner import clean_email_body
from processing.spec_extractor import extract_all_specs
from processing.sentence_tagger import tag_sentences, extract_unresolved
from processing.conflict_detector import detect_conflicts
from main import build_people_table

@pytest.fixture
def sample_emails():
    # Simulate parsed email records
    return [
        EmailRecord(
            message_id="msg001",
            subject="Motor Specs Update",
            sender_name="Alice Engineer",
            sender_email="alice@company.com",
            recipients=["bob@company.com"],
            cc=[],
            date=None,
            date_str="2023-10-24",
            body="Hey Bob,\nThe new prototype needs a 45.5mm shaft. Torque is 120Nm.\nCan we get this done by Friday?\nThanks,\nAlice",
            attachments=[],
            source_file="email1.eml"
        ),
        EmailRecord(
            message_id="msg002",
            subject="Re: Motor Specs Update",
            sender_name="Bob Manager",
            sender_email="bob@company.com",
            recipients=["alice@company.com"],
            cc=[],
            date=None,
            date_str="2023-10-25",
            body="Alice,\nActually, engineering just told me torque should be 150 Nm. \nLet's decide on the housing material too.\n-Bob",
            attachments=[],
            source_file="email2.eml"
        )
    ]

@pytest.fixture
def mock_config():
    return {
        "materials": ["Aluminum", "Steel", "Titanium"],
        "engineering_keywords": ["torque", "shaft", "material", "prototype"],
        "unresolved_markers": ["?", "decide", "TBD", "ACTION:"],
        "role_keywords": {
            "Manager": ["manager", "lead", "director"],
            "Engineer": ["engineer", "designer", "tech"]
        }
    }

def test_full_pipeline_processing(sample_emails, mock_config):
    all_specs = []
    specs_by_email = {}
    all_unresolved = []

    for record in sample_emails:
        cleaned_body = clean_email_body(record.body)
        
        # Specs
        specs = extract_all_specs(
            text=cleaned_body,
            material_keywords=mock_config["materials"],
            sender_name=record.sender_name,
            sender_email=record.sender_email,
            date_str=record.date_str,
            source_file=record.source_file,
        )
        all_specs.extend(specs)
        specs_by_email[record.message_id] = specs
        
        # Unresolved
        unresolved = extract_unresolved(
            text=cleaned_body,
            unresolved_markers=mock_config["unresolved_markers"],
            sender_name=record.sender_name,
            sender_email=record.sender_email,
            date_str=record.date_str,
            source_file=record.source_file,
            engineering_keywords=mock_config["engineering_keywords"],
        )
        all_unresolved.extend(unresolved)
        
    # 1. Verify Specs Extracted
    assert len(all_specs) >= 2
    cats = [s.category for s in all_specs]
    assert "📐 Dimensions" in cats
    assert "🔧 Torque" in cats
    
    # 2. Verify Conflicts Detected (120 vs 150 Nm)
    conflicts = detect_conflicts(all_specs)
    assert len(conflicts) == 1
    assert conflicts[0].category == "🔧 Torque"
    assert "120" in conflicts[0].spec_a_value or "150" in conflicts[0].spec_a_value
    
    # 3. Verify Unresolved Extracted
    assert len(all_unresolved) >= 2
    texts = [u.sentence for u in all_unresolved]
    assert any("Can we get this done by Friday?" in t for t in texts)
    assert any("Let's decide on the housing material too" in t for t in texts)
    
    # 4. Verify People logic doesn't crash
    people = build_people_table(sample_emails, specs_by_email, mock_config["role_keywords"])
    assert len(people) == 2
    
