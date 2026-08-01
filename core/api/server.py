"""
AudioScribe IPC API Server for Electron Desktop App Integration.
Communicates via JSON-line messages over localhost socket (127.0.0.1:8765).
"""

import asyncio
import json
import logging
import sys
import threading
from typing import Dict, Any, Optional
from core.orchestrator import TranscriptionOrchestrator
from core.utils.preflight import PreflightChecker
import sounddevice as sd

logger = logging.getLogger(__name__)


class AudioScribeServer:
    """Async socket server for Electron sidecar integration."""

    def __init__(self, orchestrator: Optional[TranscriptionOrchestrator] = None, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.orchestrator = orchestrator
        self.clients = set()
        self.server = None
        self._loop = None

    def set_orchestrator(self, orchestrator: TranscriptionOrchestrator):
        self.orchestrator = orchestrator

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        """Broadcast JSON event to all connected Electron clients."""
        payload = json.dumps({"event": event_type, "data": data}) + "\n"
        disconnected = set()
        for writer in self.clients:
            try:
                writer.write(payload.encode("utf-8"))
                await writer.drain()
            except Exception:
                disconnected.add(writer)
        self.clients -= disconnected

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming Electron client connections."""
        self.clients.add(writer)
        logger.info("Electron client connected to AudioScribe API Server.")

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break

                try:
                    message = json.loads(line.decode("utf-8").strip())
                    command = message.get("command")
                    request_id = message.get("id")

                    response = await self._process_command(command, message.get("params", {}))
                    if request_id:
                        response["id"] = request_id

                    writer.write((json.dumps(response) + "\n").encode("utf-8"))
                    await writer.drain()
                except json.JSONDecodeError:
                    error_resp = {"status": "error", "error": "Invalid JSON format"}
                    writer.write((json.dumps(error_resp) + "\n").encode("utf-8"))
                    await writer.drain()
        except Exception as e:
            logger.error(f"Client handler error: {e}")
        finally:
            self.clients.discard(writer)
            writer.close()
            await writer.wait_closed()

    async def _process_command(self, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming API commands."""
        if command == "ping":
            return {"status": "ok", "message": "AudioScribe Engine active"}

        elif command == "get_devices":
            try:
                devices = sd.query_devices()
                input_devs = []
                for i, dev in enumerate(devices):
                    if dev.get("max_input_channels", 0) > 0:
                        input_devs.append({
                            "index": i,
                            "name": dev.get("name"),
                            "channels": dev.get("max_input_channels"),
                            "default_samplerate": dev.get("default_samplerate")
                        })
                return {"status": "ok", "devices": input_devs}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        elif command == "preflight":
            checker = PreflightChecker()
            checker.run_all_checks()
            return {
                "status": "ok",
                "errors": checker.errors,
                "warnings": checker.warnings,
                "ready": len(checker.errors) == 0
            }

        elif command == "start_recording":
            if self.orchestrator and self.orchestrator.audio_input:
                self.orchestrator.audio_input.start_recording()
                await self.broadcast("status_changed", {"status": "recording"})
                return {"status": "ok", "recording": True}
            return {"status": "error", "error": "Orchestrator audio input not initialized"}

        elif command == "stop_recording":
            if self.orchestrator and self.orchestrator.audio_input:
                audio_bytes = self.orchestrator.audio_input.stop_recording()
                await self.broadcast("status_changed", {"status": "processing"})
                if audio_bytes and self.orchestrator._processing_queue:
                    self.orchestrator._processing_queue.put(audio_bytes)
                return {"status": "ok", "recording": False}
            return {"status": "error", "error": "Orchestrator audio input not initialized"}

        elif command == "get_status":
            is_recording = self.orchestrator.audio_input.is_recording() if (self.orchestrator and self.orchestrator.audio_input) else False
            return {
                "status": "ok",
                "is_recording": is_recording,
                "engine_running": self.orchestrator._is_running if self.orchestrator else False
            }

        else:
            return {"status": "error", "error": f"Unknown command: {command}"}

    async def start(self):
        """Start async server."""
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logger.info(f"AudioScribe API Server running on {self.host}:{self.port}")
        async with self.server:
            await self.server.serve_forever()

    def run_in_thread(self):
        """Run server in background thread."""
        def _thread_target():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self.start())

        t = threading.Thread(target=_thread_target, daemon=True)
        t.start()
        return t
