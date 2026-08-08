"""
AudioScribe Silent Error Audit Test Suite
Verifies that all core components report errors explicitly instead of failing silently or swallowing exceptions without notification.
"""

import pytest
import asyncio
import json
from unittest.mock import MagicMock

from core.implementations.transcription.litellm_transcriber import LiteLLMTranscriber
from core.implementations.llm.litellm_processor import LiteLLMProcessor
from core.implementations.transcription.fallback_transcriber import FallbackTranscriber
from core.implementations.llm.fallback_llm_processor import FallbackLLMProcessor
from core.implementations.output.output_handlers import ClipboardOutputHandler, ConsoleOutputHandler
from core.api.server import AudioScribeServer


class DummyConfig:
    def __init__(self, api_key="", model="invalid/model"):
        self.api_key = api_key
        self.model = model
        self.model_chain = [model]
        self.language = "pt"
        self.temperature = 0.0
        self.max_tokens = 100
        self.system_prompt = "Test prompt"


def test_transcriber_health_check_raises_on_invalid_key_or_model():
    """Verify transcriber health check raises RuntimeError on invalid API key or model."""
    cfg = DummyConfig(api_key="invalid_key_12345", model="groq/nonexistent-model")
    transcriber = LiteLLMTranscriber(cfg)
    
    with pytest.raises(RuntimeError) as exc_info:
        transcriber.health_check()
    
    assert "validation failed" in str(exc_info.value)


def test_llm_processor_health_check_raises_on_invalid_key_or_model():
    """Verify LLM processor health check raises RuntimeError on invalid API key or model."""
    cfg = DummyConfig(api_key="invalid_key_12345", model="groq/nonexistent-model")
    processor = LiteLLMProcessor(cfg)
    
    with pytest.raises(RuntimeError) as exc_info:
        processor.health_check()
    
    assert "validation failed" in str(exc_info.value)


def test_fallback_transcriber_returns_none_when_all_exhausted():
    """Verify FallbackTranscriber cleanly returns None when all chained models fail."""
    mock_t1 = MagicMock()
    mock_t1.transcribe.side_effect = RuntimeError("Primary STT failed")
    mock_t2 = MagicMock()
    mock_t2.transcribe.side_effect = RuntimeError("Secondary STT failed")

    fallback = FallbackTranscriber([mock_t1, mock_t2])
    result = fallback.transcribe(b"dummy_bytes")
    
    assert result is None, "FallbackTranscriber should return None when all models fail"


def test_fallback_llm_returns_none_when_all_exhausted():
    """Verify FallbackLLMProcessor cleanly returns None when all chained models fail."""
    mock_l1 = MagicMock()
    mock_l1.process.side_effect = RuntimeError("Primary LLM failed")
    mock_l2 = MagicMock()
    mock_l2.process.side_effect = RuntimeError("Secondary LLM failed")

    fallback = FallbackLLMProcessor([mock_l1, mock_l2])
    result = fallback.process("Texto de teste")
    
    assert result is None, "FallbackLLMProcessor should return None when all models fail"


@pytest.mark.asyncio
async def test_ipc_server_returns_error_json():
    """Verify IPC server returns explicit JSON error payload on unknown actions or failure."""
    srv = AudioScribeServer(None)
    response = await srv._process_command("unknown_action_xyz", {})
    
    assert response.get("status") == "error"
    assert response.get("code") == "unknown_command"
    assert "Unknown command" in response.get("error", "")
