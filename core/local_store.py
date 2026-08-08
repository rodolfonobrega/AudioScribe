"""Local-first persistence for AudioScribe."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_data_dir() -> Path:
    configured = os.getenv("AUDIOSCRIBE_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / "AudioScribe"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AudioScribe"
    return Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "audioscribe"


class LocalStore:
    """Thread-safe SQLite store for history, dictionary and snippets."""

    def __init__(self, db_path: Optional[str | Path] = None, history_enabled: Optional[bool] = None):
        self.db_path = Path(db_path or (default_data_dir() / "audioscribe.db")).expanduser()
        # Production history is opt-in. Explicit database paths are used by
        # tests and diagnostic tools, where retaining the requested sample is
        # the least surprising behavior.
        self.history_enabled = history_enabled if history_enabled is not None else (
            db_path is not None or os.getenv("AUDIOSCRIBE_HISTORY_ENABLED", "0") == "1"
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._db = sqlite3.connect(self.db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA secure_delete=ON")
        self._migrate()

    @classmethod
    def temporary(cls) -> "LocalStore":
        return cls(Path(tempfile.mkdtemp(prefix="audioscribe-store-")) / "test.db")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _migrate(self) -> None:
        with self._lock, self._db:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS transcriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id TEXT NOT NULL UNIQUE,
                    text TEXT NOT NULL,
                    raw_text TEXT,
                    status TEXT NOT NULL DEFAULT 'completed',
                    source TEXT NOT NULL DEFAULT 'dictation',
                    model TEXT,
                    provider TEXT,
                    language TEXT,
                    duration_ms INTEGER,
                    audio_path TEXT,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_transcriptions_created
                    ON transcriptions(created_at DESC);
                CREATE TABLE IF NOT EXISTS dictionary_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    source TEXT NOT NULL DEFAULT 'manual',
                    use_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT
                );
                CREATE TABLE IF NOT EXISTS snippets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trigger TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    replacement TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT
                );
                """
            )

    @staticmethod
    def _row(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
        return dict(row) if row is not None else None

    def save_transcription(self, text: str, raw_text: Optional[str] = None, **metadata: Any) -> Dict[str, Any]:
        if not self.history_enabled:
            return {}
        now = utc_now()
        values = {
            "status": "completed", "source": "dictation", "model": None,
            "provider": None, "language": None, "duration_ms": None,
            "audio_path": None, "error_code": None,
        }
        values.update({key: metadata[key] for key in values if key in metadata})
        with self._lock, self._db:
            cursor = self._db.execute(
                """INSERT INTO transcriptions
                (client_id, text, raw_text, status, source, model, provider, language,
                 duration_ms, audio_path, error_code, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                # Audio and raw transcription are deliberately never retained.
                (str(uuid.uuid4()), text, None, values["status"], values["source"],
                 values["model"], values["provider"], values["language"], values["duration_ms"],
                 values["audio_path"], values["error_code"], now, now),
            )
            row = self._db.execute("SELECT * FROM transcriptions WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._row(row) or {}

    def list_transcriptions(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        if not self.history_enabled:
            return []
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM transcriptions WHERE deleted_at IS NULL ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (max(1, min(int(limit), 500)), max(0, int(offset))),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_transcription(self, transcription_id: int) -> bool:
        with self._lock, self._db:
            result = self._db.execute(
                "DELETE FROM transcriptions WHERE id = ?",
                (int(transcription_id),),
            )
        return result.rowcount > 0

    def clear_transcriptions(self) -> int:
        with self._lock, self._db:
            result = self._db.execute("DELETE FROM transcriptions")
            self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._db.execute("VACUUM")
        return result.rowcount

    @staticmethod
    def _normalize_words(words: Iterable[str]) -> List[str]:
        seen, result = set(), []
        for raw in words or []:
            if not isinstance(raw, str):
                continue
            word = raw.strip()
            if word and word.casefold() not in seen:
                seen.add(word.casefold())
                result.append(word)
        return result

    def list_dictionary(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM dictionary_entries WHERE deleted_at IS NULL ORDER BY id ASC").fetchall()
        return [dict(row) for row in rows]

    def add_dictionary_words(self, words: Iterable[str], source: str = "manual") -> int:
        source = source if source in {"manual", "learned"} else "manual"
        now, added = utc_now(), 0
        with self._lock, self._db:
            for word in self._normalize_words(words):
                result = self._db.execute(
                    """INSERT INTO dictionary_entries (word, source, created_at, updated_at)
                    VALUES (?, ?, ?, ?) ON CONFLICT(word) DO UPDATE SET deleted_at = NULL,
                    source = CASE WHEN dictionary_entries.source = 'learned' AND excluded.source = 'manual'
                                  THEN 'manual' ELSE dictionary_entries.source END,
                    updated_at = excluded.updated_at""", (word, source, now, now)
                )
                added += max(result.rowcount, 0)
        return added

    def remove_dictionary_words(self, words: Iterable[str]) -> int:
        normalized = self._normalize_words(words)
        if not normalized:
            return 0
        now = utc_now()
        placeholders = ",".join("?" for _ in normalized)
        with self._lock, self._db:
            result = self._db.execute(
                f"UPDATE dictionary_entries SET deleted_at = ?, updated_at = ? WHERE lower(word) IN ({placeholders}) AND deleted_at IS NULL",
                (now, now, *[word.casefold() for word in normalized]),
            )
        return result.rowcount

    def list_snippets(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        where = "WHERE deleted_at IS NULL" + (" AND enabled = 1" if enabled_only else "")
        with self._lock:
            rows = self._db.execute(f"SELECT * FROM snippets {where} ORDER BY id ASC").fetchall()
        return [dict(row) for row in rows]

    def upsert_snippet(self, trigger: str, replacement: str, enabled: bool = True, snippet_id: Optional[int] = None) -> Dict[str, Any]:
        trigger, replacement = str(trigger or "").strip(), str(replacement or "").strip()
        if not trigger or not replacement:
            raise ValueError("Snippet trigger and replacement are required")
        now = utc_now()
        with self._lock, self._db:
            if snippet_id is not None:
                self._db.execute(
                    "UPDATE snippets SET trigger = ?, replacement = ?, enabled = ?, updated_at = ?, deleted_at = NULL WHERE id = ?",
                    (trigger, replacement, int(bool(enabled)), now, int(snippet_id)),
                )
                row = self._db.execute("SELECT * FROM snippets WHERE id = ?", (int(snippet_id),)).fetchone()
            else:
                self._db.execute(
                    """INSERT INTO snippets (trigger, replacement, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?) ON CONFLICT(trigger) DO UPDATE SET replacement = excluded.replacement,
                    enabled = excluded.enabled, updated_at = excluded.updated_at, deleted_at = NULL""",
                    (trigger, replacement, int(bool(enabled)), now, now),
                )
                row = self._db.execute("SELECT * FROM snippets WHERE lower(trigger) = lower(?)", (trigger,)).fetchone()
        return self._row(row) or {}

    def delete_snippet(self, snippet_id: int) -> bool:
        now = utc_now()
        with self._lock, self._db:
            result = self._db.execute(
                "UPDATE snippets SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                (now, now, int(snippet_id)),
            )
        return result.rowcount > 0
