"""
Transcription Orchestrator
Manages the transcription workflow and coordinates components.
"""

import sys
import threading
import queue
import time
import uuid
from typing import Optional, Callable

from core.interfaces.audio_input import AbstractAudioInput
from core.interfaces.transcriber import AbstractTranscriber
from core.interfaces.llm_processor import AbstractLLMProcessor
from core.interfaces.output_handler import AbstractOutputHandler
from core.interfaces.keyboard_listener import AbstractKeyboardListener
from core.ui import TerminalUI
from core.usage import UsageRecord, UsageStore, PriceCatalog, audio_duration_seconds, has_audio_data
from core.local_store import LocalStore
from core.text_expansion import dictionary_hint_words, expand_snippets


class TranscriptionOrchestrator:
    """Orchestrates the transcription workflow."""
    
    def __init__(
        self,
        audio_input: Optional[AbstractAudioInput],
        transcriber: AbstractTranscriber,
        output_handler: AbstractOutputHandler,
        llm_processor: Optional[AbstractLLMProcessor] = None,
        keyboard_listener: Optional[AbstractKeyboardListener] = None,
        ui: Optional[TerminalUI] = None,
        config=None,
        usage_store: Optional[UsageStore] = None,
        local_store: Optional[LocalStore] = None,
    ):
        """
        Initialize the orchestrator.
        
        Args:
            audio_input: Audio input component
            transcriber: Transcription component
            output_handler: Output component
            llm_processor: Optional LLM processor
            keyboard_listener: Optional keyboard listener
            ui: Optional UI component
        """
        self.audio_input = audio_input
        self.transcriber = transcriber
        self.output_handler = output_handler
        self.llm_processor = llm_processor
        self.keyboard_listener = keyboard_listener
        self.ui = ui or TerminalUI()
        self.config = config
        self.usage_store = usage_store or (UsageStore() if config is not None else None)
        self.local_store = local_store or (LocalStore() if config is not None else None)
        self.price_catalog = PriceCatalog()
        self._event_listeners = []
        
        self._is_running = False
        self._processing_queue = queue.Queue()
        self._processing_thread = None
        self._stop_event = threading.Event()
    
    def start(self):
        """Start the orchestrator."""
        if self._is_running:
            print("Already running")
            return
        
        self._is_running = True
        self._stop_event.clear()
        
        # Start processing thread
        self._processing_thread = threading.Thread(
            target=self._process_audio_loop,
            daemon=True
        )
        self._processing_thread.start()
        
        # Start keyboard listener if available
        if self.keyboard_listener:
            self.keyboard_listener.start(
                on_press=self._on_hotkey_press,
                on_release=self._on_hotkey_release
            )
        
        if self.ui:
            hotkey = getattr(self.keyboard_listener, "hotkey", None)
            message = f"Press {hotkey.upper()} to record | Ctrl+C to exit" if hotkey else "Ready | Ctrl+C to exit"
            self.ui.update_live_status("ready", message)
        self._emit_event("engine_status", {"status": "ready", "engine_running": True})
        self._is_running = True
        if getattr(self.ui, "verbose", True):
            print("[Orchestrator] Service started successfully.")

    def start_recording(self):
        """Start audio recording if not already recording."""
        if self.audio_input is None:
            raise RuntimeError("Audio capture is available only in CLI mode.")
        if not self.audio_input.is_recording:
            while not self._processing_queue.empty():
                try:
                    self._processing_queue.get_nowait()
                except queue.Empty:
                    break
            self.audio_input.start_recording()
            self._emit_event("status_changed", {"status": "recording"})
            if self.ui:
                self.ui.update_live_status("recording")

    def stop_recording(self):
        """Stop audio recording and enqueue audio for processing."""
        if self.audio_input is None:
            raise RuntimeError("Audio capture is available only in CLI mode.")
        if self.audio_input.is_recording:
            audio_data = self.audio_input.stop_recording()
            self._processing_queue.put(audio_data)
            self._emit_event("status_changed", {"status": "processing"})
            if self.ui:
                self.ui.update_live_status("processing")

    def toggle_recording(self):
        """Toggle recording state."""
        if self.audio_input is None:
            raise RuntimeError("Audio capture is available only in CLI mode.")
        if self.audio_input.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    def _on_hotkey_press(self):
        """Handle hotkey press event."""
        self.start_recording()

    def _on_hotkey_release(self):
        """Handle hotkey release event."""
        self.stop_recording()

    def add_event_listener(self, listener: Callable[[str, dict], None]) -> None:
        if listener not in self._event_listeners:
            self._event_listeners.append(listener)

    def _emit_event(self, event_type: str, data: dict) -> None:
        for listener in list(self._event_listeners):
            try:
                listener(event_type, data)
            except Exception as exc:
                print(f"Event listener error: {exc}")
    
    def _process_audio_loop(self):
        """Process audio in a separate thread."""
        while not self._stop_event.is_set():
            try:
                # Get audio data from queue with timeout
                queued = self._processing_queue.get(timeout=0.5)
                if isinstance(queued, tuple):
                    audio_data, profile = queued
                else:
                    audio_data, profile = queued, None
                
                # Process audio
                self._process_audio(audio_data, profile=profile)
                
            except queue.Empty:
                continue
            except Exception as e:
                import logging
                logging.getLogger(__name__).error("Processing error in audio loop: %s", e, exc_info=True)
                print(f"Processing error: {e}")
                self._emit_event("error", {"stage": "processing", "message": f"Erro no processamento de áudio: {e}"})
                self._emit_event("status_changed", {"status": "ready"})
    
    def _process_audio(self, audio_data: bytes, profile=None):
        """Process audio data through the pipeline."""
        try:
            from core.implementations.audio.sounddevice_input import calculate_rms
            request_id = uuid.uuid4().hex
            start_time = time.perf_counter()

            if not has_audio_data(audio_data) or len(audio_data) < 100:
                self._emit_event("error", {"request_id": request_id, "stage": "audio", "message": "Nenhum áudio capturado."})
                self._emit_event("status_changed", {"status": "ready"})
                return ""

            audio_seconds = audio_duration_seconds(audio_data)

            # Check RMS Noise Gate threshold
            silence_threshold = 0.005
            if hasattr(self.audio_input, 'config') and hasattr(self.audio_input.config, 'silence_threshold_rms'):
                silence_threshold = self.audio_input.config.silence_threshold_rms

            compressed_container = (
                isinstance(audio_data, bytes)
                and (audio_data.startswith(b"OggS") or audio_data[:4] == b"\x1a\x45\xdf\xa3")
            )
            rms = None if compressed_container else calculate_rms(audio_data)
            if rms is not None and rms < silence_threshold:
                if self.ui:
                    self.ui.show_info(f"Silent audio ignored (RMS {rms:.4f} < {silence_threshold})")
                    hotkey_msg = f"Press {self.keyboard_listener.hotkey.upper()} to record" if (self.keyboard_listener and hasattr(self.keyboard_listener, 'hotkey')) else "Ready"
                    self.ui.update_live_status("ready", hotkey_msg)
                self._emit_event("status_changed", {"status": "ready"})
                self._emit_event("error", {"stage": "audio", "message": f"Silêncio detectado (RMS {rms:.4f} < {silence_threshold})."})
                return ""

            self._emit_event("status_changed", {"status": "transcribing", "request_id": request_id})

            # Transcribe
            if self.ui:
                self.ui.update_live_status("transcribing")
            
            dictionary = self.local_store.list_dictionary() if self.local_store else []
            vocabulary = dictionary_hint_words(dictionary)
            if vocabulary and hasattr(self.transcriber, "transcribe_with_vocabulary"):
                text = self.transcriber.transcribe_with_vocabulary(audio_data, vocabulary)
            else:
                text = self.transcriber.transcribe(audio_data)
            raw_text = text  # Save original transcription
            
            if not text:
                if self.ui:
                    self.ui.update_live_status("error", "Transcription failed")
                self._record_usage(request_id, "transcription", self.transcriber, "error", start_time, audio_seconds, "empty_result")
                self._emit_event("transcription_result", {"text": "", "is_silent": True, "latency_ms": round((time.perf_counter() - start_time) * 1000.0)})
                self._emit_event("error", {"request_id": request_id, "stage": "transcription", "message": "Transcrição vazia"})
                self._emit_event("status_changed", {"status": "ready"})
                return ""
            
            # Post-processing is opt-in per profile. A plain dictation must
            # remain the literal transcription, even if an LLM provider was
            # configured for other profiles.
            profile_prompt = (profile or {}).get("prompt", "").strip() if isinstance(profile, dict) else ""
            if profile_prompt and not self.llm_processor:
                message = "This profile requires post-processing, but no LLM provider is enabled. Enable and save Profile Processing in Settings before using this shortcut."
                self._emit_event("error", {"request_id": request_id, "stage": "llm", "code": "profile_llm_not_configured", "message": message})
                self._emit_event("transcription_result", {
                    "request_id": request_id,
                    "text": "",
                    "raw_text": raw_text,
                    "is_error": True,
                    "is_silent": False,
                    "latency_ms": round((time.perf_counter() - start_time) * 1000.0),
                    "error": message,
                })
                self._emit_event("status_changed", {"status": "ready"})
                return ""

            if self.llm_processor and profile_prompt:
                if self.ui:
                    self.ui.update_live_status("llm")
                self._emit_event("status_changed", {"status": "llm", "request_id": request_id})
                enhanced_text = self.llm_processor.process(text, system_prompt_override=profile_prompt)
                if not enhanced_text:
                    message = "Profile post-processing failed. The raw transcription was not pasted because this shortcut requires its profile rule."
                    self._emit_event("error", {"request_id": request_id, "stage": "llm", "code": "profile_llm_failed", "message": message})
                    self._emit_event("transcription_result", {
                        "request_id": request_id,
                        "text": "",
                        "raw_text": raw_text,
                        "is_error": True,
                        "is_silent": False,
                        "latency_ms": round((time.perf_counter() - start_time) * 1000.0),
                        "error": message,
                    })
                    self._emit_event("status_changed", {"status": "ready"})
                    return ""
                text = enhanced_text

            if self.local_store:
                text = expand_snippets(text, self.local_store.list_snippets(enabled_only=True))
            
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            # Output result - show both raw and processed if LLM was used with latency
            if self.ui:
                self.ui.show_result(text, raw_text=raw_text if profile_prompt else None, latency_ms=latency_ms)
            
            self.output_handler.output(text)

            history_item = None
            if self.local_store:
                history_item = self.local_store.save_transcription(
                    text,
                    raw_text=raw_text,
                    model=self._component_model(self.transcriber),
                    provider=self._component_provider(self.transcriber),
                    duration_ms=round(latency_ms),
                )

            self._record_usage(request_id, "transcription", self.transcriber, "success", start_time, audio_seconds)
            if self.llm_processor and profile_prompt:
                self._record_usage(request_id, "llm", self.llm_processor, "success", start_time, audio_seconds)
            self._emit_event("transcription_result", {
                "request_id": request_id,
                "raw_text": raw_text,
                "text": text,
                "latency_ms": latency_ms,
                "provider": self._component_provider(self.transcriber),
                "model": self._component_model(self.transcriber),
                "history": history_item,
            })
            
            if self.ui:
                hotkey_msg = f"Press {self.keyboard_listener.hotkey.upper()} to record" if (self.keyboard_listener and hasattr(self.keyboard_listener, 'hotkey')) else "Ready"
                self.ui.update_live_status("ready", hotkey_msg)

            return text
            
        except Exception as e:
            if self.ui:
                self.ui.show_error(f"Audio processing error: {e}")
                hotkey_msg = f"Press {self.keyboard_listener.hotkey.upper()} to record" if (self.keyboard_listener and hasattr(self.keyboard_listener, 'hotkey')) else "Ready"
                self.ui.update_live_status("ready", hotkey_msg)
            self._emit_event("error", {"stage": "processing", "message": str(e)})
            self._emit_event("transcription_result", {
                "text": "",
                "is_error": True,
                "is_silent": False,
                "latency_ms": 0,
                "error": str(e),
            })
            self._emit_event("status_changed", {"status": "ready"})
            return None

    @staticmethod
    def _component_model(component) -> str:
        return getattr(component, "active_model", None) or getattr(component, "model", None) or component.__class__.__name__

    @staticmethod
    def _component_provider(component) -> str:
        config = getattr(component, "config", None)
        return getattr(config, "provider", None) or str(TranscriptionOrchestrator._component_model(component)).split("/", 1)[0]

    def _record_usage(self, request_id, operation, component, status, start_time, audio_seconds, error_code=None):
        if not self.usage_store:
            return
        usage = getattr(component, "last_usage", {}) or {}
        model = self._component_model(component)
        cost = usage.get("cost")
        price_source = "provider_response" if cost is not None else "unknown"
        if operation == "transcription" and cost is None:
            cost, price_source = self.price_catalog.estimate_transcription(model, audio_seconds)
        if operation == "llm" and cost is None:
            cost, price_source = self.price_catalog.estimate_llm(model, usage.get("input_tokens"), usage.get("output_tokens"))
        self.usage_store.record(UsageRecord(
            request_id=request_id,
            operation=operation,
            provider=self._component_provider(component),
            model=model,
            status=status,
            latency_ms=(time.perf_counter() - start_time) * 1000.0,
            audio_seconds=audio_seconds if operation == "transcription" else None,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            estimated_cost_usd=cost,
            price_source=price_source,
            fallback_used=bool(getattr(component, "last_fallback_used", False)),
            error_code=error_code,
        ))
    
    def stop(self):
        """Stop the orchestrator."""
        if not self._is_running:
            return
        
        self._is_running = False
        self._stop_event.set()
        
        # Stop keyboard listener
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        
        # Stop recording if active
        if self.audio_input and self.audio_input.is_recording:
            self.audio_input.stop_recording()
        
        # Wait for processing thread
        if self._processing_thread:
            self._processing_thread.join(timeout=2.0)
        
        print("\nOrchestrator stopped.")
        self._emit_event("engine_status", {"status": "stopped", "engine_running": False})
    
    def process_file(self, file_path: str) -> None:
        """
        Process an audio file.
        
        Args:
            file_path: Path to audio file
        """
        if self.ui:
            self.ui.update_status(f"Processing file: {file_path}")
        
        try:
            # Read file
            import soundfile as sf
            audio_data, sample_rate = sf.read(file_path)
            
            # Convert to WAV bytes
            import io
            buffer = io.BytesIO()
            sf.write(buffer, audio_data, sample_rate, format='WAV')
            audio_bytes = buffer.getvalue()
            
            # Process
            self._process_audio(audio_bytes)
            
        except Exception as e:
            print(f"File processing error: {e}")
            if self.ui:
                self.ui.update_status(f"Error: {e}")
    
    def transcribe_text(self, text: str) -> None:
        """
        Transcribe and enhance text (for API-based input).
        
        Args:
            text: Input text
        """
        if self.ui:
            self.ui.update_status("Processing text...")
        
        try:
            result = text
            
            # Process with LLM if available
            if self.llm_processor:
                result = self.llm_processor.process(text)
                
                if not result:
                    result = text
            
            # Output result
            if self.ui:
                self.ui.show_result(result)
            
            self.output_handler.output(result)
            
            if self.ui:
                self.ui.update_status("Ready.")
            
        except Exception as e:
            print(f"Text processing error: {e}")
            if self.ui:
                self.ui.update_status(f"Error: {e}")
    
    @property
    def is_running(self) -> bool:
        """Check if orchestrator is running."""
        return self._is_running
