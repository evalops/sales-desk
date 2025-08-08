# Sales Desk - AI-Powered Security Document Request Handler

An intelligent system that monitors Gmail for inbound security and due diligence document requests, automatically detects requested artifacts, applies organizational policies, and generates appropriate responses.

## Overview

Sales Desk is an AI assistant that:
- **Monitors** Gmail inbox for security documentation requests
- **Detects** specific artifacts being requested (SOC2, pentest reports, etc.)
- **Enforces** policies (NDA requirements, access controls)
- **Generates** professional responses with appropriate documents
- **Routes** complex requests to humans when needed

## Key Features

### 🎯 Intelligent Request Detection
- Automatically identifies security document requests in emails
- Recognizes 8+ types of common security artifacts
- Understands context and intent, not just keywords

### 🔐 Policy Enforcement
- Checks NDA status before sharing sensitive documents
- Applies document sensitivity levels
- Enforces sharing policies (watermarking, expiration, etc.)

### 📧 Automated Response Generation
- Creates professional, context-aware email responses
- Lists approved documents with delivery methods
- Explains requirements for restricted documents
- Provides clear next steps

### 🚨 Smart Escalation
- Identifies requests needing human review
- Routes legal/contract discussions appropriately
- Flags unclear or complex requests

## Installation

```bash
# Clone repository
git clone <repository-url>
cd sales_agent

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

### Environment Variables

Edit `.env` file:
```env
OPENAI_API_KEY=your_openai_api_key
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
```

### Gmail Authentication

On first run, the system will:
1. Open a browser for OAuth authentication
2. Request permissions to read and send emails
3. Save credentials locally for future use

## Usage

### Quick Start

```bash
# Test with sample requests
python main.py test

# Check system status
python main.py status

# Monitor inbox (single cycle)
python main.py monitor --test

# Start continuous monitoring
python main.py monitor --interval 60
```

### Commands

#### `test` - Run Test Cases
Tests the system with sample security document requests:
```bash
python main.py test
```

#### `monitor` - Monitor Gmail Inbox
Continuously monitors for new requests:
```bash
python main.py monitor               # Check every 60 seconds (default)
python main.py monitor --interval 30  # Check every 30 seconds
python main.py monitor --test         # Single cycle for testing
```

#### `process` - Process Specific Email
Process a single email by message ID:
```bash
python main.py process <message_id>
```

#### `status` - Show System Status
Display available artifacts and configuration:
```bash
python main.py status
```

## Supported Artifacts

The system recognizes and handles these document types:

| Artifact | Sensitivity | NDA Required | Description |
|----------|-------------|--------------|-------------|
| SOC 2 Type II | High | Yes | Annual audit report |
| ISO 27001 | Medium | No | Certification document |
| Security Whitepaper | Medium | No | Architecture overview |
| Penetration Test | High | Yes | Security test results |
| Vendor Questionnaire | Low | No | Security assessment form |
| Privacy Policy | Low | No | Data privacy documentation |
| DPA | Medium | No | Data processing agreement |
| Insurance Certificate | Medium | No | Cyber liability coverage |

## Response Flow

1. **Email Received** → System detects security document request
2. **Artifact Detection** → Identifies specific documents requested
3. **Policy Check** → Verifies NDA status and access permissions
4. **Response Generation** → Creates appropriate email response
5. **Action Decision** → Either sends response or routes to human

## JSON Output Schema

All responses follow this structure:
```json
{
  "detected_artifacts": ["soc2", "pentest"],
  "requires_nda": true,
  "nda_on_file": false,
  "approved_artifacts": [],
  "denied_artifacts": ["soc2", "pentest"],
  "share_method": "none",
  "link_expiration": null,
  "response_message": "Email response text...",
  "requires_human_review": false,
  "routing_reason": null
}
```

## Customization

### Adding New Artifacts

Edit `ARTIFACT_CATALOG` in `sales_desk.py`:
```python
"new_artifact": {
    "name": "Display Name",
    "sensitivity": "high|medium|low",
    "requires_nda": True|False,
    "description": "Description",
    "file_path": "/path/to/document"
}
```

### Modifying NDA Database

Update `_load_nda_database()` in `sales_desk.py`:
```python
return {
    "trusted@company.com": True,
    "*@partner.com": True,  # Domain-wide NDA
    "prospect@example.com": False
}
```

### Adjusting Detection Keywords

Edit `ARTIFACT_KEYWORDS` in `sales_desk.py`:
```python
"artifact_id": ["keyword1", "keyword2", "phrase to match"]
```

## Security Considerations

- Gmail credentials stored locally in `token.pickle`
- Never commits sensitive files (see `.gitignore`)
- All document sharing follows defined policies
- Human review for sensitive or unclear requests

## Troubleshooting

### Gmail Authentication Issues
- Delete `token.pickle` and re-authenticate
- Verify Google API credentials in `.env`
- Check OAuth consent screen settings

### No Emails Detected
- Verify search queries match your email patterns
- Check that emails contain recognized keywords
- Review `ARTIFACT_KEYWORDS` configuration

### API Rate Limits
- Adjust monitoring interval if hitting limits
- Implement exponential backoff if needed

## Architecture

```
main.py           # Entry point and CLI interface
├── sales_desk.py # Core logic for processing requests
├── gmail_tool.py # Gmail API integration
└── gmail_monitor.py # Inbox monitoring and orchestration
```

## Future Enhancements

- [ ] Webhook integration for real-time processing
- [ ] Database for tracking sent documents
- [ ] Analytics dashboard for request patterns
- [ ] Slack/Teams notifications for escalations
- [ ] Document watermarking integration
- [ ] Secure link generation with expiration