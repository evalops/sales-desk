import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sales_desk import SalesDesk, ARTIFACT_CATALOG


def make_email(sender: str, subject: str, body: str):
    return {"from": sender, "subject": subject, "body": body}


@pytest.fixture()
def sd():
    return SalesDesk()


def test_sender_name_parsing(sd: SalesDesk):
    email = make_email(
        "John Doe <john@example.com>",
        "Request",
        "Please send your privacy policy."
    )
    resp = sd.process_request(email)
    # Should greet John Doe, not 'there'
    assert resp["response_message"].startswith("Hi John Doe")


def test_requires_nda_flag_when_any_sensitive(sd: SalesDesk):
    email = make_email(
        "user@test.com",
        "Docs",
        "SOC 2 and privacy policy please."
    )
    resp = sd.process_request(email)
    assert resp["requires_nda"] is True


def test_escalation_threshold_is_configurable(sd: SalesDesk):
    # Lower threshold to 1 so two denied sensitive docs trigger escalation
    sd.config.setdefault("settings", {}).setdefault("escalation", {})["max_sensitive_without_nda"] = 1
    email = make_email(
        "user@no-nda.com",
        "Need sensitive docs",
        "Please share SOC2 and penetration test."
    )
    resp = sd.process_request(email)
    assert resp["requires_human_review"] is True
    assert resp["routing_reason"] == "Multiple sensitive documents requested without NDA"


def test_unclear_response_lists_available_documents(sd: SalesDesk):
    email = make_email(
        "user@test.com",
        "Hello",
        "Can you help?"
    )
    resp = sd.process_request(email)
    msg = resp["response_message"]
    # Ensure at least one known document name appears
    any_name_included = any(d["name"] in msg for d in ARTIFACT_CATALOG.values())
    assert any_name_included


def test_signature_is_configurable(sd: SalesDesk):
    sd.config.setdefault("settings", {})["email_signature"] = "Trust Team"
    email = make_email(
        "user@test.com",
        "ISO",
        "Need ISO 27001 certificate."
    )
    resp = sd.process_request(email)
    assert resp["response_message"].strip().endswith("Trust Team")

