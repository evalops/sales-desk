import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import utils


def test_notify_escalation_posts_when_enabled(monkeypatch):
    posted = {"called": 0, "payload": None}

    def fake_post(url, json=None, timeout=5):  # noqa: A002
        posted["called"] = posted["called"] + 1
        posted["payload"] = json
        class Resp:
            status_code = 200
        return Resp()

    class FakeRequests:
        def post(self, *args, **kwargs):
            return fake_post(*args, **kwargs)

    monkeypatch.setattr(utils, "requests", FakeRequests())
    cfg = {"settings": {"notifications": {"slack": {"enabled": True, "webhook_url": "http://example"}}}}
    utils.notify_escalation(cfg, "user@example.com", "Requires review", {"foo": "bar"})
    assert posted["called"] == 1
    assert "Escalation" in posted["payload"]["text"]


def test_notify_escalation_noop_when_disabled(monkeypatch):
    posted = {"called": 0}

    def fake_post(url, json=None, timeout=5):  # noqa: A002
        posted["called"] = posted["called"] + 1
        class Resp:
            status_code = 200
        return Resp()

    class FakeRequests:
        def post(self, *args, **kwargs):
            return fake_post(*args, **kwargs)

    monkeypatch.setattr(utils, "requests", FakeRequests())
    cfg = {"settings": {"notifications": {"slack": {"enabled": False, "webhook_url": "http://example"}}}}
    utils.notify_escalation(cfg, "user@example.com", "Requires review", {"foo": "bar"})
    assert posted["called"] == 0

