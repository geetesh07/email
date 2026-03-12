"""
local_ai.py - Connect to local Ollama instance for LLM operations.
"""
import requests
import json
from typing import List, Dict
import logging

OLLAMA_URL = "http://localhost:11434/api/generate"

def check_ollama_status() -> bool:
    """Check if Ollama is running locally."""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def generate_local_summary(emails: List[object], specs: List[object], people: List[Dict], unresolved: List[object]) -> str:
    """Generate an executive summary using a local Ollama model."""
    if not check_ollama_status():
        return "⚠️ Local AI (Ollama) is not accessible. Please ensure Ollama is running at `localhost:11434`."

    # Prepare abbreviated context to fit context windows reasonably well
    email_texts = "\n---\n".join([f"From: {e.sender_name}\nSubject: {e.subject}\nBody:\n{e.body[:1500]}..." for e in emails[:15]])
    
    prompt = f"""
You are an expert engineering assistant. Please summarize the following email thread discussing engineering specifications.

Email Thread:
{email_texts}

Key Participants:
{', '.join([p['name'] for p in people])}

Instructions:
1. Provide a concise executive summary describing the overall intent and context of the conversation.
2. Highlight the key engineering specifications (like dimensions, materials, torque, etc.) discussed.
3. List any open action items or pending decisions.

Write in a professional tone. Keep it under 3-4 paragraphs.
"""

    payload = {
        "model": "llama3",  # Assumes llama3 is installed; could also try mistral
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()
        return result.get("response", "Error: No response generated.")
    except requests.exceptions.ReadTimeout:
        return "⚠️ Local AI timeout. The model took too long to respond."
    except Exception as e:
        return f"⚠️ Error connecting to Local AI: {str(e)}\n\n(Ensure you have the `llama3` model installed in Ollama by running `ollama pull llama3`)."
