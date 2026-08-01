from types import SimpleNamespace
import pytest

from core.model_discovery import discover_models
from core.usage import PriceCatalog, UsageRecord, UsageStore, extract_usage, response_cost


def test_usage_store_aggregates_known_and_unknown_costs(tmp_path):
    store = UsageStore(str(tmp_path / "usage.sqlite3"))
    store.record(UsageRecord("a", "transcription", "groq", "groq/whisper-large-v3-turbo", "success", audio_seconds=3600, estimated_cost_usd=0.04, price_source="catalog"))
    store.record(UsageRecord("b", "llm", "groq", "unknown-model", "success", input_tokens=10, output_tokens=5))

    summary = store.summary()
    assert summary["requests"] == 2
    assert summary["estimated_cost_usd"] == 0.04
    assert summary["cost_known"] is True
    assert len(summary["by_model"]) == 2


def test_usage_helpers_read_dict_and_object_metadata():
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=4, completion_tokens=7), response_cost="0.012")
    assert extract_usage(response) == {"input_tokens": 4, "output_tokens": 7}
    assert response_cost(response) == 0.012
    assert PriceCatalog().estimate_transcription("not-catalogued", 10) == (None, "unknown")
    cost, source = PriceCatalog().estimate_llm("groq/openai/gpt-oss-120b", 1_000_000, 500_000)
    assert cost == pytest.approx(0.45)
    assert source == "catalog:groq-docs"


def test_ollama_discovery_uses_native_tags_endpoint(monkeypatch):
    seen = {}

    def fake_get_json(url, api_key=None, timeout=3.0):
        seen["url"] = url
        return {"models": [{"name": "qwen2.5:7b", "details": {"family": "qwen2"}}]}

    monkeypatch.setattr("core.model_discovery._get_json", fake_get_json)
    models = discover_models("http://127.0.0.1:11434/v1", None, "ollama")
    assert seen["url"] == "http://127.0.0.1:11434/api/tags"
    assert models[0]["id"] == "qwen2.5:7b"
    assert models[0]["local"] is True
