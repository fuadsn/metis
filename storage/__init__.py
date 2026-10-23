"""Transactional evidence storage; legacy JSON snapshots are imported once."""

import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import DATA_DIR
from models import (
    REVIEW_LABELS,
    evidence_fingerprint,
    normalize_post,
    timestamp,
    unique_posts,
)


class Store:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else DATA_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "metis.sqlite3"
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY, source TEXT NOT NULL, created_utc REAL,
                    first_seen REAL NOT NULL, last_seen REAL NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS posts_source_date ON posts(source, created_utc);
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY, recorded_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    post_id TEXT PRIMARY KEY, label TEXT NOT NULL, note TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL, fingerprint TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS research_notes (
                    id TEXT PRIMARY KEY, source TEXT NOT NULL,
                    published_on TEXT, payload TEXT NOT NULL
                );
            """)
            if not db.execute(
                "SELECT 1 FROM metadata WHERE key='legacy_import_complete'"
            ).fetchone():
                self._import_legacy(db)
                db.execute(
                    "INSERT INTO metadata VALUES ('legacy_import_complete', '1')"
                )

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=20)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _import_legacy(self, db):
        batches = []
        for path in (self.root / "raw").glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            batches.append(
                (timestamp(data.get("collection_time")) or path.stat().st_mtime, data)
            )
        for seen_at, data in sorted(batches, key=lambda item: item[0]):
            posts = [
                normalize_post(post, data.get("source"))
                for post in data.get("posts", [])
            ]
            self._upsert(db, unique_posts(posts), seen_at)

    def _upsert(self, db, posts, seen_at):
        counts = {"new": 0, "updated": 0, "unchanged": 0}
        for post in posts:
            row = db.execute(
                "SELECT payload FROM posts WHERE id=?", (post["id"],)
            ).fetchone()
            if row:
                old = json.loads(row[0])
                post["matched_queries"] = sorted(
                    set(old.get("matched_queries", []) + post["matched_queries"])
                )
                counts["updated" if post != old else "unchanged"] += 1
            else:
                counts["new"] += 1
            db.execute(
                """INSERT INTO posts VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET created_utc=excluded.created_utc,
                    last_seen=excluded.last_seen, payload=excluded.payload""",
                (
                    post["id"],
                    post["source"],
                    post["created_utc"],
                    seen_at,
                    seen_at,
                    json.dumps(post),
                ),
            )
        return counts

    def upsert(self, posts):
        with self.connection() as db:
            return self._upsert(
                db, unique_posts(posts), datetime.now(timezone.utc).timestamp()
            )

    def load_posts(self, sources=None, since=None, limit=10000):
        sql, args, conditions = "SELECT payload FROM posts", [], []
        if sources is not None:
            if not sources:
                return []
            conditions.append("source IN (" + ",".join("?" for _ in sources) + ")")
            args.extend(sources)
        if since is not None:
            conditions.append("created_utc >= ?")
            args.append(since)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY last_seen DESC, created_utc DESC, id"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(limit)
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute(sql, args)]

    def counts(self):
        with self.connection() as db:
            return dict(
                db.execute("SELECT source, count(*) FROM posts GROUP BY source")
            )

    def save_result(self, data, filename):
        directory = self.root / "processed"
        directory.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            dir=directory, prefix=".metis-", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(data, output, indent=2, ensure_ascii=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, directory / filename)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load_result(self, filename):
        path = self.root / "processed" / filename
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def record_run(self, result):
        with self.connection() as db:
            db.execute(
                "INSERT INTO runs(recorded_at, payload) VALUES (?, ?)",
                (datetime.now(timezone.utc).isoformat(), json.dumps(result)),
            )
        self.save_result(result, "latest_collection.json")

    def save_review(self, post_id, label, note=""):
        if label not in REVIEW_LABELS:
            raise ValueError("Review label must be opportunity, support, or noise")
        if len(note) > 2000:
            raise ValueError("Review note must be at most 2000 characters")
        reviewed_at = datetime.now(timezone.utc).isoformat()
        with self.connection() as db:
            row = db.execute(
                "SELECT payload FROM posts WHERE id=?", (post_id,)
            ).fetchone()
            if not row:
                raise ValueError("Post ID was not found in the local evidence store")
            fingerprint = evidence_fingerprint(json.loads(row[0]))
            db.execute(
                """INSERT INTO reviews VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(post_id) DO UPDATE SET label=excluded.label,
                       note=excluded.note, reviewed_at=excluded.reviewed_at,
                       fingerprint=excluded.fingerprint""",
                (post_id, label, note, reviewed_at, fingerprint),
            )
        return {
            "status": "success",
            "post_id": post_id,
            "label": label,
            "reviewed_at": reviewed_at,
        }

    def reviewed_posts(self):
        with self.connection() as db:
            return [
                {
                    "post": json.loads(payload),
                    "label": label,
                    "fingerprint": fingerprint,
                }
                for payload, label, fingerprint in db.execute(
                    "SELECT p.payload, r.label, r.fingerprint FROM reviews r JOIN posts p ON p.id=r.post_id ORDER BY r.post_id"
                )
            ]


# Compatibility for existing Python consumers. IDs are now source-qualified.
def save_raw_posts(posts, source):
    result = Store().upsert([normalize_post(post, source) for post in posts])
    return result["new"]


def load_raw_posts(source: Optional[str] = None, limit=10000):
    return Store().load_posts(sources=[source] if source else None, limit=limit)


def get_all_post_ids():
    with Store().connection() as db:
        return {row[0] for row in db.execute("SELECT id FROM posts")}


def save_processed_data(data, filename):
    Store().save_result(data, filename)


def load_processed_data(filename):
    return Store().load_result(filename)
