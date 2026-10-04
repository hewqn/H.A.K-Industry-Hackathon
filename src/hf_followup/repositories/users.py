"""User account stores: Databricks Delta (primary), SQLite (offline), in-memory (tests)."""

import sqlite3
import threading
from pathlib import Path

_FIELDS = ("user_id", "username", "password_hash", "role", "created_at")


class InMemoryUserStore:
    def __init__(self):
        self._users: dict[str, dict] = {}

    def create(self, user: dict) -> dict:
        self._users[user["user_id"]] = dict(user)
        return dict(user)

    def get_by_id(self, user_id: str) -> dict | None:
        user = self._users.get(user_id)
        return dict(user) if user else None

    def get_by_username(self, username: str) -> dict | None:
        return next((dict(u) for u in self._users.values() if u["username"] == username), None)

    def list_all(self) -> list[dict]:
        return sorted((dict(u) for u in self._users.values()), key=lambda u: u["created_at"])

    def count(self) -> int:
        return len(self._users)

    def set_role(self, user_id: str, role: str) -> None:
        self._users[user_id]["role"] = role


class SQLiteUserStore:
    def __init__(self, db_path: str | Path):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS users ("
                "user_id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, "
                "password_hash TEXT NOT NULL, role TEXT NOT NULL, created_at TEXT NOT NULL)"
            )

    def _one(self, sql: str, params: tuple) -> dict | None:
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def create(self, user: dict) -> dict:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO users (user_id, username, password_hash, role, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                tuple(user[f] for f in _FIELDS),
            )
        return dict(user)

    def get_by_id(self, user_id: str) -> dict | None:
        return self._one("SELECT * FROM users WHERE user_id = ?", (user_id,))

    def get_by_username(self, username: str) -> dict | None:
        return self._one("SELECT * FROM users WHERE username = ?", (username,))

    def list_all(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        return self._one("SELECT COUNT(*) AS n FROM users", ())["n"]

    def set_role(self, user_id: str, role: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))


class DatabricksUserStore:
    """Users live in the Delta table ``<catalog>.<schema>.users``.

    Username uniqueness is enforced by the single API writer, not a Delta constraint.
    """

    def __init__(self, repo):
        self._repo = repo
        self._table = repo._table("users")
        with repo.connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {self._table} "
                "(user_id STRING, username STRING, password_hash STRING, role STRING, "
                "created_at STRING) USING DELTA"
            )

    def _query(self, sql: str, params: list) -> list[dict]:
        with self._repo.connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [dict(zip(_FIELDS, row, strict=True)) for row in rows]

    def _select(self, where: str, params: list) -> dict | None:
        rows = self._query(
            f"SELECT {', '.join(_FIELDS)} FROM {self._table} WHERE {where} LIMIT 1", params
        )
        return rows[0] if rows else None

    def create(self, user: dict) -> dict:
        with self._repo.connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {self._table} ({', '.join(_FIELDS)}) VALUES (?, ?, ?, ?, ?)",
                [user[f] for f in _FIELDS],
            )
        return dict(user)

    def get_by_id(self, user_id: str) -> dict | None:
        return self._select("user_id = ?", [user_id])

    def get_by_username(self, username: str) -> dict | None:
        return self._select("username = ?", [username])

    def list_all(self) -> list[dict]:
        return self._query(
            f"SELECT {', '.join(_FIELDS)} FROM {self._table} ORDER BY created_at", []
        )

    def count(self) -> int:
        with self._repo.connect() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {self._table}")
            return cur.fetchone()[0]

    def set_role(self, user_id: str, role: str) -> None:
        with self._repo.connect() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE {self._table} SET role = ? WHERE user_id = ?", [role, user_id])
