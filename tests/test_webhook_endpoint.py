import pytest
from fastapi.testclient import TestClient

import main
import agent


@pytest.fixture
def client(monkeypatch):
    calls = []
    monkeypatch.setattr(
        agent, "run_expense_flow",
        lambda **kw: calls.append(kw) or {"success": True},
    )
    main._SEEN_UPDATE_IDS.clear()
    c = TestClient(main.app)
    c.calls = calls
    return c


def _update(update_id=1, text="اشتريت قهوة ب50", user_id=123456):
    return {
        "update_id": update_id,
        "message": {
            "message_id": 1,
            "from": {"id": user_id},
            "chat": {"id": user_id},
            "date": 1_756_700_000,
            "text": text,
        },
    }


def test_valid_update_is_processed_once(client):
    r = client.post("/webhook", json=_update(update_id=10))
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert len(client.calls) == 1


def test_duplicate_update_id_is_not_reprocessed(client):
    client.post("/webhook", json=_update(update_id=11))
    r = client.post("/webhook", json=_update(update_id=11))
    assert r.json()["status"] == "duplicate"
    assert len(client.calls) == 1


def test_unauthorized_user_is_rejected(client):
    r = client.post("/webhook", json=_update(update_id=12, user_id=999))
    assert r.json()["status"] == "unauthorized"
    assert client.calls == []


def test_non_message_update_is_ignored(client):
    r = client.post("/webhook", json={"update_id": 13, "edited_message": {}})
    assert r.json()["status"] == "ignored"


def test_agent_exception_does_not_leak_internals(client, monkeypatch):
    def boom(**kw):
        raise RuntimeError("secret internal detail")
    monkeypatch.setattr(agent, "run_expense_flow", boom)
    r = client.post("/webhook", json=_update(update_id=14))
    assert r.status_code == 200
    assert r.json() == {"status": "error"}
    assert "secret internal detail" not in r.text


def test_webhook_secret_enforced_when_configured(client, monkeypatch):
    monkeypatch.setattr(main.config, "TELEGRAM_WEBHOOK_SECRET", "s3cr3t")
    bad = client.post("/webhook", json=_update(update_id=15))
    assert bad.status_code == 403
    assert client.calls == []
    good = client.post(
        "/webhook",
        json=_update(update_id=16),
        headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t"},
    )
    assert good.status_code == 200 and good.json()["status"] == "ok"


def test_health_check(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "healthy"
