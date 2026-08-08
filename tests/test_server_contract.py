import asyncio
import base64
import hashlib
import hmac
import io
import json
import wave
from types import SimpleNamespace

from core.api.server import AudioScribeServer


def _signed_request(token, request_id, sequence, command, params):
    canonical = json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    material = ":".join(("request", "3", str(sequence), request_id, command, canonical))
    return {
        "protocol_version": 3,
        "id": request_id,
        "sequence": sequence,
        "command": command,
        "params": params,
        "auth": hmac.new(token.encode("utf-8"), material.encode("utf-8"), hashlib.sha256).hexdigest(),
    }


def test_server_exposes_engine_status_contract():
    config = SimpleNamespace(
        transcription=SimpleNamespace(provider="groq", model="groq/whisper-large-v3-turbo", model_chain=["groq/whisper-large-v3-turbo"], base_url=None, api_key=None),
        llm=SimpleNamespace(model="groq/openai/gpt-oss-120b", model_chain=["groq/openai/gpt-oss-120b"]),
    )
    orchestrator = SimpleNamespace(
        config=config,
        audio_input=None,
        is_running=True,
        transcriber=None,
        llm_processor=None,
        output_handler=None,
        usage_store=None,
        add_event_listener=lambda listener: None,
    )
    server = AudioScribeServer(orchestrator=orchestrator)
    status = asyncio.run(server._process_command("get_status", {}))
    assert status["engine_running"] is True
    assert status["transcription_model"] == "groq/whisper-large-v3-turbo"
    assert asyncio.run(server._process_command("get_devices", {}))["code"] == "unknown_command"
    assert asyncio.run(server._process_command("start_recording", {}))["code"] == "unknown_command"


def test_effective_config_keeps_transcription_and_llm_separate():
    config = SimpleNamespace(
        transcription=SimpleNamespace(provider="groq", base_url=None, model="groq/whisper-large-v3-turbo", api_key="trans-key"),
        llm=SimpleNamespace(provider="openrouter", base_url="https://openrouter.ai/api/v1", model="openrouter/openai/gpt-4o-mini", api_key="llm-key"),
    )
    orchestrator = SimpleNamespace(config=config, add_event_listener=lambda listener: None)
    effective = AudioScribeServer(orchestrator=orchestrator)._effective_config()
    assert effective["transcription"]["provider"] == "groq"
    assert effective["llm"]["provider"] == "openrouter"
    assert effective["llm"]["base_url"] == "https://openrouter.ai/api/v1"
    assert effective["transcription"]["api_key_configured"] is True


def test_transcribe_audio_keeps_renderer_wav_bytes_for_transcriber():
    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * 160)

    received_types = []
    orchestrator = SimpleNamespace(
        config=None,
        add_event_listener=lambda listener: None,
        _process_audio=lambda audio_data, profile=None: (received_types.append(type(audio_data)), "ok")[1],
    )
    server = AudioScribeServer(orchestrator=orchestrator)
    result = asyncio.run(server._process_command("transcribe_audio", {
        "audio_base64": base64.b64encode(audio.getvalue()).decode("ascii"),
    }))

    assert result["status"] == "ok"
    assert received_types == [bytes]


def test_transcribe_audio_accepts_renderer_webm_container():
    received = []
    orchestrator = SimpleNamespace(
        config=None,
        add_event_listener=lambda listener: None,
        _process_audio=lambda audio_data, profile=None: (received.append(audio_data[:4]), "ok")[1],
    )
    server = AudioScribeServer(orchestrator=orchestrator)
    webm_payload = b"\x1a\x45\xdf\xa3" + b"\x00" * 200

    result = asyncio.run(server._process_command("transcribe_audio", {
        "audio_base64": base64.b64encode(webm_payload).decode("ascii"),
    }))

    assert result["status"] == "ok"
    assert received == [b"\x1a\x45\xdf\xa3"]


def test_authenticated_ipc_rejects_invalid_and_replayed_messages():
    token = "a" * 48
    server = AudioScribeServer(session_token=token)
    writer = object()
    valid = _signed_request(token, "ping-1", 1, "ping", {})

    assert server._is_authenticated(valid, writer) is True
    assert server._is_authenticated(valid, writer) is False

    invalid = _signed_request(token, "ping-2", 2, "ping", {})
    invalid["auth"] = "0" * 64
    assert server._is_authenticated(invalid, writer) is False


def test_ipc_canonical_json_normalizes_integral_floats_for_javascript():
    server = AudioScribeServer(session_token="a" * 48)

    assert server._canonical_json({"audio_seconds": 0.0, "latency": 1.0, "cost": 0.0001}) == (
        '{"audio_seconds":0,"cost":0.0001,"latency":1}'
    )


def test_outbound_ipc_envelope_signs_the_exact_payload_text():
    token = "a" * 48
    server = AudioScribeServer(session_token=token)

    envelope = server._sign_outbound({"cost": 9.363e-05}, "response")
    material = f"response:3:1:{envelope['payload']}"

    assert envelope["payload"] == '{"cost":9.363e-05}'
    assert envelope["auth"] == hmac.new(token.encode("utf-8"), material.encode("utf-8"), hashlib.sha256).hexdigest()


def test_provider_check_rejects_insecure_custom_endpoint():
    server = AudioScribeServer(session_token="a" * 48)
    result = asyncio.run(server._test_connection({"provider": "openai", "base_url": "http://127.0.0.1:8000"}))

    assert result["status"] == "error"
    assert result["code"] == "unsafe_endpoint"


def test_llm_provider_check_executes_a_minimal_completion_for_selected_model(monkeypatch):
    config = SimpleNamespace(
        transcription=SimpleNamespace(provider="groq", model="groq/whisper-large-v3-turbo", api_key="stt-key"),
        llm=SimpleNamespace(
            provider="groq",
            model="groq/old-model",
            fallback_models=["groq/fallback"],
            api_key="old-key",
            base_url=None,
            enabled=False,
        ),
    )
    server = AudioScribeServer(orchestrator=SimpleNamespace(config=config, add_event_listener=lambda listener: None))
    observed = {}

    class FakeProcessor:
        def health_check(self):
            observed["health_check"] = True

    from core.factory import TranscriptionFactory

    def create_llm(candidate):
        observed["provider"] = candidate.llm.provider
        observed["model"] = candidate.llm.model
        observed["fallback_models"] = candidate.llm.fallback_models
        observed["api_key"] = candidate.llm.api_key
        observed["enabled"] = candidate.llm.enabled
        return FakeProcessor()

    monkeypatch.setattr(TranscriptionFactory, "create_llm_processor", staticmethod(create_llm))

    result = asyncio.run(server._test_connection({
        "type": "llm",
        "provider": "groq",
        "model": "groq/gpt-oss-120b",
        "api_key": "test-key",
    }))

    assert result["status"] == "ok"
    assert result["health"]["capability_verified"] is True
    assert observed == {
        "provider": "groq",
        "model": "groq/gpt-oss-120b",
        "fallback_models": [],
        "api_key": "test-key",
        "enabled": True,
        "health_check": True,
    }


def test_llm_provider_check_rejects_a_model_that_cannot_complete(monkeypatch):
    config = SimpleNamespace(
        transcription=SimpleNamespace(provider="groq", model="groq/whisper-large-v3-turbo", api_key="stt-key"),
        llm=SimpleNamespace(provider="groq", model="groq/gpt-oss-120b", fallback_models=[], api_key="key", base_url=None, enabled=True),
    )
    server = AudioScribeServer(orchestrator=SimpleNamespace(config=config, add_event_listener=lambda listener: None))

    class FailingProcessor:
        def health_check(self):
            raise RuntimeError("Primary model validation failed: invalid API key")

    from core.factory import TranscriptionFactory
    monkeypatch.setattr(TranscriptionFactory, "create_llm_processor", staticmethod(lambda candidate: FailingProcessor()))

    result = asyncio.run(server._test_connection({"type": "llm", "provider": "groq", "model": "groq/gpt-oss-120b", "api_key": "bad"}))

    assert result["status"] == "error"
    assert result["code"] == "llm_validation_failed"
    assert "invalid API key" in result["error"]
