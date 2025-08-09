#!/usr/bin/env python3
"""
Sales Desk - Inbound security and due diligence document request handler
"""

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from crewai import Agent, Task, Crew, Process
from gmail_tool import GmailTool
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from utils import load_config

load_dotenv()

# Load configuration and derive catalogs/keywords from config.yaml
_CONFIG = load_config()

def _catalog_from_config(cfg: dict) -> dict:
    artifacts = cfg.get("artifacts", {}) or {}
    catalog = {}
    for aid, a in artifacts.items():
        catalog[aid] = {
            "name": a.get("name", aid),
            "sensitivity": a.get("sensitivity", "low"),
            "requires_nda": bool(a.get("requires_nda", False)),
            "description": a.get("description", ""),
            "file_path": a.get("file_path", "")
        }
    return catalog

def _keywords_from_config(cfg: dict) -> dict:
    artifacts = cfg.get("artifacts", {}) or {}
    kmap = {}
    for aid, a in artifacts.items():
        kmap[aid] = [k.lower() for k in (a.get("keywords") or [])]
    return kmap

# Expose module-level constants for compatibility (e.g., main.status)
ARTIFACT_CATALOG = _catalog_from_config(_CONFIG) or {
    "soc2": {
        "name": "SOC 2 Type II Report",
        "sensitivity": "high",
        "requires_nda": True,
        "description": "Annual SOC 2 Type II audit report",
        "file_path": "/secure/documents/soc2_report_latest.pdf"
    },
    "iso27001": {
        "name": "ISO 27001 Certificate",
        "sensitivity": "medium",
        "requires_nda": False,
        "description": "ISO 27001 certification",
        "file_path": "/secure/documents/iso27001_cert.pdf"
    },
    "security_whitepaper": {
        "name": "Security Architecture Whitepaper",
        "sensitivity": "medium",
        "requires_nda": False,
        "description": "Technical security architecture overview",
        "file_path": "/secure/documents/security_whitepaper.pdf"
    },
    "pentest": {
        "name": "Penetration Test Report",
        "sensitivity": "high",
        "requires_nda": True,
        "description": "Latest penetration testing results",
        "file_path": "/secure/documents/pentest_report_latest.pdf"
    },
    "vendor_questionnaire": {
        "name": "Security Questionnaire Template",
        "sensitivity": "low",
        "requires_nda": False,
        "description": "Standard vendor security questionnaire",
        "file_path": "/secure/documents/vendor_questionnaire.xlsx"
    },
    "privacy_policy": {
        "name": "Privacy Policy",
        "sensitivity": "low",
        "requires_nda": False,
        "description": "Current privacy policy",
        "file_path": "/secure/documents/privacy_policy.pdf"
    },
    "dpa": {
        "name": "Data Processing Agreement",
        "sensitivity": "medium",
        "requires_nda": False,
        "description": "Standard DPA template",
        "file_path": "/secure/documents/dpa_template.pdf"
    },
    "insurance": {
        "name": "Insurance Certificate",
        "sensitivity": "medium",
        "requires_nda": False,
        "description": "Cyber liability insurance certificate",
        "file_path": "/secure/documents/insurance_cert.pdf"
    }
}

ARTIFACT_KEYWORDS = _keywords_from_config(_CONFIG) or {
    "soc2": ["soc 2", "soc2", "soc-2", "soc ii", "type 2", "type ii", "audit report"],
    "iso27001": ["iso 27001", "iso27001", "iso certification", "27001"],
    "security_whitepaper": ["security whitepaper", "security overview", "architecture document", "security architecture"],
    "pentest": ["penetration test", "pen test", "pentest", "vulnerability assessment", "security test"],
    "vendor_questionnaire": ["questionnaire", "security questionnaire", "vendor form", "security assessment"],
    "privacy_policy": ["privacy policy", "data privacy", "privacy notice"],
    "dpa": ["dpa", "data processing", "processing agreement", "gdpr agreement"],
    "insurance": ["insurance", "cyber insurance", "liability insurance", "insurance certificate"]
}

class SalesDeskResponse(BaseModel):
    """Schema for Sales Desk response"""
    detected_artifacts: List[str] = Field(description="List of artifact IDs detected in request")
    requires_nda: bool = Field(description="Whether any requested artifacts require NDA")
    nda_on_file: Optional[bool] = Field(description="Whether requester has NDA on file")
    approved_artifacts: List[str] = Field(description="Artifacts approved for sharing")
    denied_artifacts: List[str] = Field(description="Artifacts denied due to policy")
    share_method: str = Field(description="How artifacts will be shared (secure_link, email_attachment, etc)")
    link_expiration: Optional[str] = Field(description="When share links expire")
    response_message: str = Field(description="Email response to send")
    requires_human_review: bool = Field(description="Whether human review is needed")
    routing_reason: Optional[str] = Field(description="Why routing to human if applicable")

class SalesDesk:
    def __init__(self):
        # Lazy/no Gmail dependency: SalesDesk core does not require Gmail
        self.gmail_tool = None
        self.nda_database = self._load_nda_database()
        self.config = _CONFIG
        
    def _load_nda_database(self) -> Dict[str, bool]:
        """Load NDA database from config (emails or *@domain.com)."""
        entries = (_CONFIG.get("nda_database") or [])
        db: Dict[str, bool] = {}
        for e in entries:
            if isinstance(e, str) and e.strip():
                db[e.strip().lower()] = True
        # Backward-compatible defaults if config empty
        if not db:
            db = {
                "acme@example.com": True,
                "trusted@partner.com": True,
                "new@prospect.com": False,
            }
        return db
    
    def detect_artifacts(self, email_body: str) -> List[str]:
        """Detect which artifacts are being requested"""
        email_lower = email_body.lower()
        detected = []
        
        for artifact_id, keywords in ARTIFACT_KEYWORDS.items():
            if any(keyword in email_lower for keyword in keywords):
                detected.append(artifact_id)
        
        return detected
    
    def check_nda_status(self, sender_email: str) -> bool:
        """Check if sender has NDA on file (exact or wildcard domain)."""
        email = (sender_email or "").strip().lower()
        domain = email.split('@')[1] if '@' in email else email
        return bool(
            self.nda_database.get(email, False)
            or self.nda_database.get(f"*@{domain}", False)
        )
    
    def apply_policy(self, artifacts: List[str], has_nda: bool) -> tuple[List[str], List[str]]:
        """Apply org policy to determine approved/denied artifacts"""
        approved = []
        denied = []
        
        for artifact_id in artifacts:
            artifact = ARTIFACT_CATALOG.get(artifact_id)
            if artifact:
                if artifact["requires_nda"] and not has_nda:
                    denied.append(artifact_id)
                else:
                    approved.append(artifact_id)
        
        return approved, denied
    
    def generate_response(self, 
                         sender_name: str,
                         approved: List[str], 
                         denied: List[str],
                         has_nda: bool) -> str:
        """Generate email response using templates from config if available."""
        settings = (self.config.get("settings") or {})
        templates = (self.config.get("templates") or {})
        expiration_days = int((settings.get("link_expiration_days") or 7))
        signature = settings.get("email_signature", "Sales Desk Team")

        approved_list = "\n".join(
            [f"• {ARTIFACT_CATALOG[a]['name']}" for a in approved if a in ARTIFACT_CATALOG]
        ) or ""
        denied_list = "\n".join(
            [f"• {ARTIFACT_CATALOG[a]['name']}" for a in denied if a in ARTIFACT_CATALOG]
        ) or ""
        available_documents = "\n".join([f"- {d['name']}" for d in ARTIFACT_CATALOG.values()])

        # Unclear request template
        if not approved and not denied:
            tmpl = templates.get("unclear_request")
            if tmpl:
                return tmpl.format(
                    sender_name=sender_name,
                    available_documents=available_documents,
                    signature=signature,
                )
            # Fallback
            return (
                f"Hi {sender_name},\n\n"
                "Thank you for reaching out. I couldn't identify specific security documents in your request.\n\n"
                "Could you please clarify which of the following you need:\n"
                f"{available_documents}\n\n"
                f"Best regards,\n{signature}"
            )

        # Approved + possibly NDA required
        if denied:
            tmpl = templates.get("nda_required")
            approved_section = ""
            if approved:
                approved_section = (
                    "I'm preparing the following documents for you:\n" + approved_list + "\n\n"
                )
            if tmpl:
                return tmpl.format(
                    sender_name=sender_name,
                    approved_section=approved_section,
                    denied_list=denied_list,
                    expiration_days=expiration_days,
                    signature=signature,
                )

        # Approved only
        tmpl = templates.get("approved_response")
        if tmpl and approved:
            return tmpl.format(
                sender_name=sender_name,
                approved_list=approved_list,
                expiration_days=expiration_days,
                signature=signature,
            )

        # Fallback generic message
        response = f"Hi {sender_name},\n\nThank you for your security documentation request.\n\n"
        if approved:
            response += "I'm preparing the following documents for you:\n" + approved_list + "\n\n"
            response += f"You'll receive a secure link within the next few minutes that will be valid for {expiration_days} days.\n\n"
        if denied:
            response += "The following documents require an executed NDA before sharing:\n" + denied_list + "\n\n"
            response += "Please have your legal team complete our mutual NDA, and I'll send these immediately after execution.\n\n"
        response += f"Best regards,\n{signature}"
        return response
    
    def process_request(self, email_data: Dict[str, str]) -> Dict[str, Any]:
        """Main processing function"""
        sender_email = email_data.get("from", "")
        sender_name = sender_email.split("<")[0].strip() if "<" in sender_email else "there"
        subject = email_data.get("subject", "")
        body = email_data.get("body", "")
        
        # Detect requested artifacts
        detected = self.detect_artifacts(body)
        
        # Check NDA status
        has_nda = self.check_nda_status(sender_email)
        
        # Apply policy
        approved, denied = self.apply_policy(detected, has_nda)
        
        # Determine if NDA is required
        requires_nda = any(ARTIFACT_CATALOG.get(a, {}).get("requires_nda", False) for a in detected)
        
        # Generate response
        response_message = self.generate_response(sender_name, approved, denied, has_nda)
        
        # Determine if human review needed (configurable)
        escal_cfg = (self.config.get("settings", {}).get("escalation") or {})
        max_sensitive_without_nda = int(escal_cfg.get("max_sensitive_without_nda", 2))
        human_keywords = [k.lower() for k in (escal_cfg.get("human_review_keywords") or [])]

        body_lower = body.lower()
        keyword_hit = any(k in body_lower for k in human_keywords)
        requires_human = (
            len(detected) == 0 or
            len(denied) > max_sensitive_without_nda or
            keyword_hit
        )
        
        routing_reason = None
        if requires_human:
            if len(detected) == 0:
                routing_reason = "Unable to detect specific document request"
            elif len(denied) > max_sensitive_without_nda:
                routing_reason = "Multiple sensitive documents requested without NDA"
            elif keyword_hit:
                routing_reason = "Human review keyword detected"
        
        # Prepare response
        expiration_days = int((self.config.get("settings", {}).get("link_expiration_days") or 7))
        expiration = (datetime.now() + timedelta(days=expiration_days)).isoformat() if approved else None
        
        return {
            "detected_artifacts": detected,
            "requires_nda": requires_nda,
            "nda_on_file": has_nda,
            "approved_artifacts": approved,
            "denied_artifacts": denied,
            "share_method": "secure_link" if approved else "none",
            "link_expiration": expiration,
            "response_message": response_message,
            "requires_human_review": requires_human,
            "routing_reason": routing_reason
        }

# CrewAI Integration
def create_sales_desk_crew():
    """Create CrewAI crew for Sales Desk operations"""
    
    # Initialize Sales Desk
    sales_desk = SalesDesk()
    
    # Define agents
    email_analyzer = Agent(
        role='Email Analyzer',
        goal='Analyze inbound emails to detect security document requests',
        backstory="""You are an expert at understanding buyer requests for security 
        and compliance documentation. You can identify when someone is asking for 
        SOC2 reports, security questionnaires, or other due diligence artifacts.""",
        verbose=True
    )
    
    policy_enforcer = Agent(
        role='Policy Enforcer', 
        goal='Apply organizational policies to document sharing requests',
        backstory="""You ensure all document sharing follows company policy. You check 
        NDA requirements, validate access permissions, and enforce security controls 
        like watermarking and link expiration.""",
        verbose=True
    )
    
    response_writer = Agent(
        role='Response Writer',
        goal='Craft professional responses to document requests',
        backstory="""You write clear, helpful responses to buyers requesting security 
        documentation. You explain what can be shared, what requires additional steps, 
        and provide clear next steps.""",
        verbose=True
    )
    
    # Define tasks
    analyze_task = Task(
        description="""Analyze the inbound email to:
        1. Detect if it's asking for security/compliance documents
        2. Identify specific artifacts being requested
        3. Extract sender information
        4. Flag any special requirements or urgency
        
        Email to analyze: {email_content}""",
        expected_output="List of detected artifacts and sender details",
        agent=email_analyzer
    )
    
    policy_task = Task(
        description="""Apply organizational policy to the request:
        1. Check if sender has NDA on file
        2. Determine which documents can be shared
        3. Identify documents that require NDA
        4. Set appropriate sharing method and expiration
        5. Flag if human review is needed""",
        expected_output="Policy decision on what can be shared and how",
        agent=policy_enforcer
    )
    
    response_task = Task(
        description="""Generate the response:
        1. Create professional email response
        2. List approved documents with delivery method
        3. Explain any documents requiring NDA
        4. Provide clear next steps
        5. Output in required JSON schema""",
        expected_output="Complete JSON response following schema",
        agent=response_writer
    )
    
    # Create crew
    crew = Crew(
        agents=[email_analyzer, policy_enforcer, response_writer],
        tasks=[analyze_task, policy_task, response_task],
        process=Process.sequential,
        verbose=True
    )
    
    return crew, sales_desk

if __name__ == "__main__":
    # Test with sample request
    test_email = {
        "from": "buyer@example.com",
        "subject": "Security Documentation Request",
        "body": """Hi team,
        
        We're evaluating your solution and need to review your security posture.
        Could you please share your SOC 2 report and latest penetration test results?
        We'd also like to see your security architecture whitepaper if available.
        
        Thanks,
        John from Acme Corp"""
    }
    
    print("Sales Desk - Inbound Document Request Handler")
    print("=" * 60)
    
    sales_desk = SalesDesk()
    response = sales_desk.process_request(test_email)
    
    print("\nJSON Response:")
    print(json.dumps(response, indent=2))
    
    print("\n" + "=" * 60)
    print("Email Response Preview:")
    print(response["response_message"])
