"""Local JSON-lines IPC server used by the Electron desktop application."""

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.orchestrator import TranscriptionOrchestrator
from core.utils.preflight import PreflightChecker
from core.model_discovery import discover_models, discovery_error

logger = logging.getLogger(__name__)


class AudioScribeServer:
    def __init__(self, orchestrator: Optional[TranscriptionOrchestrator] = None, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.orchestrator = orchestrator
        self.clients = set()
        self.server = None
        self._loop = None
        self._active_profile = None
        self.config = getattr(orchestrator, "config", None) if orchestrator else None
        if orchestrator:
            self.set_orchestrator(orchestrator)

    def set_orchestrator(self, orchestrator: TranscriptionOrchestrator):
        self.orchestrator = orchestrator
        self.config = getattr(orchestrator, "config", None)
        orchestrator.add_event_listener(self._on_orchestrator_event)

    def _on_orchestrator_event(self, event_type: str, data: Dict[str, Any]):
        if not self._loop or self._loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(event_type, data), self._loop)

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        payload = (json.dumps({"event": event_type, "data": data}, ensure_ascii=False) + "\n").encode("utf-8")
        disconnected = set()
        for writer in list(self.clients):
            try:
                writer.write(payload)
                await writer.drain()
            except Exception:
                disconnected.add(writer)
        self.clients -= disconnected

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.clients.add(writer)
        logger.info("Electron client connected to AudioScribe IPC server")
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    message = json.loads(line.decode("utf-8").strip())
                    command = message.get("command")
                    request_id = message.get("id")
                    response = await self._process_command(command, message.get("params") or {})
                    if request_id:
                        response["id"] = request_id
                    writer.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
                    await writer.drain()
                except json.JSONDecodeError:
                    writer.write(b'{"status":"error","error":"Invalid JSON format"}\n')
                    await writer.drain()
        except Exception as exc:
            logger.error("Client handler error: %s", exc)
        finally:
            self.clients.discard(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _process_command(self, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if command == "ping":
            return {
                "status": "ok",
                "message": "AudioScribe engine active",
                "engine_running": bool(self.orchestrator and self.orchestrator.is_running),
            }

        if command == "get_devices":
            try:
                import sounddevice as sd
                devices = sd.query_devices()
                input_devs = [
                    {"index": i, "name": dev.get("name"), "channels": dev.get("max_input_channels"),
                     "default_samplerate": dev.get("default_samplerate")}
                    for i, dev in enumerate(devices)
                    if dev.get("max_input_channels", 0) > 0
                ]
                return {"status": "ok", "devices": input_devs}
            except Exception as exc:
                return {"status": "error", "error": str(exc), "code": "audio_devices_unavailable"}

        if command == "set_device":
            audio = self.orchestrator.audio_input if self.orchestrator else None
            if not audio or not hasattr(audio, "set_device"):
                return {"status": "error", "code": "audio_unavailable", "error": "Entrada de áudio indisponível."}
            try:
                device_index = params.get("device_index")
                audio.set_device(None if device_index in (None, "") else int(device_index))
                return {"status": "ok", "device_index": audio.device_index}
            except (TypeError, ValueError) as exc:
                return {"status": "error", "code": "invalid_device", "error": str(exc)}

        if command == "get_models":
            return await self._get_models()

        if command == "get_usage":
            store = getattr(self.orchestrator, "usage_store", None) if self.orchestrator else None
            if not store:
                empty = {"requests": 0, "cost_known": False, "by_model": []}
                return {"status": "ok", "summary": empty, "periods": {"today": empty, "month": empty}}
            now = datetime.now(timezone.utc)
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
            return {"status": "ok", "summary": store.summary(), "periods": {
                "today": store.summary(day_start),
                "month": store.summary(month_start),
            }}

        if command == "preflight":
            return await self._preflight(deep=bool(params.get("deep")))

        if command == "configure_provider":
            return self._configure_provider(params)

        if command == "start_recording":
            if self.orchestrator and self.orchestrator.audio_input:
                try:
                    if self.orchestrator.audio_input.is_recording:
                        return {"status": "error", "code": "already_recording", "error": "A gravação já está ativa."}
                    self.orchestrator.audio_input.health_check()
                    profile = params.get("profile")
                    self._active_profile = profile if isinstance(profile, dict) else None
                    self.orchestrator.audio_input.start_recording()
                    await self.broadcast("status_changed", {"status": "recording"})
                    return {"status": "ok", "recording": True}
                except Exception as exc:
                    self._active_profile = None
                    return {"status": "error", "code": "audio_not_ready", "error": str(exc), "remediation": "Verifique o microfone e as permissões de áudio em Diagnostics."}
            return {"status": "error", "code": "audio_unavailable", "error": "Entrada de áudio não inicializada."}

        if command == "stop_recording":
            if self.orchestrator and self.orchestrator.audio_input:
                try:
                    if not self.orchestrator.audio_input.is_recording:
                        return {"status": "error", "code": "not_recording", "error": "Nenhuma gravação ativa."}
                    audio_bytes = self.orchestrator.audio_input.stop_recording()
                    await self.broadcast("status_changed", {"status": "processing"})
                    if audio_bytes:
                        self.orchestrator._processing_queue.put((audio_bytes, self._active_profile))
                    profile = self._active_profile
                    self._active_profile = None
                    return {"status": "ok", "recording": False, "profile": profile}
                except Exception as exc:
                    self._active_profile = None
                    return {"status": "error", "code": "audio_stop_failed", "error": str(exc), "remediation": "Verifique o estado do microfone e tente novamente."}
            return {"status": "error", "code": "audio_unavailable", "error": "Entrada de áudio não inicializada."}

        if command == "get_status":
            audio = self.orchestrator.audio_input if self.orchestrator else None
            return {
                "status": "ok",
                "is_recording": bool(audio and audio.is_recording),
                "engine_running": bool(self.orchestrator and self.orchestrator.is_running),
                "provider": self._effective_config().get("provider"),
                "transcription_model": self._effective_config().get("transcription_model"),
                "llm_model": self._effective_config().get("llm_model"),
            }

        return {"status": "error", "code": "unknown_command", "error": f"Unknown command: {command}"}

    async def _preflight(self, deep: bool = False) -> Dict[str, Any]:
        checker = PreflightChecker(config=self.config)
        ready = checker.check_all()
        checks = []
        transcription_config = getattr(self.config, "transcription", None)
        if transcription_config and (
            getattr(transcription_config, "provider", "").lower() == "ollama"
            or "11434" in (getattr(transcription_config, "base_url", None) or "")
        ):
            ready = False
            checks.append({
                "component": "transcription",
                "status": "error",
                "code": "ollama_speech_unsupported",
                "error": "Ollama foi detectado, mas este engine não possui adaptador de speech-to-text para o endpoint de chat.",
                "remediation": "Use Ollama apenas no pós-processamento ou configure um servidor local de Whisper como endpoint de transcrição.",
            })
        if self.orchestrator:
            components = [
                ("transcription", self.orchestrator.transcriber),
                ("llm", self.orchestrator.llm_processor),
                ("output", self.orchestrator.output_handler),
            ]
            for name, component in components:
                if not component:
                    continue
                try:
                    if name == "output" and not component.is_available():
                        raise RuntimeError("output handler indisponível")
                    if deep:
                        health_check = getattr(component, "health_check", None)
                        if callable(health_check):
                            await asyncio.to_thread(health_check)
                        checks.append({"component": name, "status": "ok", "model": getattr(component, "model", None), "verified": True})
                    elif name == "output":
                        checks.append({"component": name, "status": "ok", "verified": True})
                    else:
                        checks.append({
                            "component": name,
                            "status": "ok",
                            "model": getattr(component, "model", None),
                            "verified": False,
                            "message": "Live provider test skipped; use the recording action to verify the selected model.",
                        })
                except Exception as exc:
                    ready = False
                    checks.append({"component": name, "status": "error", "error": str(exc), "model": getattr(component, "model", None)})
        return {"status": "ok", "ready": ready and not checker.errors, "errors": checker.errors, "warnings": checker.warnings, "checks": checks}

    async def _get_models(self) -> Dict[str, Any]:
        config = self.config
        if not config:
            return {"status": "error", "code": "config_unavailable", "error": "Configuração do engine indisponível."}
        def discover_for(section):
            configured = [{"id": model, "name": model, "provider": section.provider, "local": False, "source": "configured"} for model in section.model_chain]
            if not section.base_url:
                return configured, "configured"
            try:
                discovered = discover_models(section.base_url, section.api_key, section.provider)
                # LiteLLM needs the routing prefix even when the provider's
                # /models endpoint returns the vendor-native model id.
                if section.provider in {"groq", "openrouter"}:
                    for item in discovered:
                        model_id = item.get("id")
                        if model_id and not model_id.startswith(f"{section.provider}/"):
                            item["id"] = f"{section.provider}/{model_id}"
                            item["name"] = model_id
                return discovered, "endpoint"
            except Exception as exc:
                return [{"error": discovery_error(exc), "configured": configured}], "error"

        transcription, transcription_source = discover_for(config.transcription)
        llm = []
        llm_source = "disabled"
        if config.llm and config.llm.enabled:
            llm, llm_source = discover_for(config.llm)
        if transcription_source == "error" or llm_source == "error":
            errors = []
            if transcription_source == "error": errors.append(transcription[0]["error"])
            if llm_source == "error": errors.append(llm[0]["error"])
            return {"status": "error", "code": "model_discovery_failed", "errors": errors, "models": [], "llm_models": []}
        is_ollama = config.transcription.provider.lower() == "ollama" or "11434" in (config.transcription.base_url or "")
        return {
            "status": "ok",
            "models": [] if is_ollama else transcription,
            "llm_models": llm,
            "configured": {
                "transcription": [] if is_ollama else config.transcription.model_chain,
                "llm": config.llm.model_chain if config.llm else [],
            },
            "sources": {"transcription": transcription_source, "llm": llm_source},
            "capability_warning": "Ollama models are shown for chat only; the current engine has no Ollama speech-to-text adapter." if is_ollama else None,
        }

    def _configure_provider(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.config or not self.orchestrator:
            return {"status": "error", "code": "config_unavailable", "error": "Configuração do engine indisponível."}
        legacy_provider = (params.get("provider") or self.config.transcription.provider).strip().lower()
        transcription = params.get("transcription") or {}
        llm = params.get("llm") or {}
        trans_provider = (transcription.get("provider") or legacy_provider).strip().lower()
        trans_base_url = transcription.get("base_url") if "base_url" in transcription else params.get("base_url")
        trans_api_key = transcription.get("api_key") if "api_key" in transcription else params.get("api_key")
        trans_model = transcription.get("model") or params.get("transcription_model") or self.config.transcription.model
        self.config.transcription.provider = trans_provider
        self.config.transcription.base_url = trans_base_url or None
        self.config.transcription.api_key = trans_api_key or None
        self.config.transcription.model = trans_model
        if self.config.llm:
            self.config.llm.provider = (llm.get("provider") or params.get("llm_provider") or legacy_provider).strip().lower()
            self.config.llm.base_url = (llm.get("base_url") if "base_url" in llm else params.get("llm_base_url")) or None
            self.config.llm.api_key = (llm.get("api_key") if "api_key" in llm else trans_api_key) or None
            llm_model = llm.get("model") or params.get("llm_model") or self.config.llm.model
            if llm_model:
                self.config.llm.model = llm_model
        from core.factory import TranscriptionFactory
        self.orchestrator.transcriber = TranscriptionFactory.create_transcriber(self.config)
        self.orchestrator.llm_processor = (
            TranscriptionFactory.create_llm_processor(self.config) if self.config.llm and self.config.llm.enabled else None
        )
        return {"status": "ok", "config": self._effective_config()}

    def _effective_config(self) -> Dict[str, Any]:
        config = self.config
        if not config:
            return {}
        return {
            "transcription": {"provider": config.transcription.provider, "base_url": config.transcription.base_url, "model": config.transcription.model, "api_key_configured": bool(getattr(config.transcription, "api_key", None))},
            "llm": {"provider": getattr(config.llm, "provider", None), "base_url": getattr(config.llm, "base_url", None), "model": config.llm.model, "api_key_configured": bool(getattr(config.llm, "api_key", None))} if config.llm else None,
            "provider": config.transcription.provider,
            "base_url": config.transcription.base_url,
            "transcription_model": config.transcription.model,
            "llm_model": config.llm.model if config.llm else None,
            "api_key_configured": bool(
                getattr(config.transcription, "api_key", None)
                or (getattr(config.llm, "api_key", None) if config.llm else None)
            ),
        }

    async def start(self):
        self._loop = asyncio.get_running_loop()
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logger.info("AudioScribe IPC server running on %s:%s", self.host, self.port)
        async with self.server:
            await self.server.serve_forever()

    def run_in_thread(self):
        def _thread_target():
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.start())

        thread = threading.Thread(target=_thread_target, daemon=True, name="audioscribe-ipc")
        thread.start()
        return thread
