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
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sales_desk import SalesDesk
from gmail_tool import GmailTool
from utils import setup_logging, AuditLogger, MetricsCollector, retry_with_backoff
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
gmail_tool = GmailTool()

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
    background_tasks: BackgroundTasks
):
    """
    Receive Gmail push notifications
    Requires setting up Gmail Push Notifications API
    """
    try:
        # Parse the notification
        body = await request.json()
        
        # Decode the message
        if 'message' in body and 'data' in body['message']:
            data = base64.b64decode(body['message']['data']).decode('utf-8')
            notification = json.loads(data)
            
            # Extract email ID
            email_id = notification.get('emailAddress')
            history_id = notification.get('historyId')
            
            logger.info(f"Received Gmail notification for {email_id}, history: {history_id}")
            
            # Process in background
            background_tasks.add_task(
                process_new_emails,
                email_id,
                history_id
            )
            
            return {"status": "accepted", "message": "Processing initiated"}
        
        return {"status": "ignored", "message": "No message data"}
        
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
        # Fetch new messages since history_id
        # This would use Gmail History API
        logger.info(f"Processing new emails for {email_address} since {history_id}")
        
        # For now, just search for recent unread
        results = gmail_tool.search_emails(
            query=f"is:unread to:{email_address}",
            max_results=5
        )
        
        # Process each message
        # ... processing logic ...
        
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
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Sales Desk Webhook Server starting...")
    # Initialize database connections, etc.

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