# n8n & Salesforce Integration Guide

This guide explains how to connect your Salesforce instance to the built Email Intelligence Tool using **n8n**.

## 1. Start the API Server

Your Email Intelligence tool now has a REST API ready to receive data from n8n.

1. Open a terminal in the folder containing the `api.py` file (`C:\Users\Geeteshh\Downloads\email`).
2. Run the following command to start the server:
   ```bash
   uvicorn api:app --host 0.0.0.0 --port 8000
   ```
3. The server will start and be accessible at `http://localhost:8000` (or your public IP/domain if hosted).

## 2. Setting up n8n

In n8n, create a new workflow to listen for Salesforce events, process them through the API, and update Salesforce back.

### Step 1: Trigger Node
1. Search and add a **Salesforce trigger node**.
2. **Action**: Listen for when an `EmailMessage` record is **created**.
3. *Alternative*: If you don't use the native n8n Salesforce trigger, use a **Webhook** node and configure an Outbound Message / Apex trigger in Salesforce to hit the n8n webhook URL.

### Step 2: HTTP Request Node (To the Email API)
1. Add an **HTTP Request** node after the Trigger.
2. **Method**: `POST`
3. **URL**: `http://<your-server-ip>:8000/api/v1/analyze` (If running n8n on the same PC, use `http://host.docker.internal:8000/api/v1/analyze` or the local IP).
4. **Send Body**: Switch to `JSON` or Expression.
5. **Body format**:
```json
{
  "emails": [
    {
      "message_id": "{{ $json.Id }}",
      "subject": "{{ $json.Subject }}",
      "body": "{{ $json.TextBody }}",
      "sender_email": "{{ $json.FromAddress }}",
      "sender_name": "{{ $json.FromName }}",
      "recipients": ["{{ $json.ToAddress }}"],
      "date_str": "{{ $json.MessageDate }}"
    }
  ],
  "use_local_ai": true,
  "ai_model_name": "llama3:latest"
}
```
*(Adjust the variables according to your Salesforce trigger outputs)*.

### Step 3: Salesforce Update Node (Writing back)
1. Add a **Salesforce** node.
2. **Action**: `Update`
3. **Resource**: Example `Case` or `Opportunity`
4. **Record ID**: Map to the Parent ID of the EmailMessage (`{{ $('Salesforce Trigger').item.json.ParentId }}`).
5. **Fields to update**:
   - `Engineering_Summary__c` = `{{ $json.summary }}`
   - *Map any extracted specifications or unresolved items using n8n expressions as needed*.

### Notes
- Ensure your local Ollama is running if you set `"use_local_ai": true`.
- You can test the API by opening `http://<your-server-ip>:8000/docs` in your browser. This interactive interface allows you to send sample JSON payloads and view the formatted output.
