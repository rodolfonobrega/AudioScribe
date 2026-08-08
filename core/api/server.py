"""Local JSON-lines IPC server used by the Electron desktop application."""

import asyncio
import copy
import hmac
import json
import logging
import math
import os
import platform
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.orchestrator import TranscriptionOrchestrator
from core.usage import is_wav_audio
from core.utils.preflight import PreflightChecker
from core.model_discovery import discover_models, discovery_error

logger = logging.getLogger(__name__)


class AudioScribeServer:
    """Authenticated, per-launch local IPC server for the desktop shell."""

    PROTOCOL_VERSION = 3
    # Renderer audio is still transported as a bounded WebM/WAV payload while
    # the capture adapter is being migrated to file streaming. Keep a strict
    # ceiling well below the previous 100 MB unbounded IPC allowance.
    _STREAM_LIMIT = 32 * 1024 * 1024

    def __init__(
        self,
        orchestrator: Optional[TranscriptionOrchestrator] = None,
        host: str = "127.0.0.1",
        port: int = 0,
        session_token: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.bound_port: Optional[int] = None
        self._session_token = (session_token or "").encode("utf-8")
        self.orchestrator = orchestrator
        self.clients = set()
        self._client_sequences: Dict[Any, int] = {}
        self._outbound_sequence = 0
        self.server = None
        self._loop = None
        self._ready_event = threading.Event()
        self._config_lock = threading.RLock()
        self._download_jobs = {}
        self._downloads_by_model = {}
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

    def _canonical_json(self, value: Any) -> str:
        """Serialize a payload identically after Python and JavaScript parse it.

        JSON has one numeric type whereas Python preserves ``0.0`` and
        JavaScript serializes that value as ``0``. Normalizing integral floats
        before signing avoids an HMAC mismatch on responses such as usage
        summaries after Electron parses the JSON.
        """
        def normalize(item: Any) -> Any:
            if isinstance(item, float):
                if not math.isfinite(item):
                    raise ValueError("IPC payload contains a non-finite number")
                return int(item) if item.is_integer() else item
            if isinstance(item, dict):
                return {key: normalize(nested) for key, nested in item.items()}
            if isinstance(item, (list, tuple)):
                return [normalize(nested) for nested in item]
            return item

        return json.dumps(normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def _request_signature(self, message: Dict[str, Any]) -> str:
        material = ":".join(
            (
                "request",
                str(message.get("protocol_version")),
                str(message.get("sequence")),
                str(message.get("id") or ""),
                str(message.get("command") or ""),
                self._canonical_json(message.get("params") or {}),
            )
        )
        return hmac.new(self._session_token, material.encode("utf-8"), "sha256").hexdigest()

    def _sign_outbound(self, payload: Dict[str, Any], direction: str) -> Dict[str, Any]:
        self._outbound_sequence += 1
        # Preserve the exact serialized payload inside the envelope. Python
        # may emit 9.363e-05 while JavaScript re-renders the parsed value as
        # 0.00009363; signing the preserved text avoids false HMAC failures.
        payload_json = self._canonical_json(payload)
        signed = {
            "protocol_version": self.PROTOCOL_VERSION,
            "sequence": self._outbound_sequence,
            "payload": payload_json,
        }
        material = f"{direction}:{signed['protocol_version']}:{signed['sequence']}:{payload_json}"
        signed["auth"] = hmac.new(self._session_token, material.encode("utf-8"), "sha256").hexdigest()
        return signed

    def _is_authenticated(self, message: Dict[str, Any], writer: Any) -> bool:
        if not self._session_token or message.get("protocol_version") != self.PROTOCOL_VERSION:
            return False
        sequence = message.get("sequence")
        if not isinstance(sequence, int) or sequence <= self._client_sequences.get(writer, 0):
            return False
        provided = message.get("auth")
        if not isinstance(provided, str) or not hmac.compare_digest(provided, self._request_signature(message)):
            return False
        self._client_sequences[writer] = sequence
        return True

    async def _write_message(self, writer: Any, payload: Dict[str, Any], direction: str = "response"):
        writer.write((self._canonical_json(self._sign_outbound(payload, direction)) + "\n").encode("utf-8"))
        await writer.drain()

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        disconnected = set()
        for writer in list(self.clients):
            try:
                await self._write_message(writer, {"event": event_type, "data": data}, "event")
            except Exception:
                disconnected.add(writer)
        self.clients -= disconnected
        for writer in disconnected:
            self._client_sequences.pop(writer, None)

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        authenticated = False
        try:
            while True:
                try:
                    line = await reader.readuntil(b'\n')
                except asyncio.IncompleteReadError:
                    # Client shutdown is expected during app exit.
                    break
                except asyncio.LimitOverrunError as exc:
                    logger.warning("Incoming IPC message exceeds limit (%d bytes)", exc.consumed)
                    await reader.read(exc.consumed)
                    if authenticated:
                        await self._write_message(writer, {"status": "error", "code": "message_too_large", "error": "IPC message exceeds 32 MB."})
                    continue
                if not line:
                    break
                try:
                    message = json.loads(line.decode("utf-8").strip())
                except (UnicodeDecodeError, json.JSONDecodeError):
                    if authenticated:
                        await self._write_message(writer, {"status": "error", "code": "invalid_json", "error": "Invalid JSON payload."})
                    continue

                if not self._is_authenticated(message, writer):
                    logger.warning("Rejected unauthenticated local IPC request")
                    break
                if not authenticated:
                    authenticated = True
                    self.clients.add(writer)
                    logger.info("Authenticated Electron client connected to AudioScribe IPC server")

                try:
                    command = message.get("command")
                    request_id = message.get("id")
                    response = await self._process_command(command, message.get("params") or {})
                    if request_id:
                        response["id"] = request_id
                    await self._write_message(writer, response)
                except Exception:
                    logger.exception("IPC command failed")
                    await self._write_message(writer, {"status": "error", "code": "command_failed", "error": "The engine could not complete this command."})
        except Exception as exc:
            logger.warning("IPC client handler stopped: %s", exc)
        finally:
            self.clients.discard(writer)
            self._client_sequences.pop(writer, None)
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

        if command == "get_models":
            return await self._get_models()

        if command == "get_local_models":
            from core.local_models import gpu_capabilities, list_local_models
            models, gpu = await asyncio.gather(
                asyncio.to_thread(list_local_models),
                asyncio.to_thread(gpu_capabilities),
            )
            return {
                "status": "ok",
                "models": [
                    {
                        **model,
                        "download_active": model["id"] in self._downloads_by_model,
                        "download_job_id": self._downloads_by_model.get(model["id"]),
                    }
                    for model in models
                ],
                "gpu": gpu,
                "runtime": self._runtime_info(gpu),
            }

        if command == "download_local_model":
            from core.local_models import LOCAL_MODELS, local_model_status
            model_id = params.get("model")
            if model_id not in LOCAL_MODELS:
                return {"status": "error", "code": "unknown_model", "id": model_id}
            existing_job = self._downloads_by_model.get(model_id)
            if existing_job:
                return {"status": "started", "job_id": existing_job, "model": model_id, "already_running": True}
            if not self._loop or self._loop.is_closed():
                return {"status": "error", "code": "engine_loop_unavailable", "error": "Download service is not ready."}
            job_id = uuid.uuid4().hex
            cancel_event = threading.Event()
            self._download_jobs[job_id] = {"id": job_id, "model": model_id, "cancel_event": cancel_event}
            self._downloads_by_model[model_id] = job_id
            task = asyncio.create_task(self._run_download_job(job_id, model_id, cancel_event))
            self._download_jobs[job_id]["task"] = task
            status = await asyncio.to_thread(local_model_status, model_id)
            return {
                "status": "started", "job_id": job_id, "model": model_id,
                "resumed": bool(status.get("resumable")),
            }

        if command == "cancel_local_model":
            job_id = params.get("job_id") or self._downloads_by_model.get(params.get("model"))
            job = self._download_jobs.get(job_id)
            if not job:
                return {"status": "error", "code": "download_not_active", "job_id": job_id}
            job["cancel_event"].set()
            return {"status": "ok", "state": "cancelling", "job_id": job_id, "model": job["model"]}

        if command == "delete_local_model":
            from core.model_downloader import delete_model
            model_id = params.get("model")
            if model_id in self._downloads_by_model:
                return {"status": "error", "code": "download_active", "error": "Cancel the active download before removing this model."}
            return await asyncio.to_thread(delete_model, model_id)

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

        if command == "get_history":
            return {"status": "ok", "items": self._store().list_transcriptions(
                params.get("limit", 50), params.get("offset", 0)
            )}

        if command == "delete_history":
            return {"status": "ok", "deleted": self._store().delete_transcription(params.get("id"))}

        if command == "clear_history":
            return {"status": "ok", "deleted": self._store().clear_transcriptions()}

        if command == "get_dictionary":
            return {"status": "ok", "items": self._store().list_dictionary()}

        if command == "update_dictionary":
            store = self._store()
            added = store.add_dictionary_words(params.get("add", []), params.get("source", "manual"))
            removed = store.remove_dictionary_words(params.get("remove", []))
            return {"status": "ok", "added": added, "removed": removed, "items": store.list_dictionary()}

        if command == "get_snippets":
            return {"status": "ok", "items": self._store().list_snippets()}

        if command == "save_snippet":
            store = self._store()
            item = store.upsert_snippet(
                params.get("trigger", ""), params.get("replacement", ""),
                enabled=params.get("enabled", True), snippet_id=params.get("id")
            )
            return {"status": "ok", "item": item, "items": store.list_snippets()}

        if command == "delete_snippet":
            return {"status": "ok", "deleted": self._store().delete_snippet(params.get("id"))}

        if command == "preflight":
            return await self._preflight(deep=bool(params.get("deep")))

        if command == "configure_provider":
            return self._configure_provider(params)

        if command == "test_connection":
            return await self._test_connection(params)

        if command == "transcribe_audio":
            audio_b64 = params.get("audio_base64")
            profile = params.get("profile")
            if not audio_b64:
                return {"status": "error", "error": "audio_base64 parameter required"}
            try:
                import base64, io, wave
                audio_bytes = base64.b64decode(audio_b64)
                is_webm = audio_bytes[:4] == b"\x1a\x45\xdf\xa3"
                is_ogg = audio_bytes.startswith(b"OggS")
                if is_wav_audio(audio_bytes):
                    with wave.open(io.BytesIO(audio_bytes), 'rb') as wf:
                        if wf.getnframes() <= 0 or wf.getframerate() <= 0:
                            return {"status": "error", "code": "empty_audio", "error": "The audio payload contains no samples."}
                elif not (is_webm or is_ogg):
                    return {"status": "error", "code": "unsupported_audio", "error": "Unsupported audio container. Use WebM/Opus, Ogg/Opus, or WAV."}

                if self.orchestrator:
                    await self.broadcast("status_changed", {"status": "processing"})
                    result_text = await asyncio.to_thread(self.orchestrator._process_audio, audio_bytes, profile=profile)
                    if result_text is None:
                        return {
                            "status": "error",
                            "code": "transcription_failed",
                            "error": "O processamento do áudio falhou. Consulte o diagnóstico do engine.",
                        }
                    return {
                        "status": "ok",
                        "text": result_text or "",
                        "is_silent": not bool(result_text),
                    }
                return {"status": "error", "error": "Orchestrator unavailable"}
            except Exception as exc:
                return {"status": "error", "error": str(exc)}

        if command == "get_status":
            return {
                "status": "ok",
                "engine_running": bool(self.orchestrator and self.orchestrator.is_running),
                "provider": self._effective_config().get("provider"),
                "transcription_model": self._effective_config().get("transcription_model"),
                "llm_model": self._effective_config().get("llm_model"),
            }

        return {"status": "error", "code": "unknown_command", "error": f"Unknown command: {command}"}

    async def _run_download_job(self, job_id: str, model_id: str, cancel_event: threading.Event):
        from core.model_downloader import download_model

        def progress(downloaded: int, total: int, **metadata):
            if not self._loop or self._loop.is_closed():
                return
            payload = {
                "job_id": job_id,
                "model": model_id,
                "downloaded": downloaded,
                "total": total,
                "percent": min(99, int(downloaded * 100 / total)) if total else 0,
                "status": "resuming" if metadata.get("resumed") else "downloading",
            }
            if metadata.get("file"):
                payload["file"] = metadata["file"]
            asyncio.run_coroutine_threadsafe(self.broadcast("download_progress", payload), self._loop)

        try:
            result = await asyncio.to_thread(download_model, model_id, progress, cancel_event)
            if result.get("status") == "ok":
                await self.broadcast("download_complete", {"job_id": job_id, "model": model_id, **result})
            elif result.get("status") == "cancelled":
                await self.broadcast("download_cancelled", {"job_id": job_id, "model": model_id, **result})
            else:
                await self.broadcast("download_error", {"job_id": job_id, "model": model_id, **result})
        except Exception as exc:
            logger.exception("Local model download job failed: %s", model_id)
            await self.broadcast("download_error", {
                "job_id": job_id, "model": model_id, "status": "error",
                "code": "download_failed", "error": str(exc),
            })
        finally:
            self._download_jobs.pop(job_id, None)
            if self._downloads_by_model.get(model_id) == job_id:
                self._downloads_by_model.pop(model_id, None)

    def _store(self):
        if not self.orchestrator or not getattr(self.orchestrator, "local_store", None):
            raise RuntimeError("Local store is unavailable")
        return self.orchestrator.local_store

    def _runtime_info(self, gpu=None) -> Dict[str, Any]:
        """Describe the active local/cloud execution path for the desktop UI."""
        gpu = gpu or {}
        config = self.config
        trans_config = getattr(config, "transcription", None)
        llm_config = getattr(config, "llm", None)
        transcriber = getattr(self.orchestrator, "transcriber", None)
        llm = getattr(self.orchestrator, "llm_processor", None)
        trans_backend = transcriber.__class__.__name__ if transcriber else None
        trans_device = getattr(transcriber, "device", None) or getattr(trans_config, "device", "auto")
        trans_provider = getattr(trans_config, "provider", None) or getattr(transcriber, "provider", None)
        configured_local = str(trans_provider or "").lower() in {"local_whisper", "whisper", "whisper_local", "parakeet", "local_parakeet"}
        trans_is_local = configured_local and (not trans_backend or trans_backend in {"LocalWhisperTranscriber", "ParakeetTranscriber"})
        trans_execution = "local" if trans_is_local else "cloud"
        if trans_execution == "local" and trans_device == "auto":
            trans_device = gpu.get("device") or "cpu"

        return {
            "platform": platform.system(),
            "cpu_count": os.cpu_count() or 1,
            "gpu": gpu,
            "transcription": {
                "provider": trans_provider or "unknown",
                "model": getattr(transcriber, "model", None) or getattr(trans_config, "model", None),
                "execution": trans_execution,
                "device": trans_device or ("remote" if trans_execution == "cloud" else "cpu"),
                "compute_type": getattr(transcriber, "compute_type", None) or getattr(trans_config, "compute_type", None),
                "backend": trans_backend,
            },
            "post_processing": {
                "enabled": bool(llm_config and getattr(llm_config, "enabled", False) and llm),
                "provider": getattr(llm_config, "provider", None) if llm_config else None,
                "model": getattr(llm, "model", None) or getattr(llm_config, "model", None) if llm else getattr(llm_config, "model", None) if llm_config else None,
                "execution": "cloud" if llm else "disabled",
            },
        }

    async def _preflight(self, deep: bool = False) -> Dict[str, Any]:
        checker = PreflightChecker(config=self.config)
        ready = checker.check_desktop_engine()
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

    async def _test_connection(self, params: Dict[str, Any]) -> Dict[str, Any]:
        provider = (params.get("provider") or "").strip().lower()
        api_key = (params.get("api_key") or "").strip()
        base_url = (params.get("base_url") or "").strip()
        kind = (params.get("type") or "transcription").strip().lower()

        if api_key == "configured":
            if kind == "llm" and self.config and self.config.llm:
                api_key = getattr(self.config.llm, "api_key", None) or ""
            elif self.config and self.config.transcription:
                api_key = getattr(self.config.transcription, "api_key", None) or ""

        # A model-list endpoint proves only that the provider is reachable. A
        # profile, however, needs a real completion after the audio is already
        # gone. Validate that exact path up front with the smallest possible
        # request so an invalid key, model, or completion capability cannot
        # turn into a lost dictation.
        if kind == "llm":
            try:
                candidate = copy.deepcopy(self.config)
                if not candidate or not candidate.llm:
                    raise RuntimeError("LLM configuration is unavailable")
                candidate.llm.provider = provider or candidate.llm.provider
                candidate.llm.api_key = api_key or None
                candidate.llm.base_url = base_url or None
                if params.get("model"):
                    candidate.llm.model = params["model"]
                    candidate.llm.fallback_models = []
                candidate.llm.enabled = True
                from core.factory import TranscriptionFactory
                processor = await asyncio.to_thread(TranscriptionFactory.create_llm_processor, candidate)
                await asyncio.to_thread(processor.health_check)
                return {
                    "status": "ok",
                    "health": {
                        "configured": True,
                        "reachable": True,
                        "authenticated": bool(api_key),
                        "model_available": True,
                        "capability_verified": True,
                    },
                    "message": "The selected post-processing model completed a validation request.",
                }
            except Exception as exc:
                return {
                    "status": "error",
                    "code": "llm_validation_failed",
                    "error": str(exc),
                    "health": {
                        "configured": True,
                        "reachable": False,
                        "authenticated": False,
                        "model_available": False,
                        "capability_verified": False,
                    },
                }

        if provider in {"local_whisper", "parakeet"}:
            try:
                candidate = copy.deepcopy(self.config)
                if not candidate:
                    raise RuntimeError("Engine configuration is unavailable")
                candidate.transcription.provider = provider
                candidate.transcription.model = params.get("model") or candidate.transcription.model
                from core.factory import TranscriptionFactory
                transcriber = await asyncio.to_thread(TranscriptionFactory.create_transcriber, candidate)
                await asyncio.to_thread(transcriber.health_check)
                return {
                    "status": "ok",
                    "latency_ms": 0,
                    "health": {"configured": True, "reachable": True, "authenticated": True, "model_available": True, "capability_verified": True},
                    "message": "Local transcription runtime and selected model are ready.",
                }
            except Exception as exc:
                return {
                    "status": "error",
                    "code": "local_runtime_unavailable",
                    "error": str(exc),
                    "health": {"configured": True, "reachable": False, "authenticated": True, "model_available": False, "capability_verified": False},
                }

        if provider == "ollama":
            url = base_url or "http://localhost:11434"
            target_url = f"{url.rstrip('/')}/api/tags"
        elif base_url:
            target_url = f"{base_url.rstrip('/')}/models"
        elif provider == "groq":
            target_url = "https://api.groq.com/openai/v1/models"
        elif provider == "mistral":
            target_url = "https://api.mistral.ai/v1/models"
        elif provider == "openrouter":
            target_url = "https://openrouter.ai/api/v1/models"
        elif provider == "anthropic":
            target_url = "https://api.anthropic.com/v1/models"
        elif provider == "gemini":
            target_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}" if api_key else "https://generativelanguage.googleapis.com/v1beta/models"
        elif provider == "xai":
            target_url = "https://api.x.ai/v1/models"
        else:
            target_url = "https://api.openai.com/v1/models"

        from urllib.parse import urlparse
        import ipaddress
        import socket
        import time
        import urllib.error
        import urllib.request

        parsed = urlparse(target_url)
        allow_local = provider == "ollama" or bool(params.get("allow_local"))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return {"status": "error", "code": "unsafe_endpoint", "error": "Provider URL must be an HTTP(S) URL with a host."}
        if parsed.scheme != "https" and not allow_local:
            return {"status": "error", "code": "unsafe_endpoint", "error": "Custom cloud provider URLs must use HTTPS."}
        try:
            for address in {item[4][0] for item in socket.getaddrinfo(parsed.hostname, None)}:
                ip = ipaddress.ip_address(address)
                if (ip.is_private or ip.is_link_local or ip.is_loopback or ip.is_multicast or ip.is_reserved) and not (allow_local and ip.is_loopback):
                    return {"status": "error", "code": "unsafe_endpoint", "error": "The provider endpoint resolves to a blocked network address."}
        except socket.gaierror:
            return {"status": "error", "code": "connection_failed", "error": "Provider host could not be resolved."}

        req = urllib.request.Request(target_url, headers={"User-Agent": "AudioScribe/1.0"})
        if api_key and provider != "gemini":
            if provider == "anthropic":
                req.add_header("x-api-key", api_key)
                req.add_header("anthropic-version", "2023-06-01")
            else:
                req.add_header("Authorization", f"Bearer {api_key}")

        start_t = time.monotonic()
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, fp, code, msg, headers, newurl):
                return None

        def _do_req():
            try:
                with urllib.request.build_opener(_NoRedirect).open(req, timeout=5) as resp:
                    return {"status": "ok", "code": resp.status}
            except urllib.error.HTTPError as exc:
                code = "authentication_failed" if exc.code in (401, 403) else "endpoint_or_model_not_found" if exc.code == 404 else "provider_rejected_request" if exc.code == 400 else "connection_failed"
                return {"status": "error", "code": code, "error": f"Provider returned HTTP {exc.code}: {exc.reason}", "http_code": exc.code}
            except Exception as exc:
                return {"status": "error", "code": "connection_failed", "error": f"Connection failed: {str(exc)}"}

        res = await asyncio.to_thread(_do_req)
        elapsed_ms = int((time.monotonic() - start_t) * 1000)
        if res.get("status") == "ok":
            return {
                "status": "ok",
                "latency_ms": elapsed_ms,
                "health": {"configured": True, "reachable": True, "authenticated": bool(api_key), "model_available": True, "capability_verified": True},
                "message": f"Connection verified in {elapsed_ms}ms.",
            }
        return {
            "status": "error",
            "error": res.get("error", "Connection failed."),
            "code": res.get("code", "connection_failed"),
            "http_code": res.get("http_code"),
            "health": {"configured": True, "reachable": res.get("code") not in {"connection_failed", "unsafe_endpoint"}, "authenticated": False, "model_available": False, "capability_verified": False},
        }

    def _configure_provider(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.config or not self.orchestrator:
            return {"status": "error", "code": "config_unavailable", "error": "Configuração do engine indisponível."}
        if getattr(self.orchestrator, "is_recording", False):
            return {"status": "error", "code": "recording_active", "error": "Stop the active recording before changing providers."}
        legacy_provider = (params.get("provider") or self.config.transcription.provider).strip().lower()
        transcription = params.get("transcription") or {}
        llm = params.get("llm") or {}
        trans_provider = (transcription.get("provider") or legacy_provider).strip().lower()
        trans_base_url = transcription.get("base_url") if "base_url" in transcription else params.get("base_url")
        trans_api_key = transcription.get("api_key") if "api_key" in transcription else params.get("api_key")
        trans_model = transcription.get("model") or params.get("transcription_model") or self.config.transcription.model
        trans_model_path = transcription.get("model_path") if "model_path" in transcription else params.get("model_path")
        trans_device = transcription.get("device") if "device" in transcription else params.get("device")
        trans_compute_type = transcription.get("compute_type") if "compute_type" in transcription else params.get("compute_type")
        candidate = copy.deepcopy(self.config)
        candidate.transcription.provider = trans_provider
        candidate.transcription.base_url = trans_base_url or None
        candidate.transcription.api_key = trans_api_key or None
        candidate.transcription.model = trans_model
        if trans_model_path is not None:
            candidate.transcription.model_path = trans_model_path or None
        if trans_device:
            candidate.transcription.device = trans_device
        if trans_compute_type:
            candidate.transcription.compute_type = trans_compute_type
        if candidate.llm:
            candidate.llm.provider = (llm.get("provider") or params.get("llm_provider") or legacy_provider).strip().lower()
            candidate.llm.base_url = (llm.get("base_url") if "base_url" in llm else params.get("llm_base_url")) or None
            candidate.llm.api_key = (llm.get("api_key") if "api_key" in llm else trans_api_key) or None
            llm_model = llm.get("model") or params.get("llm_model") or candidate.llm.model
            if llm_model:
                candidate.llm.model = llm_model
            if "enabled" in llm:
                candidate.llm.enabled = bool(llm.get("enabled"))
        from core.factory import TranscriptionFactory
        try:
            candidate_transcriber = TranscriptionFactory.create_transcriber(candidate)
            candidate_llm = TranscriptionFactory.create_llm_processor(candidate) if candidate.llm and candidate.llm.enabled else None
        except Exception as exc:
            return {"status": "error", "code": "provider_configuration_invalid", "error": str(exc)}
        with self._config_lock:
            self.config = candidate
            self.orchestrator.config = candidate
            self.orchestrator.transcriber = candidate_transcriber
            self.orchestrator.llm_processor = candidate_llm
        return {"status": "ok", "config": self._effective_config()}

    def _effective_config(self) -> Dict[str, Any]:
        config = self.config
        if not config:
            return {}
        return {
            "transcription": {"provider": config.transcription.provider, "base_url": config.transcription.base_url, "model": config.transcription.model, "model_path": getattr(config.transcription, "model_path", None), "device": getattr(config.transcription, "device", "auto"), "compute_type": getattr(config.transcription, "compute_type", "auto"), "api_key_configured": bool(getattr(config.transcription, "api_key", None))},
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
        self.server = await asyncio.start_server(
            self.handle_client,
            self.host,
            self.port,
            limit=self._STREAM_LIMIT,
        )
        self.bound_port = self.server.sockets[0].getsockname()[1]
        self._ready_event.set()
        logger.info("AudioScribe IPC server running on %s:%s", self.host, self.bound_port)
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

    def wait_until_ready(self, timeout: float = 10.0) -> bool:
        return self._ready_event.wait(timeout) and self.bound_port is not None
