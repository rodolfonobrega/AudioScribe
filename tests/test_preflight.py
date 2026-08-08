"""
Unit tests for PreflightChecker.
"""

import pytest
import os
from unittest.mock import patch, MagicMock
from core.utils.preflight import PreflightChecker
from config.settings import Config, AudioConfig, OutputConfig, TranscriptionConfig


@pytest.mark.unit
def test_preflight_checker_init():
    checker = PreflightChecker()
    assert checker.system in ["Windows", "Darwin", "Linux"]
    assert len(checker.errors) == 0
    assert len(checker.warnings) == 0


@pytest.mark.unit
def test_preflight_api_keys_missing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)

    config = Config()
    config.transcription.provider = "litellm"
    config.transcription.api_key = None
    if config.llm:
        config.llm.api_key = None

    checker = PreflightChecker(config=config)
    checker.check_api_keys()
    assert len(checker.errors) > 0
    assert any("API Keys" in e["component"] for e in checker.errors)


@pytest.mark.unit
def test_preflight_local_provider_does_not_require_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    config = Config()
    config.transcription.provider = "local_whisper"
    config.llm.enabled = False
    checker = PreflightChecker(config=config)
    checker.check_api_keys()
    assert checker.errors == []


@pytest.mark.unit
def test_preflight_api_keys_present(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test123456789")

    config = Config()
    config.transcription.api_key = "gsk_test123456789"

    checker = PreflightChecker(config=config)
    checker.check_api_keys()
    assert len(checker.errors) == 0


@pytest.mark.unit
def test_preflight_output_handler_invalid_os():
    config = Config()
    config.output.handlers = ["applescript"]

    checker = PreflightChecker(config=config)
    if checker.system != "Darwin":
        checker.check_output_handlers()
        assert len(checker.errors) > 0
        assert any("AppleScript" in e["component"] for e in checker.errors)
