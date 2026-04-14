"""SQLite 数据库操作模块"""

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 文件信息
    file_path       TEXT NOT NULL,
    original_path   TEXT NOT NULL,
    file_hash       TEXT NOT NULL UNIQUE,
    file_size       INTEGER,
    format          TEXT,

    -- 提取的线索（来自文件名/目录名）
    parsed_artist   TEXT,
    parsed_title    TEXT,
    parsed_album    TEXT,

    -- 已有的嵌入标签
    existing_title      TEXT,
    existing_artist     TEXT,
    existing_album      TEXT,
    existing_year       TEXT,
    has_existing_cover   INTEGER DEFAULT 0,
    has_existing_lyrics  INTEGER DEFAULT 0,
    has_existing_lrc     INTEGER DEFAULT 0,

    -- 匹配结果
    matched_source      TEXT,
    matched_title       TEXT,
    matched_artist      TEXT,
    matched_album       TEXT,
    matched_year        TEXT,
    matched_song_id     TEXT,
    matched_album_id    TEXT,
    match_confidence    REAL,

    -- 处理状态
    status          TEXT DEFAULT 'new',
    error_message   TEXT,

    -- 标签写入记录
    tagged_fields   TEXT,
    cover_url       TEXT,
    lyrics_source   TEXT,
    lrc_content     TEXT,

    -- 时间戳
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(status);
CREATE INDEX IF NOT EXISTS idx_tracks_hash ON tracks(file_hash);
"""


class Database:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # --- 插入 ---

    def insert_track(self, **kwargs) -> int:
        cols = ", ".join(kwargs.keys())
        placeholders = ", ".join(["?"] * len(kwargs))
        sql = f"INSERT OR IGNORE INTO tracks ({cols}) VALUES ({placeholders})"
        cur = self.conn.execute(sql, list(kwargs.values()))
        self.conn.commit()
        return cur.lastrowid

    # --- 查询 ---

    def get_track(self, track_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM tracks WHERE id = ?", (track_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_track_by_hash(self, file_hash: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM tracks WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        return dict(row) if row else None

    def list_tracks(self, status: str | None = None, limit: int = 100) -> list[dict]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM tracks WHERE status = ? ORDER BY id LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM tracks ORDER BY id LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def count_by_status(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) as cnt FROM tracks GROUP BY status"
        ).fetchall()
        return {r["status"]: r["cnt"] for r in rows}

    def hash_exists(self, file_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM tracks WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        return row is not None

    # --- 更新 ---

    def update_track(self, track_id: int, **kwargs):
        kwargs["updated_at"] = "CURRENT_TIMESTAMP"
        sets = []
        vals = []
        for k, v in kwargs.items():
            if v == "CURRENT_TIMESTAMP":
                sets.append(f"{k} = CURRENT_TIMESTAMP")
            else:
                sets.append(f"{k} = ?")
                vals.append(v)
        vals.append(track_id)
        sql = f"UPDATE tracks SET {', '.join(sets)} WHERE id = ?"
        self.conn.execute(sql, vals)
        self.conn.commit()

    def update_status(self, track_id: int, status: str, error_message: str = None):
        if error_message:
            self.update_track(track_id, status=status, error_message=error_message)
        else:
            self.update_track(track_id, status=status)

    def set_matched(self, track_id: int, source: str, confidence: float, **metadata):
        self.update_track(
            track_id,
            status="matched",
            matched_source=source,
            match_confidence=confidence,
            **metadata,
        )

    def set_tagged(self, track_id: int, tagged_fields: list[str]):
        self.update_track(
            track_id,
            status="tagged",
            tagged_fields=json.dumps(tagged_fields, ensure_ascii=False),
        )

    # --- 统计 ---

    def total_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM tracks").fetchone()
        return row["cnt"]
