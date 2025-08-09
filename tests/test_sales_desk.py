import json
import re
import os
import sys

import pytest

# Ensure project root is on sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sales_desk import SalesDesk, ARTIFACT_CATALOG


@pytest.fixture()
def sd():
    return SalesDesk()


def make_email(sender: str, subject: str, body: str):
    return {"from": sender, "subject": subject, "body": body}


def test_detection_basic(sd: SalesDesk):
    email = make_email(
        "buyer@example.com",
        "Security Documents",
        "Please share your SOC 2 report and security whitepaper."
    )
    resp = sd.process_request(email)
    assert "soc2" in resp["detected_artifacts"]
    assert "security_whitepaper" in resp["detected_artifacts"]


def test_policy_no_nda_denies_sensitive(sd: SalesDesk):
    email = make_email(
        "buyer@newco.com",
        "Due diligence",
        "We need SOC2 and your privacy policy."
    )
    resp = sd.process_request(email)
    # SOC2 requires NDA, privacy policy does not
    assert "soc2" in resp["denied_artifacts"]
    assert "privacy_policy" in resp["approved_artifacts"]
    assert resp["requires_nda"] is True


def test_policy_with_nda_allows_sensitive(sd: SalesDesk):
    email = make_email(
        "acme@example.com",
        "Security",
        "Please send SOC2 and latest penetration test."
    )
    resp = sd.process_request(email)
    assert set(["soc2", "pentest"]).issubset(set(resp["approved_artifacts"]))
    assert not resp["denied_artifacts"]
    assert resp["nda_on_file"] is True


def test_domain_wildcard_nda(sd: SalesDesk):
    # config.yaml has *@enterprise.com
    email = make_email(
        "alice@enterprise.com",
        "SOC 2",
        "Requesting SOC 2 report."
    )
    resp = sd.process_request(email)
    assert resp["nda_on_file"] is True
    assert "soc2" in resp["approved_artifacts"]


def test_response_template_and_signature(sd: SalesDesk):
    # ISO27001 does not require NDA; tests approved template path and signature
    email = make_email(
        "user@test.com",
        "Need ISO",
        "Could you share your ISO 27001 certificate?"
    )
    resp = sd.process_request(email)
    msg = resp["response_message"].lower()
    assert "iso 27001" in msg
    assert "valid for 7 days" in msg
    assert "sales desk team" in msg


def test_escalation_keywords_trigger_review(sd: SalesDesk):
    email = make_email(
        "user@test.com",
        "Contract question",
        "We need your security docs, and our legal team requires contract terms."
    )
    resp = sd.process_request(email)
    assert resp["requires_human_review"] is True
    assert resp["routing_reason"] is not None


def test_unclear_request_routes_to_human(sd: SalesDesk):
    email = make_email(
        "user@test.com",
        "Hello",
        "Can you tell me more about your product?"
    )
    resp = sd.process_request(email)
    assert not resp["detected_artifacts"]
    assert resp["requires_human_review"] is True
    assert resp["routing_reason"] == "Unable to detect specific document request"
