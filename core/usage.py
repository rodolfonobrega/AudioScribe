"""Local usage and estimated API cost tracking."""

from __future__ import annotations

import io
import os
import sqlite3
import threading
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class UsageRecord:
    request_id: str
    operation: str
    provider: str
    model: str
    status: str
    latency_ms: Optional[float] = None
    audio_seconds: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    price_source: str = "unknown"
    fallback_used: bool = False
    error_code: Optional[str] = None


def audio_duration_seconds(audio_data: bytes) -> Optional[float]:
    """Return WAV duration without failing the transcription pipeline."""
    try:
        with wave.open(io.BytesIO(audio_data), "rb") as wav:
            return wav.getnframes() / float(wav.getframerate())
    except Exception:
        return None


def extract_usage(response: Any) -> Dict[str, Optional[int]]:
    usage = response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
    if usage is None:
        return {"input_tokens": None, "output_tokens": None}
    getter = usage.get if isinstance(usage, dict) else lambda key, default=None: getattr(usage, key, default)
    return {
        "input_tokens": getter("prompt_tokens", getter("input_tokens")),
        "output_tokens": getter("completion_tokens", getter("output_tokens")),
    }


def response_cost(response: Any) -> Optional[float]:
    """Read provider/LiteLLM cost metadata when available."""
    if isinstance(response, dict):
        value = response.get("cost") or response.get("response_cost")
    else:
        value = getattr(response, "response_cost", None)
        if value is None:
            hidden = getattr(response, "_hidden_params", {}) or {}
            value = hidden.get("response_cost")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class PriceCatalog:
    """Conservative catalog; unknown models intentionally return unknown cost."""

    TRANSCRIPTION_PER_HOUR_USD = {
        "groq/whisper-large-v3-turbo": 0.04,
        "groq/whisper-large-v3": 0.111,
    }
    LLM_PER_MILLION_TOKENS_USD = {
        "groq/openai/gpt-oss-120b": (0.15, 0.60),
        "openai/gpt-oss-120b": (0.15, 0.60),
        "groq/openai/gpt-oss-20b": (0.075, 0.30),
        "openai/gpt-oss-20b": (0.075, 0.30),
    }

    def estimate_transcription(self, model: str, seconds: Optional[float]) -> tuple[Optional[float], str]:
        if seconds is None or model not in self.TRANSCRIPTION_PER_HOUR_USD:
            return None, "unknown"
        return seconds / 3600.0 * self.TRANSCRIPTION_PER_HOUR_USD[model], "catalog:groq-docs"

    def estimate_llm(self, model: str, input_tokens: Optional[int], output_tokens: Optional[int]) -> tuple[Optional[float], str]:
        prices = self.LLM_PER_MILLION_TOKENS_USD.get(model)
        if not prices or input_tokens is None or output_tokens is None:
            return None, "unknown"
        input_price, output_price = prices
        cost = (input_tokens / 1_000_000 * input_price) + (output_tokens / 1_000_000 * output_price)
        return cost, "catalog:groq-docs"


class UsageStore:
    def __init__(self, path: Optional[str] = None):
        default_dir = Path(os.getenv("AUDIOSCRIBE_DATA_DIR", Path.home() / ".audioscribe"))
        self.path = Path(path or default_dir / "usage.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self):
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS usage_records (
                    request_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    latency_ms REAL,
                    audio_seconds REAL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    estimated_cost_usd REAL,
                    price_source TEXT NOT NULL,
                    fallback_used INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )

    def record(self, record: UsageRecord) -> None:
        values = asdict(record)
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT INTO usage_records (
                    request_id, operation, provider, model, status, latency_ms,
                    audio_seconds, input_tokens, output_tokens, estimated_cost_usd,
                    price_source, fallback_used, error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    values["request_id"], values["operation"], values["provider"], values["model"],
                    values["status"], values["latency_ms"], values["audio_seconds"],
                    values["input_tokens"], values["output_tokens"], values["estimated_cost_usd"],
                    values["price_source"], int(values["fallback_used"]), values["error_code"],
                ),
            )

    def summary(self) -> Dict[str, Any]:
        with self._connect() as db:
            row = db.execute(
                """SELECT COUNT(*) AS requests,
                          COALESCE(SUM(audio_seconds), 0) AS audio_seconds,
                          COALESCE(SUM(input_tokens), 0) AS input_tokens,
                          COALESCE(SUM(output_tokens), 0) AS output_tokens,
                          SUM(estimated_cost_usd) AS estimated_cost_usd
                   FROM usage_records"""
            ).fetchone()
            by_model = db.execute(
                """SELECT provider, model, COUNT(*) AS requests,
                          SUM(estimated_cost_usd) AS estimated_cost_usd
                   FROM usage_records GROUP BY provider, model
                   ORDER BY requests DESC"""
            ).fetchall()
        result = dict(row)
        result["cost_known"] = result["estimated_cost_usd"] is not None
        result["by_model"] = [dict(item) for item in by_model]
        return result
