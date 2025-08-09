import base64
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
import webhook_server as ws


@pytest.fixture(autouse=True)
def set_secret(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SHARED_SECRET", "testsecret")
    yield


def make_message(data: dict) -> dict:
    raw = base64.b64encode(json.dumps(data).encode()).decode()
    return {"message": {"data": raw}}


def test_health_endpoint():
    client = TestClient(ws.app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_webhook_rejects_bad_secret():
    client = TestClient(ws.app)
    payload = make_message({"emailAddress": "test@example.com", "historyId": "123"})
    r = client.post("/webhook/gmail", headers={"x-webhook-secret": "wrong"}, json=payload)
    assert r.status_code == 401


def test_webhook_missing_history():
    client = TestClient(ws.app)
    payload = make_message({"emailAddress": "test@example.com"})
    r = client.post("/webhook/gmail", headers={"x-webhook-secret": "testsecret"}, json=payload)
    assert r.status_code == 400


def test_webhook_accepts_valid():
    client = TestClient(ws.app)
    payload = make_message({"emailAddress": "test@example.com", "historyId": "123"})
    r = client.post("/webhook/gmail", headers={"x-webhook-secret": "testsecret"}, json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") in {"accepted", "ignored"}

