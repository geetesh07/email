from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
import datetime
import os
import sys

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import load_config, build_people_table, build_timeline
from ingestion.msg_parser import EmailRecord
from processing.cleaner import clean_email_body
from processing.deduplicator import deduplicate_body
from processing.spec_extractor import extract_all_specs
from processing.sentence_tagger import tag_sentences, extract_unresolved
from processing.summarizer import generate_summary
from processing.local_ai import generate_local_summary, check_ollama_status

app = FastAPI(
    title="Engineering Email Intelligence API",
    description="API for n8n/Salesforce integration to process engineering emails and extract specifications.",
    version="1.0"
)

config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
config = load_config(config_path)

class EmailPayload(BaseModel):
    message_id: str
    subject: str
    body: str
    sender_name: Optional[str] = ""
    sender_email: str
    recipients: Optional[List[str]] = []
    cc: Optional[List[str]] = []
    date_str: str

class AnalysisRequest(BaseModel):
    emails: List[EmailPayload]
    use_local_ai: Optional[bool] = False
    ai_model_name: Optional[str] = "llama3:latest"

@app.get("/health")
def health_check():
    return {"status": "ok", "ollama_reachable": check_ollama_status()}

@app.post("/api/v1/analyze")
def analyze_emails(payload: AnalysisRequest):
    if not payload.emails:
        raise HTTPException(status_code=400, detail="No emails provided in the request payload.")

    emails_records = []
    for p in payload.emails:
        # Try to parse the datetime
        try:
            # Handle ISO formats
            dt = datetime.datetime.fromisoformat(p.date_str.replace('Z', '+00:00'))
        except Exception:
            # Fallback
            dt = datetime.datetime.now()

        record = EmailRecord(
            subject=p.subject,
            sender_name=p.sender_name,
            sender_email=p.sender_email,
            date=dt,
            date_str=p.date_str,
            recipients=p.recipients or [],
            cc=p.cc or [],
            body=p.body,
            source_file="api_input",
            message_id=p.message_id
        )
        emails_records.append(record)

    # 1. Sort by date
    emails_records.sort(key=lambda e: e.date or datetime.datetime.min)

    # 2. Clean & Deduplicate
    seen_hashes = set()
    for record in emails_records:
        record.body = clean_email_body(
            record.body,
            config.get("signature_markers", []),
            config.get("disclaimer_phrases", []),
        )
        record.body = deduplicate_body(record.body, seen_hashes)

    # 3. Extract Specs & Sentences
    all_specs = []
    specs_by_email = {}
    all_tagged = []
    all_unresolved = []

    for record in emails_records:
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
        )
        all_unresolved.extend(unresolved)

    # 4. People & Timeline
    people = build_people_table(emails_records, specs_by_email, config.get("role_keywords", []))
    timeline = build_timeline(all_specs, all_tagged)

    # 5. Executive Summary
    if payload.use_local_ai:
        summary = generate_local_summary(
            emails_records, 
            all_specs, 
            people, 
            all_unresolved,
            model_name=payload.ai_model_name
        )
    else:
        summary = generate_summary(emails_records, all_specs, people, all_unresolved, timeline)

    # Helper function to convert custom objects to dicts
    def safe_dict(obj):
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return str(obj)

    return {
        "status": "success",
        "metrics": {
            "emails_analyzed": len(emails_records),
            "specs_extracted": len(all_specs),
            "unresolved_items": len(all_unresolved)
        },
        "summary": summary,
        "specs": [safe_dict(s) for s in all_specs],
        "unresolved": [safe_dict(u) for u in all_unresolved],
        "people": people,
        "timeline": timeline
    }
