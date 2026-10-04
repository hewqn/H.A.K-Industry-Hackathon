"""TestClient that starts the app with a seeded admin and sends its bearer token."""

import os
from unittest.mock import patch

from fastapi.testclient import TestClient

ADMIN = {"username": "test-admin", "password": "test-admin-password"}


class AdminClient(TestClient):
    def __enter__(self):
        env = {"HF_ADMIN_USERNAME": ADMIN["username"], "HF_ADMIN_PASSWORD": ADMIN["password"]}
        with patch.dict(os.environ, env):
            client = super().__enter__()
        token = client.post("/api/v1/auth/login", json=ADMIN).json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        return client
