import asyncio
from types import SimpleNamespace

from core.api.server import AudioScribeServer


class FakeAudio:
    is_recording = False
    device_index = None

    def set_device(self, index):
        self.device_index = index


def test_server_exposes_status_and_device_contract():
    config = SimpleNamespace(
        transcription=SimpleNamespace(provider="groq", model="groq/whisper-large-v3-turbo", model_chain=["groq/whisper-large-v3-turbo"], base_url=None, api_key=None),
        llm=SimpleNamespace(model="groq/openai/gpt-oss-120b", model_chain=["groq/openai/gpt-oss-120b"]),
    )
    orchestrator = SimpleNamespace(
        config=config,
        audio_input=FakeAudio(),
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

    result = asyncio.run(server._process_command("set_device", {"device_index": "3"}))
    assert result == {"status": "ok", "device_index": 3}
    assert orchestrator.audio_input.device_index == 3


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
