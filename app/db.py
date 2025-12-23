import sqlite3
import time
import hashlib
from pathlib import Path
from app.models import Item

def compute_hash(title: str, url: str, thumb_url: str) -> str:
    h = hashlib.sha256()
    h.update(f"{title}|{url}|{thumb_url}".encode("utf-8"))
    return h.hexdigest()

class DB:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self):
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            thumb_url TEXT,
            local_folder TEXT NOT NULL,
            last_seen_ts INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            has_update INTEGER NOT NULL
        )
        """)
        self.conn.commit()

    def upsert_item(self, item_id, title, url, thumb_url, folder):
        now = int(time.time())
        new_hash = compute_hash(title, url, thumb_url)

        cur = self.conn.execute(
            "SELECT content_hash FROM items WHERE item_id=?",
            (item_id,)
        )
        row = cur.fetchone()

        has_update = 0
        if row is None:
            has_update = 0
        elif row[0] != new_hash:
            has_update = 1

        self.conn.execute("""
        INSERT OR REPLACE INTO items
        VALUES (?,?,?,?,?,?,?,?)
        """, (
            item_id,
            title,
            url,
            thumb_url,
            str(folder),
            now,
            new_hash,
            has_update
        ))
        self.conn.commit()

        return has_update

    def list_items(self):
        cur = self.conn.execute(
            "SELECT * FROM items ORDER BY last_seen_ts DESC"
        )
        return [Item(*r) for r in cur.fetchall()]

    def clear_update_flag(self, item_id: str):
        self.conn.execute(
            "UPDATE items SET has_update=0 WHERE item_id=?",
            (item_id,)
        )
        self.conn.commit()
