#!/usr/bin/env python3
"""
Gmail Monitor - Monitors inbox for inbound security document requests
"""

import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from gmail_tool import GmailTool
from sales_desk import SalesDesk
from crewai import Agent, Task, Crew, Process
from dotenv import load_dotenv
from utils import load_config
import logging

load_dotenv()

class GmailMonitor:
    def __init__(self):
        self.gmail = GmailTool()
        self.sales_desk = SalesDesk()
        self.processed_messages = set()
        self.config = load_config()
        self.logger = logging.getLogger('gmail_monitor')
        
    def fetch_unread_requests(self) -> List[Dict]:
        """Fetch unread emails that might be document requests"""
        # Search for unread emails using configured queries
        mon_cfg = (self.config.get("settings", {}).get("monitoring") or {})
        search_queries = mon_cfg.get("search_queries") or [
            "is:unread (soc2 OR soc 2 OR security OR compliance OR audit OR questionnaire OR pentest OR iso27001)",
            "is:unread subject:(security documentation OR due diligence OR vendor assessment)",
            "is:unread (DPA OR NDA OR insurance certificate)"
        ]
        max_per_cycle = int(mon_cfg.get("max_per_cycle", 10))
        
        messages = []
        for query in search_queries:
            try:
                results = self.gmail.search_emails(query=query, max_results=10)
                if results and results != "No messages found.":
                    # Parse the results to get message IDs
                    for line in results.split('\n'):
                        if 'ID:' in line:
                            msg_id = line.split('ID:')[1].strip()
                            if msg_id not in self.processed_messages:
                                messages.append(msg_id)
                                if len(messages) >= max_per_cycle:
                                    break
                if len(messages) >= max_per_cycle:
                    break
            except Exception as e:
                self.logger.error(f"Error searching emails: {e}")
        
        return messages
    
    def process_message(self, message_id: str) -> Dict:
        """Process a single message through Sales Desk"""
        try:
            details = self.gmail.read_email_details(message_id)
            if 'error' in details:
                raise RuntimeError(details['error'])
            email_data = {
                "from": details.get("from", ""),
                "subject": details.get("subject", ""),
                "body": details.get("body", ""),
                "message_id": message_id,
                "thread_id": details.get("thread_id"),
            }
            
            # Process through Sales Desk
            response = self.sales_desk.process_request(email_data)
            response["message_id"] = message_id
            if email_data.get('thread_id'):
                response['thread_id'] = email_data['thread_id']
            
            # Mark as processed
            self.processed_messages.add(message_id)
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error processing message {message_id}: {e}")
            return {
                "error": str(e),
                "message_id": message_id,
                "requires_human_review": True,
                "routing_reason": "Error processing message"
            }
    
    def send_response(self, response: Dict, recipient_email: str) -> bool:
        """Send the response email"""
        try:
            if response.get("response_message"):
                result = self.gmail.send_email(
                    to=recipient_email,
                    subject=f"Re: Security Documentation Request",
                    body=response["response_message"],
                    in_reply_to=response.get("message_id"),
                    thread_id=response.get("thread_id"),
                )
                return "successfully" in result.lower()
            return False
        except Exception as e:
            self.logger.error(f"Error sending response: {e}")
            return False
    
    def create_monitoring_crew(self):
        """Create CrewAI crew for continuous monitoring"""
        
        monitor_agent = Agent(
            role='Inbox Monitor',
            goal='Monitor Gmail inbox for security document requests',
            backstory="""You continuously monitor the inbox for emails requesting 
            security documentation, compliance artifacts, or due diligence materials. 
            You identify and prioritize these requests for processing.""",
            tools=[self.gmail],
            verbose=True
        )
        
        processor_agent = Agent(
            role='Request Processor',
            goal='Process document requests through Sales Desk workflow',
            backstory="""You take identified requests and process them through the 
            Sales Desk system, applying policies and generating appropriate responses.""",
            verbose=True
        )
        
        responder_agent = Agent(
            role='Response Manager',
            goal='Send appropriate responses and track interactions',
            backstory="""You manage sending responses, tracking what was shared, 
            and ensuring follow-up when needed. You also escalate to humans when required.""",
            tools=[self.gmail],
            verbose=True
        )
        
        monitor_task = Task(
            description="""Monitor the Gmail inbox for new security document requests.
            Check for unread emails containing keywords like:
            - SOC2, security audit, compliance report
            - Penetration test, security assessment
            - Questionnaire, vendor assessment
            - DPA, NDA, insurance
            
            Return list of message IDs that need processing.""",
            expected_output="List of message IDs for security document requests",
            agent=monitor_agent
        )
        
        process_task = Task(
            description="""Process each identified request:
            1. Read full email content
            2. Detect requested artifacts
            3. Check NDA status
            4. Apply organizational policies
            5. Generate appropriate response
            6. Output JSON response per schema""",
            expected_output="JSON responses for each request",
            agent=processor_agent
        )
        
        respond_task = Task(
            description="""Handle responses:
            1. Send approved responses via email
            2. Flag items needing human review
            3. Track what was sent and when
            4. Schedule follow-ups if needed""",
            expected_output="Summary of actions taken",
            agent=responder_agent
        )
        
        crew = Crew(
            agents=[monitor_agent, processor_agent, responder_agent],
            tasks=[monitor_task, process_task, respond_task],
            process=Process.sequential,
            verbose=True
        )
        
        return crew
    
    def run_monitoring_cycle(self):
        """Run a single monitoring cycle"""
        self.logger.info(f"Checking for new requests...")
        
        # Fetch unread requests
        message_ids = self.fetch_unread_requests()
        
        if not message_ids:
            self.logger.info("No new security document requests found.")
            return
        
        self.logger.info(f"Found {len(message_ids)} potential requests to process")
        
        # Process each message
        responses = []
        for msg_id in message_ids:
            self.logger.info(f"Processing message: {msg_id}")
            response = self.process_message(msg_id)
            responses.append(response)
            
            # Output the response
            self.logger.info("Generated Response:\n" + json.dumps(response, indent=2))
            
            # If not requiring human review and has approved artifacts, could auto-send
            if not response.get("requires_human_review") and response.get("approved_artifacts"):
                self.logger.info("✅ Ready for automated response")
            elif response.get("requires_human_review"):
                self.logger.warning(f"⚠️ Requires human review: {response.get('routing_reason')}")
        
        return responses
    
    def start_continuous_monitoring(self, interval_seconds: int = 60):
        """Start continuous monitoring loop"""
        self.logger.info(f"Starting Gmail monitoring (checking every {interval_seconds} seconds)")
        self.logger.info("Press Ctrl+C to stop")
        
        try:
            while True:
                self.run_monitoring_cycle()
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            self.logger.info("Monitoring stopped")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('gmail_monitor')
    logger.info("Gmail Monitor for Sales Desk")
    
    monitor = GmailMonitor()
    
    # Run a single cycle for testing
    logger.info("Running single monitoring cycle...")
    responses = monitor.run_monitoring_cycle()
    
    if responses:
        logger.info("PROCESSING SUMMARY")
        for resp in responses:
            if "error" not in resp:
                logger.info(f"Message ID: {resp.get('message_id')}")
                logger.info(f"Detected Artifacts: {resp.get('detected_artifacts')}")
                logger.info(f"Approved: {resp.get('approved_artifacts')}")
                logger.info(f"Denied: {resp.get('denied_artifacts')}")
                logger.info(f"Human Review: {resp.get('requires_human_review')}")
    
    logger.info("To start continuous monitoring, run monitor.start_continuous_monitoring(interval_seconds=60)")
