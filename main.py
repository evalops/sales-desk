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
from typing import Dict, Optional
from sales_desk import SalesDesk
from gmail_monitor import GmailMonitor
from dotenv import load_dotenv

load_dotenv()

def test_request_processing():
    """Test the Sales Desk with sample requests"""
    print("\n" + "="*60)
    print("TESTING SALES DESK REQUEST PROCESSING")
    print("="*60)
    
    test_cases = [
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
        print(f"\n📧 Test Case: {test_case['name']}")
        print("-" * 40)
        print(f"From: {test_case['email']['from']}")
        print(f"Subject: {test_case['email']['subject']}")
        print(f"Body: {test_case['email']['body'][:100]}...")
        
        response = sales_desk.process_request(test_case['email'])
        
        print("\n📊 Response JSON:")
        print(json.dumps(response, indent=2))
        
        print("\n✉️ Email Response:")
        print(response['response_message'])
        print("-" * 40)

def monitor_inbox(interval: int = 60, test_mode: bool = False):
    """Monitor Gmail inbox for security document requests"""
    print("\n" + "="*60)
    print("GMAIL MONITORING MODE")
    print("="*60)
    
    monitor = GmailMonitor()
    
    if test_mode:
        print("\n🔍 Running single monitoring cycle...")
        responses = monitor.run_monitoring_cycle()
        
        if responses:
            print("\n📊 Processing Summary:")
            for resp in responses:
                if "error" not in resp:
                    print(f"\n• Message ID: {resp.get('message_id')}")
                    print(f"  Detected: {resp.get('detected_artifacts')}")
                    print(f"  Approved: {resp.get('approved_artifacts')}")
                    print(f"  Needs Review: {resp.get('requires_human_review')}")
    else:
        print(f"\n🔄 Starting continuous monitoring (every {interval} seconds)")
        print("Press Ctrl+C to stop")
        monitor.start_continuous_monitoring(interval_seconds=interval)

def process_single_email(message_id: str):
    """Process a specific email by message ID"""
    print("\n" + "="*60)
    print(f"PROCESSING EMAIL: {message_id}")
    print("="*60)
    
    monitor = GmailMonitor()
    response = monitor.process_message(message_id)
    
    print("\n📊 Response:")
    print(json.dumps(response, indent=2))
    
    if response.get("response_message"):
        print("\n✉️ Generated Response:")
        print(response["response_message"])
    
    return response

def show_status():
    """Show system status and configuration"""
    print("\n" + "="*60)
    print("SALES DESK STATUS")
    print("="*60)
    
    sales_desk = SalesDesk()
    
    print("\n📚 Available Artifacts:")
    from sales_desk import ARTIFACT_CATALOG
    for artifact_id, details in ARTIFACT_CATALOG.items():
        nda_req = "🔒 NDA Required" if details["requires_nda"] else "✅ No NDA"
        print(f"  • {details['name']}: {nda_req}")
    
    print("\n🔐 NDA Database:")
    for email, has_nda in sales_desk.nda_database.items():
        status = "✅ On file" if has_nda else "❌ Not on file"
        print(f"  • {email}: {status}")
    
    print("\n⚙️ Configuration:")
    print(f"  • Gmail API: {'✅ Configured' if os.getenv('GOOGLE_CLIENT_ID') else '❌ Not configured'}")
    print(f"  • OpenAI API: {'✅ Configured' if os.getenv('OPENAI_API_KEY') else '❌ Not configured'}")

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
    
    print("\n🤖 Sales Desk - Inbound Document Request Handler")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
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
        print("\n\n👋 Sales Desk shutting down gracefully...")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()