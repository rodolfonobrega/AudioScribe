"""
Transcription Orchestrator
Manages the transcription workflow and coordinates components.
"""

import sys
import threading
import queue
from typing import Optional, Callable

from core.interfaces.audio_input import AbstractAudioInput
from core.interfaces.transcriber import AbstractTranscriber
from core.interfaces.llm_processor import AbstractLLMProcessor
from core.interfaces.output_handler import AbstractOutputHandler
from core.interfaces.keyboard_listener import AbstractKeyboardListener
from core.ui import TerminalUI


class TranscriptionOrchestrator:
    """Orchestrates the transcription workflow."""
    
    def __init__(
        self,
        audio_input: AbstractAudioInput,
        transcriber: AbstractTranscriber,
        output_handler: AbstractOutputHandler,
        llm_processor: Optional[AbstractLLMProcessor] = None,
        keyboard_listener: Optional[AbstractKeyboardListener] = None,
        ui: Optional[TerminalUI] = None
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
            self.ui.update_live_status("ready", f"Press {self.keyboard_listener.hotkey.upper()} to record | Ctrl+C to exit")
    
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
                audio_data = self._processing_queue.get(timeout=0.5)
                
                # Process audio
                self._process_audio(audio_data)
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Processing error: {e}")
    
    def _process_audio(self, audio_data: bytes):
        """Process audio data through the pipeline."""
        try:
            # Transcribe
            if self.ui:
                self.ui.update_live_status("transcribing")
            
            text = self.transcriber.transcribe(audio_data)
            raw_text = text  # Save original transcription
            
            if not text:
                if self.ui:
                    self.ui.update_live_status("error", "Transcription failed")
                return
            
            # Process with LLM if available
            if self.llm_processor:
                if self.ui:
                    self.ui.update_live_status("llm")
                
                enhanced_text = self.llm_processor.process(text)
                
                if enhanced_text:
                    text = enhanced_text
            
            # Output result - show both raw and processed if LLM was used
            if self.ui:
                self.ui.show_result(text, raw_text=raw_text if self.llm_processor else None)
            
            self.output_handler.output(text)
            
            if self.ui:
                self.ui.update_live_status("ready", f"Press {self.keyboard_listener.hotkey.upper()} to record")
            
        except Exception as e:
            if self.ui:
                self.ui.show_error(f"Audio processing error: {e}")
                self.ui.update_live_status("ready", f"Press {self.keyboard_listener.hotkey.upper()} to record")
    
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
