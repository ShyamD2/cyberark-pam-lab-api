import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.main import store as app_store
from app.store import LabStore, seed

AUTH = {"X-API-Key": "lab-demo-key"}


@pytest.fixture()
def client() -> TestClient:
    seed(app_store)
    return TestClient(app)


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_summary_matches_seed(client: TestClient) -> None:
    body = client.get("/api/v1/summary").json()
    assert body["total_safes"] == 3
    assert body["total_accounts"] == 6
    assert body["accounts_by_status"]["compliant"] == 3
    assert body["active_sessions"] == 2
    assert body["compliance_rate"] == 0.5
    assert sum(s["account_count"] for s in body["accounts_per_safe"]) == 6


def test_write_requires_api_key(client: TestClient) -> None:
    resp = client.post("/api/v1/safes", json={"name": "NOPE"})
    assert resp.status_code == 401


def test_safe_crud_and_account_lifecycle(client: TestClient) -> None:
    safe = client.post("/api/v1/safes", json={"name": "APP-TEAM"}, headers=AUTH).json()
    assert client.post("/api/v1/safes", json={"name": "app-team"}, headers=AUTH).status_code == 409

    patched = client.patch(
        f"/api/v1/safes/{safe['id']}", json={"description": "app team safe"}, headers=AUTH
    ).json()
    assert patched["description"] == "app team safe"

    account = client.post(
        "/api/v1/accounts",
        json={"username": "svc_app", "address": "app03.pam.lab", "safe_id": safe["id"]},
        headers=AUTH,
    ).json()
    assert account["status"] == "pending_rotation"
    assert account["last_rotated_at"] is None

    assert client.delete(f"/api/v1/safes/{safe['id']}", headers=AUTH).status_code == 409

    rotated = client.post(f"/api/v1/accounts/{account['id']}/rotate", headers=AUTH).json()
    assert rotated["status"] == "compliant"
    assert rotated["last_rotated_at"] is not None

    assert client.delete(f"/api/v1/accounts/{account['id']}", headers=AUTH).status_code == 204
    assert client.delete(f"/api/v1/safes/{safe['id']}", headers=AUTH).status_code == 204
    assert client.get(f"/api/v1/safes/{safe['id']}").status_code == 404


def test_account_filters(client: TestClient) -> None:
    safe_id = client.get("/api/v1/safes").json()[0]["id"]
    assert all(a["safe_id"] == safe_id for a in client.get(f"/api/v1/accounts?safe_id={safe_id}").json())
    failed = client.get("/api/v1/accounts?status=failed").json()
    assert [a["address"] for a in failed] == ["app02.pam.lab"]
    assert len(client.get("/api/v1/accounts?risk_level=critical").json()) == 2


def test_session_lifecycle_and_disabled_account(client: TestClient) -> None:
    accounts = client.get("/api/v1/accounts").json()
    disabled = next(a for a in accounts if a["status"] == "disabled")
    enabled = next(a for a in accounts if a["status"] == "compliant")

    resp = client.post(
        "/api/v1/sessions", json={"account_id": disabled["id"], "requested_by": "eve"}, headers=AUTH
    )
    assert resp.status_code == 409

    session = client.post(
        "/api/v1/sessions", json={"account_id": enabled["id"], "requested_by": "dan"}, headers=AUTH
    ).json()
    assert session["status"] == "active"
    assert client.delete(f"/api/v1/accounts/{enabled['id']}", headers=AUTH).status_code == 409

    terminated = client.post(f"/api/v1/sessions/{session['id']}/terminate", headers=AUTH).json()
    assert terminated["status"] == "terminated"
    assert terminated["ended_at"] is not None
    assert client.post(f"/api/v1/sessions/{session['id']}/terminate", headers=AUTH).status_code == 409


def test_unknown_ids_return_404(client: TestClient) -> None:
    assert client.get("/api/v1/accounts/acct-missing").status_code == 404
    assert client.post("/api/v1/accounts/acct-missing/rotate", headers=AUTH).status_code == 404
    assert client.get("/api/v1/sessions").status_code == 200


def test_seed_is_reproducible() -> None:
    store = seed(LabStore())
    assert len(store.safes) == 3
    assert len(store.accounts) == 6
    assert len(store.list_sessions()) == 3
