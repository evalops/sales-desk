#!/usr/bin/env python3
"""
Sales Desk - AI-powered inbound security document request handler
Main entry point for the application
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Any, Dict, List
import logging
from typing import Dict, Optional
from sales_desk import SalesDesk
from gmail_monitor import GmailMonitor
from dotenv import load_dotenv
from utils import setup_logging

load_dotenv()
logger = setup_logging()

def test_request_processing():
    """Test the Sales Desk with sample requests"""
    logger.info("TESTING SALES DESK REQUEST PROCESSING")
    
    test_cases: List[Dict[str, Any]] = [
        {
            "name": "SOC2 Request (No NDA)",
            "email": {
                "from": "buyer@newcompany.com",
                "subject": "Security Documentation Request",
                "body": "Hi, we need your SOC 2 report and security whitepaper for our vendor assessment."
            }
        },
        {
            "name": "Multiple Sensitive Docs (With NDA)",
            "email": {
                "from": "acme@example.com",  # Has NDA in mock database
                "subject": "Due Diligence Request",
                "body": "Please send your latest SOC2 report, penetration test results, and ISO 27001 certificate."
            }
        },
        {
            "name": "Unclear Request",
            "email": {
                "from": "vague@company.com",
                "subject": "Security Info",
                "body": "Can you send me information about your security?"
            }
        }
    ]
    
    sales_desk = SalesDesk()
    
    for test_case in test_cases:
        logger.info(f"Test Case: {test_case['name']}")
        logger.info(f"From: {test_case['email']['from']}")
        logger.info(f"Subject: {test_case['email']['subject']}")
        logger.info(f"Body: {test_case['email']['body'][:100]}...")
        
        response = sales_desk.process_request(test_case['email'])
        
        logger.info("Response JSON:\n" + json.dumps(response, indent=2))
        logger.info("Email Response:\n" + response['response_message'])

def monitor_inbox(interval: int = 60, test_mode: bool = False):
    """Monitor Gmail inbox for security document requests"""
    logger.info("GMAIL MONITORING MODE")
    
    monitor = GmailMonitor()
    
    if test_mode:
        logger.info("Running single monitoring cycle...")
        responses = monitor.run_monitoring_cycle()
        
        if responses:
            logger.info("Processing Summary:")
            for resp in responses:
                if "error" not in resp:
                    logger.info(f"• Message ID: {resp.get('message_id')}")
                    logger.info(f"  Detected: {resp.get('detected_artifacts')}")
                    logger.info(f"  Approved: {resp.get('approved_artifacts')}")
                    logger.info(f"  Needs Review: {resp.get('requires_human_review')}")
    else:
        logger.info(f"Starting continuous monitoring (every {interval} seconds)")
        logger.info("Press Ctrl+C to stop")
        monitor.start_continuous_monitoring(interval_seconds=interval)

def process_single_email(message_id: str):
    """Process a specific email by message ID"""
    logger.info(f"PROCESSING EMAIL: {message_id}")
    
    monitor = GmailMonitor()
    response = monitor.process_message(message_id)
    
    logger.info("Response:\n" + json.dumps(response, indent=2))
    
    if response.get("response_message"):
        logger.info("Generated Response:\n" + response["response_message"])
    
    return response

def show_status():
    """Show system status and configuration"""
    logger.info("SALES DESK STATUS")
    
    sales_desk = SalesDesk()
    
    logger.info("Available Artifacts:")
    from sales_desk import ARTIFACT_CATALOG
    for artifact_id, details in ARTIFACT_CATALOG.items():
        nda_req = "🔒 NDA Required" if details["requires_nda"] else "✅ No NDA"
        logger.info(f"  • {details['name']}: {nda_req}")
    
    logger.info("NDA Database:")
    for email, has_nda in sales_desk.nda_database.items():
        status = "✅ On file" if has_nda else "❌ Not on file"
        logger.info(f"  • {email}: {status}")
    
    logger.info("Configuration:")
    logger.info(f"  • Gmail API: {'✅ Configured' if os.getenv('GOOGLE_CLIENT_ID') else '❌ Not configured'}")
    logger.info(f"  • OpenAI API: {'✅ Configured' if os.getenv('OPENAI_API_KEY') else '❌ Not configured'}")

def main():
    parser = argparse.ArgumentParser(
        description='Sales Desk - AI-powered security document request handler',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s test                    # Run test cases
  %(prog)s monitor                 # Start monitoring Gmail inbox
  %(prog)s monitor --interval 30   # Check every 30 seconds
  %(prog)s process MSG_ID          # Process specific email
  %(prog)s status                  # Show system status
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Test command
    test_parser = subparsers.add_parser('test', help='Run test cases')
    
    # Monitor command
    monitor_parser = subparsers.add_parser('monitor', help='Monitor Gmail inbox')
    monitor_parser.add_argument('--interval', type=int, default=60, 
                                help='Check interval in seconds (default: 60)')
    monitor_parser.add_argument('--test', action='store_true',
                                help='Run single cycle for testing')
    
    # Process command
    process_parser = subparsers.add_parser('process', help='Process specific email')
    process_parser.add_argument('message_id', help='Gmail message ID to process')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show system status')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    logger.info("🤖 Sales Desk - Inbound Document Request Handler")
    logger.info(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        if args.command == 'test':
            test_request_processing()
        elif args.command == 'monitor':
            monitor_inbox(interval=args.interval, test_mode=args.test)
        elif args.command == 'process':
            process_single_email(args.message_id)
        elif args.command == 'status':
            show_status()
    except KeyboardInterrupt:
        logger.info("👋 Sales Desk shutting down gracefully...")
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
