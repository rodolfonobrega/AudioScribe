"""
Unit tests for LiteLLMTranscriber.
"""

import pytest
from unittest.mock import patch, MagicMock
from core.implementations.transcription.litellm_transcriber import LiteLLMTranscriber
from config.settings import TranscriptionConfig


@pytest.mark.unit
def test_litellm_transcriber_init():
    config = TranscriptionConfig(
        model="openai/whisper-1",
        api_key="sk-testkey123"
    )
    transcriber = LiteLLMTranscriber(config)
    assert transcriber.model == "openai/whisper-1"
    assert transcriber.active_model == "openai/whisper-1"
    assert transcriber.api_key == "sk-testkey123"


@pytest.mark.unit
def test_litellm_transcriber_base_url():
    config = TranscriptionConfig(
        model="openai/whisper-local",
        api_key="not-needed",
        base_url="http://localhost:11434/v1"
    )
    transcriber = LiteLLMTranscriber(config)
    assert transcriber.base_url == "http://localhost:11434/v1"


@pytest.mark.unit
def test_litellm_transcriber_mock_transcribe():
    config = TranscriptionConfig(
        model="groq/whisper-large-v3-turbo",
        api_key="gsk_test123"
    )
    transcriber = LiteLLMTranscriber(config)

    with patch.object(transcriber, 'litellm') as mock_litellm, \
         patch("builtins.open", MagicMock()):
        mock_response = MagicMock()
        mock_response.text = "Hello world transcription"
        mock_litellm.transcription.return_value = mock_response

        res = transcriber._try_transcribe("groq/whisper-large-v3-turbo", "dummy.wav")
        assert res == "Hello world transcription"
