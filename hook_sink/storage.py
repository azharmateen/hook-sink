"""SQLite storage for captured webhooks."""

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class Webhook:
    id: str
    method: str
    path: str
    headers: dict[str, str]
    body: str
    query_params: dict[str, str]
    source_ip: str
    content_type: str
    timestamp: float
    body_size: int

    @property
    def body_json(self) -> Optional[Any]:
        """Try to parse body as JSON."""
        try:
            return json.loads(self.body)
        except (json.JSONDecodeError, TypeError):
            return None

    @property
    def timestamp_iso(self) -> str:
        import datetime
        return datetime.datetime.fromtimestamp(self.timestamp).isoformat()


class WebhookStorage:
    """SQLite-backed storage for webhooks."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(Path.cwd() / ".hook-sink" / "webhooks.db")
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS webhooks (
                id TEXT PRIMARY KEY,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                headers TEXT NOT NULL,
                body TEXT,
                query_params TEXT,
                source_ip TEXT,
                content_type TEXT,
                timestamp REAL NOT NULL,
                body_size INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_webhooks_timestamp ON webhooks(timestamp DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_webhooks_path ON webhooks(path)
        """)
        conn.commit()
        conn.close()

    def store(self, method: str, path: str, headers: dict, body: str,
              query_params: dict, source_ip: str, content_type: str) -> str:
        """Store a webhook and return its ID."""
        webhook_id = uuid.uuid4().hex[:12]
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO webhooks (id, method, path, headers, body, query_params,
               source_ip, content_type, timestamp, body_size)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                webhook_id,
                method,
                path,
                json.dumps(dict(headers)),
                body,
                json.dumps(dict(query_params)),
                source_ip,
                content_type,
                time.time(),
                len(body) if body else 0,
            ),
        )
        conn.commit()
        conn.close()
        return webhook_id

    def _row_to_webhook(self, row: sqlite3.Row) -> Webhook:
        return Webhook(
            id=row["id"],
            method=row["method"],
            path=row["path"],
            headers=json.loads(row["headers"]),
            body=row["body"] or "",
            query_params=json.loads(row["query_params"] or "{}"),
            source_ip=row["source_ip"] or "",
            content_type=row["content_type"] or "",
            timestamp=row["timestamp"],
            body_size=row["body_size"] or 0,
        )

    def get(self, webhook_id: str) -> Optional[Webhook]:
        """Get a webhook by ID."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM webhooks WHERE id = ?", (webhook_id,)).fetchone()
        conn.close()
        if row is None:
            return None
        return self._row_to_webhook(row)

    def list_all(self, limit: int = 50, offset: int = 0) -> list[Webhook]:
        """List webhooks, most recent first."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM webhooks ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        conn.close()
        return [self._row_to_webhook(r) for r in rows]

    def search(self, path: Optional[str] = None, body_contains: Optional[str] = None,
               since: Optional[float] = None, until: Optional[float] = None,
               method: Optional[str] = None) -> list[Webhook]:
        """Search webhooks by various criteria."""
        conditions = []
        params = []

        if path:
            conditions.append("path LIKE ?")
            params.append(f"%{path}%")
        if body_contains:
            conditions.append("body LIKE ?")
            params.append(f"%{body_contains}%")
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)
        if until:
            conditions.append("timestamp <= ?")
            params.append(until)
        if method:
            conditions.append("method = ?")
            params.append(method.upper())

        where = " AND ".join(conditions) if conditions else "1=1"
        conn = self._get_conn()
        rows = conn.execute(
            f"SELECT * FROM webhooks WHERE {where} ORDER BY timestamp DESC LIMIT 100",
            params,
        ).fetchall()
        conn.close()
        return [self._row_to_webhook(r) for r in rows]

    def count(self) -> int:
        """Get total webhook count."""
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) as cnt FROM webhooks").fetchone()
        conn.close()
        return row["cnt"]

    def clear(self) -> int:
        """Delete all webhooks. Returns count deleted."""
        count = self.count()
        conn = self._get_conn()
        conn.execute("DELETE FROM webhooks")
        conn.commit()
        conn.close()
        return count

    def delete(self, webhook_id: str) -> bool:
        """Delete a single webhook."""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
        conn.commit()
        conn.close()
        return cursor.rowcount > 0
