"""Integration tests: empty/silent audio must never result in 'Pasted!' overlay."""
import io
import pytest
import queue
import numpy as np
import soundfile as sf


class FakeOutput:
    def output(self, text):
        pass


class FakeAudioStoppedMic:
    is_recording = False

    def start_recording(self):
        self.is_recording = True

    def stop_recording(self):
        self.is_recording = False
        return b""


class FakeTranscriber:
    def transcribe(self, audio):
        return "Fake transcription"


class FakeLLM:
    def process(self, text, profile=None):
        return text


def _make_wav(samples, sr=16000):
    buf = io.BytesIO()
    sf.write(buf, samples, sr, format="WAV")
    return buf.getvalue()


def test_empty_audio_emits_error_not_transcription_result():
    """Empty audio must emit error+ready, NOT transcription_result."""
    from core.orchestrator import TranscriptionOrchestrator

    orch = TranscriptionOrchestrator(
        audio_input=FakeAudioStoppedMic(),
        transcriber=FakeTranscriber(),
        output_handler=FakeOutput(),
        llm_processor=FakeLLM(),
    )

    events = []
    orch._emit_event = lambda etype, data: events.append((etype, data))

    orch._process_audio(b"", profile=None)

    event_types = [e[0] for e in events]
    assert "error" in event_types, f"Expected 'error', got {event_types}"
    assert "status_changed" in event_types, f"Expected 'status_changed', got {event_types}"
    assert "transcription_result" not in event_types, (
        f"Empty audio must NOT emit transcription_result. Got {event_types}"
    )


def test_silent_audio_below_rms_emits_error_not_transcription_result():
    """RMS < threshold must emit error+ready, NOT transcription_result."""
    from core.orchestrator import TranscriptionOrchestrator

    silent = np.zeros(16000, dtype=np.float32)
    wav = _make_wav(silent)

    orch = TranscriptionOrchestrator(
        audio_input=FakeAudioStoppedMic(),
        transcriber=FakeTranscriber(),
        output_handler=FakeOutput(),
        llm_processor=FakeLLM(),
    )

    events = []
    orch._emit_event = lambda etype, data: events.append((etype, data))

    orch._process_audio(wav, profile=None)

    event_types = [e[0] for e in events]
    assert "error" in event_types, f"Expected 'error', got {event_types}"
    assert "status_changed" in event_types, f"Expected 'status_changed', got {event_types}"
    assert "transcription_result" not in event_types, (
        f"Silent audio must NOT emit transcription_result. Got {event_types}"
    )


def test_normal_audio_still_emits_transcription_result():
    """Regression: loud audio with text must still emit transcription_result."""
    from core.orchestrator import TranscriptionOrchestrator

    loud = np.random.randn(16000).astype(np.float32) * 0.5
    wav = _make_wav(loud)

    orch = TranscriptionOrchestrator(
        audio_input=FakeAudioStoppedMic(),
        transcriber=FakeTranscriber(),
        output_handler=FakeOutput(),
        llm_processor=FakeLLM(),
    )

    events = []
    orch._emit_event = lambda etype, data: events.append((etype, data))

    orch._process_audio(wav, profile=None)

    event_types = [e[0] for e in events]
    assert "transcription_result" in event_types, (
        f"Normal audio must emit transcription_result. Got {event_types}"
    )


def test_start_recording_drains_stale_queue():
    """start_recording drains stale entries from processing queue."""
    from core.orchestrator import TranscriptionOrchestrator

    orch = TranscriptionOrchestrator(
        audio_input=FakeAudioStoppedMic(),
        transcriber=FakeTranscriber(),
        output_handler=FakeOutput(),
        llm_processor=FakeLLM(),
    )

    orch._processing_queue.put((b"stale_audio", None))
    orch._processing_queue.put((b"stale_audio_2", None))

    orch._on_hotkey_press()

    assert orch._processing_queue.empty(), (
        "Queue must be empty after start_recording drains stale entries"
    )
