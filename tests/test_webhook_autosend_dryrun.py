import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import webhook_server as ws


def test_process_new_emails_autosend_dryrun(monkeypatch):
    # Enable auto-send and dry-run
    ws.CONFIG.setdefault("settings", {})["auto_send_when_approved"] = True
    ws.CONFIG["settings"]["dry_run"] = True

    # Track if send_email gets called (should not in dry-run)
    called = {"send": 0}

    class FakeGmail:
        def list_history_new_message_ids(self, start_history_id: str, max_pages: int = 1):
            return ["abc123"]
        def read_email_details(self, message_id: str):
            return {"from": "user@example.com", "subject": "Hi", "body": "soc 2", "thread_id": None}
        def send_email(self, **kwargs):
            called["send"] += 1
            return "ok"

    monkeypatch.setattr(ws, "gmail_tool", FakeGmail())

    class FakeSales:
        def process_request(self, email_data):
            return {
                "detected_artifacts": ["soc2"],
                "requires_nda": False,
                "nda_on_file": True,
                "approved_artifacts": ["soc2"],
                "denied_artifacts": [],
                "share_method": "secure_link",
                "link_expiration": datetime.now().isoformat(),
                "response_message": "here",
                "requires_human_review": False,
                "routing_reason": None,
            }

    monkeypatch.setattr(ws, "sales_desk", FakeSales())

    # Invoke
    ws.asyncio.get_event_loop().run_until_complete(ws.process_new_emails("me@example.com", "1"))

    # Should not send when dry-run is true
    assert called["send"] == 0

