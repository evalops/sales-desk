import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gmail_monitor import GmailMonitor


class DummyGmail:
    def send_email(self, **kwargs):
        raise RuntimeError("Should not be called in dry-run")


def test_send_response_dry_run(monkeypatch):
    m = GmailMonitor()
    # Force dry-run in config
    m.config.setdefault("settings", {})["dry_run"] = True
    m.gmail = DummyGmail()
    resp = {"response_message": "Hello", "message_id": "x", "thread_id": None}
    ok = m.send_response(resp, "user@example.com")
    assert ok is True

