"""
Unit tests for Audio RMS calculation, silence filtering, and latency measurements.
"""

import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from core.implementations.audio.sounddevice_input import calculate_rms
from core.orchestrator import TranscriptionOrchestrator
from core.interfaces.audio_input import AbstractAudioInput
from core.interfaces.transcriber import AbstractTranscriber
from core.interfaces.output_handler import AbstractOutputHandler
from core.interfaces.llm_processor import AbstractLLMProcessor
from core.ui import TerminalUI


@pytest.mark.unit
def test_calculate_rms_empty_and_none():
    assert calculate_rms(None) == 0.0
    assert calculate_rms(b"") == 0.0
    assert calculate_rms(np.array([], dtype=np.float32)) == 0.0


@pytest.mark.unit
def test_calculate_rms_silence_vs_signal():
    silence = np.zeros(1000, dtype=np.float32)
    assert calculate_rms(silence) == 0.0

    # Sine wave signal
    t = np.linspace(0, 1, 1000)
    signal = np.sin(2 * np.pi * 440 * t).astype(np.float32) * 0.5
    rms_val = calculate_rms(signal)
    assert rms_val > 0.1


@pytest.mark.unit
def test_orchestrator_silence_filtering():
    audio_mock = MagicMock()
    audio_mock.config.silence_threshold_rms = 0.05

    transcriber_mock = MagicMock(spec=AbstractTranscriber)
    output_mock = MagicMock(spec=AbstractOutputHandler)
    ui_mock = MagicMock(spec=TerminalUI)

    orchestrator = TranscriptionOrchestrator(
        audio_input=audio_mock,
        transcriber=transcriber_mock,
        output_handler=output_mock,
        ui=ui_mock
    )

    # Silent audio bytes (RMS = 0)
    silent_audio = b"\x00" * 100

    orchestrator._process_audio(silent_audio)

    # Transcriber and output should NOT be called for silent audio
    transcriber_mock.transcribe.assert_not_called()
    output_mock.output.assert_not_called()


@pytest.mark.unit
def test_ui_show_result_with_latency(capsys):
    ui = TerminalUI(verbose=True)
    ui.show_result("Test Output", latency_ms=325.4)

    captured = capsys.readouterr()
    assert "Test Output" in captured.out
    assert "⚡ 325ms" in captured.out
