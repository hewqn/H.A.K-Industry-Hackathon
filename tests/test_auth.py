"""Accounts: login, admin-only changes, viewer read access, and recorded actors."""

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from hf_followup.api.main import create_app
from hf_followup.repositories.sqlite import SQLiteRepository
from hf_followup.repositories.users import SQLiteUserStore
from hf_followup.services.auth import AuthService, hash_password, verify_password


def _cmd(revision=0):
    return {"command_id": str(uuid.uuid4()), "expected_revision": revision}


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_ADMIN_USERNAME", "")
    monkeypatch.setenv("HF_ADMIN_PASSWORD", "")
    repo = SQLiteRepository(tmp_path / "auth.db")
    with patch("hf_followup.api.main._create_repository", return_value=(repo, "sqlite")):
        with TestClient(create_app()) as c:
            yield c


@pytest.fixture()
def tokens(client):
    admin = client.post("/api/v1/auth/register", json={"username": "Alice", "password": "alice-pass-1"})
    viewer = client.post("/api/v1/auth/register", json={"username": "bob", "password": "bob-pass-12"})
    return {"admin": admin.json(), "viewer": viewer.json()}


def test_password_hash_round_trip():
    stored = hash_password("correct horse")
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong horse", stored)
    assert "correct horse" not in stored


def test_first_account_is_admin_then_viewers(tokens):
    assert tokens["admin"]["user"]["role"] == "admin"
    assert tokens["admin"]["user"]["username"] == "alice"
    assert tokens["viewer"]["user"]["role"] == "viewer"


def test_duplicate_username_rejected(client, tokens):
    resp = client.post("/api/v1/auth/register", json={"username": "ALICE", "password": "another-pass"})
    assert resp.status_code == 409


def test_login_and_me(client, tokens):
    resp = client.post("/api/v1/auth/login", json={"username": "bob", "password": "bob-pass-12"})
    assert resp.status_code == 200
    me = client.get("/api/v1/auth/me", headers=_bearer(resp.json()["access_token"]))
    assert me.json()["username"] == "bob"
    assert "password_hash" not in me.json()


def test_wrong_password_and_bad_token_rejected(client, tokens):
    resp = client.post("/api/v1/auth/login", json={"username": "bob", "password": "nope-nope-nope"})
    assert resp.status_code == 401
    forged = tokens["viewer"]["access_token"][:-2] + "xx"
    assert client.get("/api/v1/auth/me", headers=_bearer(forged)).status_code == 401


def test_login_is_rate_limited(client, tokens):
    for _ in range(8):
        assert client.post("/api/v1/auth/login", json={"username": "bob", "password": "nope-nope-nope"}).status_code == 401
    blocked = client.post("/api/v1/auth/login", json={"username": "bob", "password": "bob-pass-12"})
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "too_many_attempts"


def test_reads_stay_open_without_login(client):
    assert client.get("/api/v1/cohorts/current").status_code == 200


def test_changes_require_login(client):
    resp = client.patch("/api/v1/patients/HF-0001/workflow", json={**_cmd(), "state": "reviewed"})
    assert resp.status_code == 401


def test_viewer_cannot_change_data(client, tokens):
    headers = _bearer(tokens["viewer"]["access_token"])
    resp = client.patch(
        "/api/v1/patients/HF-0001/workflow", json={**_cmd(), "state": "reviewed"}, headers=headers
    )
    assert resp.status_code == 403
    resp = client.request(
        "DELETE", "/api/v1/patients/HF-0001", json={**_cmd(), "reason": "x"}, headers=headers
    )
    assert resp.status_code == 403


def test_admin_change_records_actor(client, tokens):
    headers = _bearer(tokens["admin"]["access_token"])
    resp = client.patch(
        "/api/v1/patients/HF-0001/workflow", json={**_cmd(), "state": "reviewed"}, headers=headers
    )
    assert resp.status_code == 200
    events = client.get("/api/v1/audit-events").json()["events"]
    assert events[-1]["payload"]["performed_by"] == "alice"


def test_admin_manages_roles(client, tokens):
    admin = _bearer(tokens["admin"]["access_token"])
    viewer = _bearer(tokens["viewer"]["access_token"])
    assert client.get("/api/v1/users", headers=viewer).status_code == 403

    users = client.get("/api/v1/users", headers=admin).json()
    bob = next(u for u in users if u["username"] == "bob")
    resp = client.patch(f"/api/v1/users/{bob['user_id']}/role", json={"role": "admin"}, headers=admin)
    assert resp.json()["role"] == "admin"
    # Role changes apply to existing tokens immediately.
    resp = client.patch(
        "/api/v1/patients/HF-0002/workflow", json={**_cmd(), "state": "reviewed"}, headers=viewer
    )
    assert resp.status_code == 200


def test_last_admin_cannot_be_demoted(client, tokens):
    admin = _bearer(tokens["admin"]["access_token"])
    alice_id = tokens["admin"]["user"]["user_id"]
    resp = client.patch(f"/api/v1/users/{alice_id}/role", json={"role": "viewer"}, headers=admin)
    assert resp.status_code == 409


def test_accounts_survive_restart(tmp_path):
    db = tmp_path / "users.db"
    first = AuthService(SQLiteUserStore(db), secret="s")
    first.register("carol", "carol-pass-1")
    token = AuthService(SQLiteUserStore(db), secret="s").login("carol", "carol-pass-1")
    assert token["user"]["role"] == "admin"
