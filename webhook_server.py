#!/usr/bin/env python3
"""
Webhook server for real-time email processing
Integrates with Gmail Push Notifications API
"""

import os
import json
import base64
import asyncio
from typing import Dict, Optional
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sales_desk import SalesDesk
from gmail_tool import GmailTool
from utils import setup_logging, AuditLogger, MetricsCollector, retry_with_backoff, load_config, get_state_store, get_bool_setting
import logging

# Initialize FastAPI app
app = FastAPI(
    title="Sales Desk Webhook API",
    description="Real-time processing of security document requests",
    version="1.0.0"
)

# Initialize components
logger = setup_logging()
audit_logger = AuditLogger()
metrics = MetricsCollector()
sales_desk = SalesDesk()
try:
    gmail_tool = GmailTool()
except Exception as e:
    # Fallback dummy to avoid hard failures in environments without OAuth/network during import
    class _DummyGmail:
        def search_emails(self, *args, **kwargs):
            return "No messages found."
        def list_history_new_message_ids(self, *args, **kwargs):
            return []
        def read_email_details(self, message_id: str):
            return {"from": "", "subject": "", "body": "", "thread_id": None}
        def send_email(self, **kwargs):
            return "Dry run: not sending"
    gmail_tool = _DummyGmail()

# Persistence-backed idempotency + history tracking
CONFIG = load_config()
state_store = get_state_store(CONFIG)

# Request models
class GmailNotification(BaseModel):
    """Gmail push notification payload"""
    message: Dict
    subscription: str

class ManualRequest(BaseModel):
    """Manual document request submission"""
    from_email: str
    subject: str
    body: str
    priority: Optional[str] = "normal"

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

# Metrics endpoint
@app.get("/metrics")
async def get_metrics():
    """Get current metrics"""
    return metrics.get_summary()

# Gmail webhook endpoint
@app.post("/webhook/gmail")
async def gmail_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_secret: Optional[str] = Header(default=None, alias="x-webhook-secret"),
):
    """
    Receive Gmail push notifications
    Requires setting up Gmail Push Notifications API
    """
    try:
        # Validate shared secret if configured
        expected_secret = os.getenv("WEBHOOK_SHARED_SECRET")
        if expected_secret and x_webhook_secret != expected_secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

        # Parse the notification
        body = await request.json()
        
        # Decode the message
        if 'message' in body and 'data' in body['message']:
            try:
                data = base64.b64decode(body['message']['data']).decode('utf-8')
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid base64 data")
            notification = json.loads(data)
            
            # Extract email ID
            email_id = notification.get('emailAddress')
            history_id = notification.get('historyId')
            
            logger.info(f"Received Gmail notification for {email_id}, history: {history_id}")
            
            if not history_id:
                raise HTTPException(status_code=400, detail="Missing historyId")

            # Idempotency: ignore duplicate history IDs
            if state_store.is_processed_history(str(history_id)):
                return {"status": "ignored", "message": "Duplicate historyId"}
            state_store.mark_processed_history(str(history_id))
            
            # Process in background
            background_tasks.add_task(
                process_new_emails,
                email_id,
                history_id
            )
            
            return {"status": "accepted", "message": "Processing initiated"}
        
        return {"status": "ignored", "message": "No message data"}
        
    except HTTPException as he:
        # Propagate intended HTTP errors (auth/validation)
        logger.error(f"Webhook error: {he.detail}")
        raise
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Manual submission endpoint
@app.post("/api/process")
async def process_manual_request(
    request: ManualRequest,
    background_tasks: BackgroundTasks
):
    """Manually submit a document request for processing"""
    try:
        # Validate input
        if not request.from_email or not request.body:
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        # Process the request
        email_data = {
            "from": request.from_email,
            "subject": request.subject,
            "body": request.body
        }
        
        # Process through Sales Desk
        start_time = datetime.now()
        response = sales_desk.process_request(email_data)
        response_time = (datetime.now() - start_time).total_seconds()
        
        # Log audit trail
        audit_logger.log_request(
            request.from_email,
            response['detected_artifacts'],
            response['approved_artifacts'],
            response['denied_artifacts']
        )
        
        # Update metrics
        metrics.record_request(
            approved=len(response['approved_artifacts']) > 0,
            escalated=response['requires_human_review'],
            artifacts=response['approved_artifacts'],
            response_time=response_time
        )
        
        # Send response if not requiring human review
        if not response['requires_human_review'] and response['approved_artifacts']:
            background_tasks.add_task(
                send_document_response,
                request.from_email,
                response
            )
        
        return response
        
    except Exception as e:
        logger.error(f"Processing error: {e}")
        metrics.record_error()
        raise HTTPException(status_code=500, detail=str(e))

# Status endpoint
@app.get("/api/status/{request_id}")
async def get_request_status(request_id: str):
    """Get status of a document request"""
    # In production, this would query the database
    return {
        "request_id": request_id,
        "status": "processing",
        "message": "Feature coming soon"
    }

# Background tasks
async def process_new_emails(email_address: str, history_id: str):
    """Process new emails in background"""
    try:
        logger.info(f"Processing new emails for {email_address} since {history_id}")

        start_from = state_store.get_last_history_id() or history_id
        new_ids = gmail_tool.list_history_new_message_ids(str(start_from), max_pages=5)
        if not new_ids:
            logger.info("No new message IDs from history API; falling back to search")
            results = gmail_tool.search_emails(query="is:unread", max_results=5)
            lines = results.split("\n") if isinstance(results, str) else []
            new_ids = [ln.split('ID:')[-1].strip() for ln in lines if 'ID:' in ln]

        for mid in new_ids:
            if state_store.is_processed_message(mid):
                continue
            state_store.mark_processed_message(mid)
            try:
                details = gmail_tool.read_email_details(mid)
                if 'error' in details:
                    raise RuntimeError(details['error'])
                email_data = {
                    "from": details.get("from", ""),
                    "subject": details.get("subject", ""),
                    "body": details.get("body", ""),
                }
                start = datetime.now()
                resp = sales_desk.process_request(email_data)
                metrics.record_request(
                    approved=len(resp['approved_artifacts']) > 0,
                    escalated=resp['requires_human_review'],
                    artifacts=resp['approved_artifacts'],
                    response_time=(datetime.now() - start).total_seconds(),
                )
                audit_logger.log_request(
                    email_data.get('from',''),
                    resp['detected_artifacts'],
                    resp['approved_artifacts'],
                    resp['denied_artifacts'],
                )
                # Optionally auto-send could be gated by config; here we only log readiness
                if not resp['requires_human_review'] and resp['approved_artifacts']:
                    logger.info(f"Ready to send response for message {mid}")
                    auto_send = get_bool_setting(CONFIG, ["settings", "auto_send_when_approved"], "AUTO_SEND_WHEN_APPROVED", False)
                    dry_run = get_bool_setting(CONFIG, ["settings", "dry_run"], "DRY_RUN", False)
                    if auto_send and email_data.get('from'):
                        # Reply within thread if possible
                        if dry_run:
                            logger.info(f"[DRY-RUN] Would auto-send response to {email_data['from']}")
                        else:
                            thread_id = details.get('thread_id')
                            result = gmail_tool.send_email(
                                to=email_data['from'],
                                subject="Re: Security Documentation Request",
                                body=resp['response_message'],
                                thread_id=thread_id,
                            )
                            audit_logger.log_document_sent(
                                email_data['from'],
                                resp['approved_artifacts'],
                                'secure_link',
                                resp.get('link_expiration'),
                            )
                            logger.info(f"Auto-sent response to {email_data['from']}: {result}")
            except Exception as e:
                logger.error(f"Error processing message {mid}: {e}")
                metrics.record_error()

        state_store.set_last_history_id(str(history_id))
        
    except Exception as e:
        logger.error(f"Background processing error: {e}")
        metrics.record_error()

@retry_with_backoff(max_retries=3)
async def send_document_response(recipient: str, response: Dict):
    """Send document response with retry logic"""
    try:
        # Generate secure links for approved documents
        secure_links = {}
        for artifact in response['approved_artifacts']:
            # In production, this would generate actual secure links
            secure_links[artifact] = f"https://secure.docs.com/{artifact}"
        
        # Send email
        result = gmail_tool.send_email(
            to=recipient,
            subject="Re: Security Documentation Request",
            body=response['response_message']
        )
        
        # Log successful send
        audit_logger.log_document_sent(
            recipient,
            response['approved_artifacts'],
            'secure_link',
            response.get('link_expiration')
        )
        
        logger.info(f"Documents sent to {recipient}: {result}")
        
    except Exception as e:
        logger.error(f"Failed to send response: {e}")
        raise

# Error handlers
@app.exception_handler(404)
async def not_found(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Endpoint not found"}
    )

@app.exception_handler(500)
async def internal_error(request: Request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )

# Startup and shutdown events
# pyrefly: ignore  # deprecated
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Sales Desk Webhook Server starting...")
    # Initialize database connections, etc.

# pyrefly: ignore  # deprecated
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Sales Desk Webhook Server shutting down...")
    # Close database connections, save metrics, etc.

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )
