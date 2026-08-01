"""
Unit tests for Orchestrator and Factory.
"""

import pytest
from unittest.mock import MagicMock
from core.orchestrator import TranscriptionOrchestrator
from core.interfaces.audio_input import AbstractAudioInput
from core.interfaces.transcriber import AbstractTranscriber
from core.interfaces.output_handler import AbstractOutputHandler
from core.interfaces.llm_processor import AbstractLLMProcessor


@pytest.mark.unit
def test_orchestrator_initialization():
    audio_mock = MagicMock(spec=AbstractAudioInput)
    transcriber_mock = MagicMock(spec=AbstractTranscriber)
    output_mock = MagicMock(spec=AbstractOutputHandler)
    llm_mock = MagicMock(spec=AbstractLLMProcessor)

    orchestrator = TranscriptionOrchestrator(
        audio_input=audio_mock,
        transcriber=transcriber_mock,
        output_handler=output_mock,
        llm_processor=llm_mock
    )

    assert orchestrator.is_running is False
    assert orchestrator.audio_input == audio_mock
    assert orchestrator.transcriber == transcriber_mock
    assert orchestrator.output_handler == output_mock


@pytest.mark.unit
def test_orchestrator_transcribe_text():
    audio_mock = MagicMock(spec=AbstractAudioInput)
    transcriber_mock = MagicMock(spec=AbstractTranscriber)
    output_mock = MagicMock(spec=AbstractOutputHandler)
    llm_mock = MagicMock(spec=AbstractLLMProcessor)
    llm_mock.process.return_value = "Enhanced text"

    orchestrator = TranscriptionOrchestrator(
        audio_input=audio_mock,
        transcriber=transcriber_mock,
        output_handler=output_mock,
        llm_processor=llm_mock
    )

    orchestrator.transcribe_text("Raw text")

    llm_mock.process.assert_called_once_with("Raw text")
    output_mock.output.assert_called_once_with("Enhanced text")
