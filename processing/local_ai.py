"""
local_ai.py - Connect to local Ollama instance for LLM operations.
"""
import requests
import json
from typing import List, Dict, Any
import logging

def check_ollama_status(base_url: str = "http://localhost:11434") -> bool:
    """Check if Ollama is running locally."""
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=2)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def generate_local_summary(
    emails: List[Any], 
    specs: List[Any], 
    people: List[Dict], 
    unresolved: List[Any],
    base_url: str = "http://localhost:11434",
    model_name: str = "llama3"
) -> str:
    """Generate an executive summary using a local Ollama model."""
    if not check_ollama_status(base_url):
        return f"⚠️ Local AI (Ollama) is not accessible. Please ensure Ollama is running at `{base_url}`."

    # Prepare abbreviated context to fit context windows reasonably well
    email_texts = "\n---\n".join([f"From: {getattr(e, 'sender_name', 'Unknown')}\nSubject: {getattr(e, 'subject', 'Unknown')}\nBody:\n{(getattr(e, 'body', '') or '')[:1500]}..." for e in emails[:15]])
    
    prompt = f"""
You are an expert, meticulous mechanical engineering auditor. Your task is to analyze the following email thread and extract strictly factual engineering information. Do not provide a generic summary of the conversation.

Email Thread:
{email_texts}

Key Participants:
{', '.join([p.get('name', 'Unknown') for p in people])}

CRITICAL INSTRUCTIONS:
1. **Concrete Dimensions**: Extract exact values and map them to their specific subject (e.g., instead of "Discussed bore size", write "- **Hub Bore**: 20mm H7").
2. **Coupling Specifications**: Specifically look for coupling styles, models, interference fits, spacer lengths, ratings, and materials.
3. **No Fluff**: Do not write generic sentences like "The team discussed the coupling." Only output concrete specs and decisions.
4. **Resolved Decisions**: List final agreed-upon specs.
5. **DOUBTS / AMBIGUITIES**: You MUST create a section named "⚠️ AMBIGUITIES" if any spec is proposed but not confirmed, if two people disagree on a number, or if crucial dimensions (like torque or shaft size) are visibly missing from a request. Point exactly to where the confusion lies.
"""

    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(f"{base_url}/api/generate", json=payload, timeout=36000)
        response.raise_for_status()
        result = response.json()
        return result.get("response", "Error: No response generated.")
    except requests.exceptions.ReadTimeout:
        return "⚠️ Local AI timeout. The model took too long to respond."
    except Exception as e:
        return f"⚠️ Error connecting to Local AI: {str(e)}\n\n(Ensure you have the `{model_name}` model installed in Ollama by running `ollama pull {model_name}`)."

def generate_chat_response(
    messages: List[Dict[str, str]],
    emails: List[Any], 
    specs: List[Any], 
    people: List[Dict], 
    base_url: str = "http://localhost:11434",
    model_name: str = "llama3"
) -> str:
    """Generate a chat response keeping context of the email thread."""
    if not check_ollama_status(base_url):
        return f"⚠️ Local AI (Ollama) is not accessible. Please ensure Ollama is running at `{base_url}`."

    email_texts = "\n---\n".join([f"From: {getattr(e, 'sender_name', 'Unknown')}\nSubject: {getattr(e, 'subject', 'Unknown')}\nBody:\n{(getattr(e, 'body', '') or '')[:1500]}..." for e in emails[:15]])
    
    system_prompt = f"""
You are an expert mechanical engineering assistant. You are chatting with a user about the following email thread.
Answer their questions strictly based on the provided thread. Be precise, cite concrete dimensions and materials when asked, and if the data is missing from the thread, explicitly say so.

Email Thread:
{email_texts}

Key Participants:
{', '.join([p.get('name', 'Unknown') for p in people])}
"""

    chat_payload = [
        {"role": "system", "content": system_prompt}
    ]
    chat_payload.extend(messages)

    payload = {
        "model": model_name,
        "messages": chat_payload,
        "stream": False
    }

    try:
        response = requests.post(f"{base_url}/api/chat", json=payload, timeout=36000)
        response.raise_for_status()
        result = response.json()
        return result.get("message", {}).get("content", "Error: No response generated.")
    except requests.exceptions.ReadTimeout:
        return "⚠️ Local AI timeout. The model took too long to respond."
    except Exception as e:
        return f"⚠️ Error: {str(e)}"
