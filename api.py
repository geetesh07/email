from fastapi import FastAPI, HTTPException, Request, Depends, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, root_validator
from typing import List, Optional, Dict
import datetime
import os
import sys
import re
import time
from collections import defaultdict

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
from processing.conflict_detector import detect_conflicts
try:
    from processing.ner_extractor import extract_all_specs_hybrid, SPACY_AVAILABLE
except ImportError:
    SPACY_AVAILABLE = False

app = FastAPI(
    title="Engineering Email Intelligence API",
    description="API for n8n/Salesforce integration to process engineering emails and extract specifications.",
    version="1.0"
)

# ── SECURITY HARdENING ──
config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
config = load_config(config_path)

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Simple in-memory rate limiting (100 req per minute per IP)
RATE_LIMIT = 100
RATE_LIMIT_WINDOWS = defaultdict(list)

def get_api_key(api_key: str = Security(api_key_header)):
    expected_api_key = config.get("api", {}).get("key") or os.getenv("EEI_API_KEY", "dev_secret_key")
    if api_key != expected_api_key:
        raise HTTPException(status_code=403, detail="Could not validate API key")
    return api_key

def check_rate_limit(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    
    # Clean old requests
    window_start = now - 60
    RATE_LIMIT_WINDOWS[client_ip] = [t for t in RATE_LIMIT_WINDOWS[client_ip] if t > window_start]
    
    if len(RATE_LIMIT_WINDOWS[client_ip]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too Many Requests")
    
    RATE_LIMIT_WINDOWS[client_ip].append(now)

def sanitize_input(text: str) -> str:
    if not text:
        return text
    # Remove null bytes and control chars (except newline/tab)
    return re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', text)

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

    def __init__(self, **data):
        # Sanitize body and subject on init
        super().__init__(**data)
        self.body = sanitize_input(self.body)
        self.subject = sanitize_input(self.subject)
        self.sender_name = sanitize_input(self.sender_name or "")
        
class AnalysisRequest(BaseModel):
    emails: List[EmailPayload]
    use_local_ai: Optional[bool] = False
    ai_model_name: Optional[str] = "llama3:latest"

@app.get("/health")
def health_check():
    return {"status": "ok", "ollama_reachable": check_ollama_status()}

@app.post("/analyze", dependencies=[Depends(get_api_key), Depends(check_rate_limit)])
def analyze_emails(payload: AnalysisRequest):
    """
    Main endpoint for pipeline processing.
    Expects a list of emails (subject, body, sender).
    Returns structured data: specs, people, open items, timeline, and summary.
    """
    if not payload.emails:
        raise HTTPException(status_code=400, detail="No emails provided in request payload")
        
    # Enforce payload size limit
    if len(payload.emails) > 500:
        raise HTTPException(status_code=413, detail="Payload too large (max 500 emails)")

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
    try:
        for record in emails_records:
            # Use hybrid extraction if available
            if SPACY_AVAILABLE:
                email_specs = extract_all_specs_hybrid(
                    text=record.body,
                    material_keywords=config.get("materials", []),
                    sender_name=record.sender_name,
                    sender_email=record.sender_email,
                    date_str=record.date_str,
                    source_file=record.source_file,
                )
            else:
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
                engineering_keywords=config.get("engineering_keywords", []),
            )
            all_unresolved.extend(unresolved)

        # 4. People & Timeline & Conflicts
        people = build_people_table(emails_records, specs_by_email, config.get("role_keywords", []))
        timeline = build_timeline(all_specs, all_tagged)
        conflicts = detect_conflicts(all_specs)

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
                "emails_processed": len(emails_records),
                "specs": [safe_dict(s) for s in all_specs],
                "people": people,
                "tagged_sentences": [safe_dict(t) for t in all_tagged],
                "unresolved_items": [safe_dict(u) for u in all_unresolved],
                "conflicts": [safe_dict(c) for c in conflicts],
                "timeline": timeline,
                "summary": summary
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline processing error: {str(e)}")

# Add env/dotenv logic to config
from dotenv import load_dotenv
load_dotenv()
