#!/usr/bin/env python3
"""
Huly Webhook Receiver for Graphiti
Receives webhook events from Huly and ingests them into Graphiti knowledge graph
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
import uvicorn
import httpx
import os

# Configuration
GRAPHITI_API_URL = os.getenv("GRAPHITI_API_URL", "http://localhost:8003")
GROUP_ID = os.getenv("GRAPHITI_GROUP_ID", "huly_project_management")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Logging setup
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Huly Webhook Receiver for Graphiti",
    description="Receives webhook events from Huly and ingests them into Graphiti.",
    version="0.1.0",
)

class HulyWebhookPayload(BaseModel):
    """Huly webhook event payload"""
    id: str
    type: str
    timestamp: str
    workspace: Optional[str] = None
    data: Dict[str, Any]
    changes: Optional[Dict[str, Any]] = None

async def send_to_graphiti(event_data: dict):
    """Send event data to Graphiti for ingestion"""
    try:
        # Format as messages for Graphiti
        event_type = event_data.get('type', 'unknown')
        timestamp = event_data.get('timestamp', datetime.now().isoformat())
        
        # Create a readable content summary
        content_parts = [f"Huly {event_type} Event"]
        
        data = event_data.get('data', {})
        if 'issue' in data:
            issue = data['issue']
            content_parts.append(f"Issue: {issue.get('identifier', 'Unknown')} - {issue.get('title', 'No title')}")
            if issue.get('description'):
                content_parts.append(f"Description: {issue['description'][:200]}...")
            content_parts.append(f"Status: {issue.get('status', 'Unknown')}")
            content_parts.append(f"Priority: {issue.get('priority', 'Unknown')}")
            if issue.get('assignee'):
                content_parts.append(f"Assignee: {issue['assignee']}")
                
        elif 'project' in data:
            project = data['project']
            content_parts.append(f"Project: {project.get('identifier', 'Unknown')} - {project.get('name', 'No name')}")
            if project.get('description'):
                content_parts.append(f"Description: {project['description'][:200]}...")
                
        elif 'comment' in data:
            comment = data['comment']
            content_parts.append(f"Comment on {comment.get('issue_id', 'Unknown')}")
            if comment.get('text'):
                content_parts.append(f"Text: {comment['text'][:200]}...")
        
        # Add changes if present
        changes = event_data.get('changes', {})
        if changes:
            content_parts.append("Changes:")
            for field, change in changes.items():
                content_parts.append(f"  - {field}: {change.get('from', 'N/A')} → {change.get('to', 'N/A')}")
        
        content = "\n".join(content_parts)
        
        # Create message for Graphiti
        messages = [{
            "content": content,
            "name": f"huly_{event_type}_{timestamp}",
            "role_type": "system",
            "role": "huly_webhook",
            "timestamp": timestamp,
            "metadata": {
                "source": "huly",
                "event_type": event_type,
                "event_id": event_data.get('id', 'unknown'),
                "workspace": event_data.get('workspace', 'unknown')
            }
        }]
        
        # Send to Graphiti
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{GRAPHITI_API_URL}/messages",
                json={
                    "group_id": GROUP_ID,
                    "messages": messages
                }
            )
            
            if response.status_code == 202:
                logger.info(f"Successfully sent Huly event {event_type} to Graphiti")
                return True
            else:
                logger.error(f"Failed to send to Graphiti: {response.status_code} - {response.text}")
                return False
                
    except Exception as e:
        logger.exception(f"Error sending to Graphiti: {e}")
        return False

@app.post("/webhook")
async def receive_huly_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives webhook events from Huly.
    Queues the event for processing in the background.
    """
    logger.info("-" * 30)
    logger.info(f"Received Huly webhook event. Headers: {dict(request.headers)}")
    
    try:
        payload_data = await request.json()
        logger.info(f"Raw webhook payload: {payload_data}")
        
        # Validate payload
        validated_payload = HulyWebhookPayload(**payload_data)
        logger.info(f"Validated Huly event type: {validated_payload.type}")
        
        # Queue the event processing in the background
        background_tasks.add_task(send_to_graphiti, payload_data)
        
        # Return immediately with success response
        return {"status": "success", "message": "Webhook received and queued for processing"}
        
    except Exception as e:
        logger.exception("Error processing webhook request")
        raise HTTPException(status_code=400, detail=f"Invalid request or payload: {e}")

@app.get("/")
async def root():
    """Root endpoint for health check."""
    return {"message": "Huly Webhook Receiver for Graphiti is running."}

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "huly-webhook-receiver"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8006))
    logger.info(f"Starting Huly Webhook Receiver on port {port}")
    logger.info(f"Graphiti API URL: {GRAPHITI_API_URL}")
    logger.info(f"Group ID: {GROUP_ID}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level=LOG_LEVEL.lower())