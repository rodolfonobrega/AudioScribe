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
from core.usage import UsageRecord, UsageStore, PriceCatalog, audio_duration_seconds


class TranscriptionOrchestrator:
    """Orchestrates the transcription workflow."""
    
    def __init__(
        self,
        audio_input: AbstractAudioInput,
        transcriber: AbstractTranscriber,
        output_handler: AbstractOutputHandler,
        llm_processor: Optional[AbstractLLMProcessor] = None,
        keyboard_listener: Optional[AbstractKeyboardListener] = None,
        ui: Optional[TerminalUI] = None,
        config=None,
        usage_store: Optional[UsageStore] = None
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
            self.keyboard_listener.start(on_press=self._on_hotkey_press)
        
        if self.ui:
            hotkey = getattr(self.keyboard_listener, "hotkey", None)
            message = f"Press {hotkey.upper()} to record | Ctrl+C to exit" if hotkey else "Ready | Ctrl+C to exit"
            self.ui.update_live_status("ready", message)
        self._emit_event("engine_status", {"status": "ready", "engine_running": True})

    def add_event_listener(self, listener: Callable[[str, dict], None]) -> None:
        if listener not in self._event_listeners:
            self._event_listeners.append(listener)

    def _emit_event(self, event_type: str, data: dict) -> None:
        for listener in list(self._event_listeners):
            try:
                listener(event_type, data)
            except Exception as exc:
                print(f"Event listener error: {exc}")
    
    def _on_hotkey_press(self):
        """Handle hotkey press."""
        if self.audio_input.is_recording:
            # Stop recording
            audio_data = self.audio_input.stop_recording()
            self._processing_queue.put(audio_data)
            if self.ui:
                self.ui.update_live_status("processing")
        else:
            # Start recording
            self.audio_input.start_recording()
            if self.ui:
                self.ui.update_live_status("recording")
    
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
                print(f"Processing error: {e}")
    
    def _process_audio(self, audio_data: bytes, profile=None):
        """Process audio data through the pipeline."""
        try:
            from core.implementations.audio.sounddevice_input import calculate_rms
            request_id = uuid.uuid4().hex
            start_time = time.perf_counter()
            audio_seconds = audio_duration_seconds(audio_data)

            # Check RMS Noise Gate threshold
            silence_threshold = 0.005
            if hasattr(self.audio_input, 'config') and hasattr(self.audio_input.config, 'silence_threshold_rms'):
                silence_threshold = self.audio_input.config.silence_threshold_rms

            rms = calculate_rms(audio_data)
            if rms < silence_threshold:
                if self.ui:
                    self.ui.show_info(f"Silent audio ignored (RMS {rms:.4f} < {silence_threshold})")
                    hotkey_msg = f"Press {self.keyboard_listener.hotkey.upper()} to record" if (self.keyboard_listener and hasattr(self.keyboard_listener, 'hotkey')) else "Ready"
                    self.ui.update_live_status("ready", hotkey_msg)
                return

            self._emit_event("status_changed", {"status": "transcribing", "request_id": request_id})

            # Transcribe
            if self.ui:
                self.ui.update_live_status("transcribing")
            
            text = self.transcriber.transcribe(audio_data)
            raw_text = text  # Save original transcription
            
            if not text:
                if self.ui:
                    self.ui.update_live_status("error", "Transcription failed")
                self._record_usage(request_id, "transcription", self.transcriber, "error", start_time, audio_seconds, "empty_result")
                self._emit_event("error", {"request_id": request_id, "stage": "transcription", "message": "Transcrição vazia"})
                return
            
            # Process with LLM if available
            if self.llm_processor:
                if self.ui:
                    self.ui.update_live_status("llm")
                self._emit_event("status_changed", {"status": "llm", "request_id": request_id})
                
                profile_prompt = (profile or {}).get("prompt") if isinstance(profile, dict) else None
                enhanced_text = (
                    self.llm_processor.process(text, system_prompt_override=profile_prompt)
                    if profile_prompt else self.llm_processor.process(text)
                )
                
                if enhanced_text:
                    text = enhanced_text
            
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            # Output result - show both raw and processed if LLM was used with latency
            if self.ui:
                self.ui.show_result(text, raw_text=raw_text if self.llm_processor else None, latency_ms=latency_ms)
            
            self.output_handler.output(text)

            self._record_usage(request_id, "transcription", self.transcriber, "success", start_time, audio_seconds)
            if self.llm_processor:
                self._record_usage(request_id, "llm", self.llm_processor, "success", start_time, audio_seconds)
            self._emit_event("transcription_result", {
                "request_id": request_id,
                "raw_text": raw_text,
                "text": text,
                "latency_ms": latency_ms,
                "provider": self._component_provider(self.transcriber),
                "model": self._component_model(self.transcriber),
            })
            
            if self.ui:
                hotkey_msg = f"Press {self.keyboard_listener.hotkey.upper()} to record" if (self.keyboard_listener and hasattr(self.keyboard_listener, 'hotkey')) else "Ready"
                self.ui.update_live_status("ready", hotkey_msg)
            
        except Exception as e:
            if self.ui:
                self.ui.show_error(f"Audio processing error: {e}")
                hotkey_msg = f"Press {self.keyboard_listener.hotkey.upper()} to record" if (self.keyboard_listener and hasattr(self.keyboard_listener, 'hotkey')) else "Ready"
                self.ui.update_live_status("ready", hotkey_msg)
            self._emit_event("error", {"stage": "processing", "message": str(e)})

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
        if self.audio_input.is_recording:
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
