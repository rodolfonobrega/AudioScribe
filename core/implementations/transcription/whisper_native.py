"""
Whisper Native Transcriber Implementation
Uses OpenAI's Whisper library directly (not via LiteLLM).
This is an example of a non-LiteLLM provider implementation.
"""

import os
import tempfile
import warnings
from typing import Optional
from dataclasses import dataclass

from core.interfaces.transcriber import AbstractTranscriber


@dataclass
class WhisperNativeConfig:
    """Configuration for Whisper native transcriber."""
    model_size: str = "base"  # tiny, base, small, medium, large-v1, large-v2, large-v3
    device: str = "cpu"  # cpu, cuda, mps
    language: Optional[str] = None  # None = auto-detect
    compute_type: str = "int8"  # int8, float16, float32


class WhisperNativeTranscriber(AbstractTranscriber):
    """
    Transcriber implementation using OpenAI's Whisper library directly.

    This is an example of a non-LiteLLM provider that can be used
    in combination with LiteLLM-based transcribers via FallbackTranscriber.

    Installation:
        pip install openai-whisper

    Example:
        >>> config = WhisperNativeConfig(model_size="base", device="cpu")
        >>> transcriber = WhisperNativeTranscriber(config)
        >>> result = transcriber.transcribe(audio_data)
    """

    def __init__(self, config: WhisperNativeConfig):
        """
        Initialize Whisper native transcriber.

        Args:
            config: WhisperNativeConfig instance
        """
        self.config = config
        self.model_size = config.model_size
        self.device = config.device
        self.language = config.language
        self.compute_type = config.compute_type

        # Validate model_size
        valid_models = [
            "tiny", "tiny.en", "base", "base.en",
            "small", "small.en", "medium", "medium.en",
            "large", "large-v1", "large-v2", "large-v3"
        ]
        if self.model_size not in valid_models:
            raise ValueError(
                f"Invalid model_size: {self.model_size}. "
                f"Must be one of: {', '.join(valid_models)}"
            )

        # Validate compute_type
        valid_compute_types = ["int8", "float16", "float32"]
        if self.compute_type not in valid_compute_types:
            raise ValueError(
                f"Invalid compute_type: {self.compute_type}. "
                f"Must be one of: {', '.join(valid_compute_types)}"
            )

        # Import whisper (suppress warning about FP16 support)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                import whisper
                self.whisper = whisper
            except ImportError:
                raise ImportError(
                    "whisper is required. Install with: pip install openai-whisper"
                )

        # Load model
        print(f"Loading Whisper model: {self.model_size} on {self.device}...")
        try:
            self.model = self.whisper.load_model(
                self.model_size,
                device=self.device
            )
            print(f"✓ Whisper model loaded successfully")
        except Exception as e:
            raise RuntimeError(f"Failed to load Whisper model: {e}")

    def transcribe(self, audio_data: bytes) -> Optional[str]:
        """
        Transcribe audio data using Whisper native.

        Args:
            audio_data: WAV audio data

        Returns:
            Transcribed text, or None if failed
        """
        try:
            # Save audio data to temporary file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
                temp_file.write(audio_data)

            # Transcribe the temporary file
            result = self.transcribe_file(temp_path)

            # Clean up
            try:
                os.unlink(temp_path)
            except OSError:
                pass

            return result

        except Exception as e:
            print(f"Whisper native transcription error: {e}")
            return None

    def transcribe_file(self, file_path: str) -> Optional[str]:
        """
        Transcribe audio file using Whisper native.

        Args:
            file_path: Path to audio file (WAV, MP3, FLAC, etc.)

        Returns:
            Transcribed text, or None if failed
        """
        try:
            # Prepare transcription options
            options = {
                'fp16': False,  # Use FP32 for better compatibility
            }

            # Add language if specified
            if self.language:
                options['language'] = self.language

            # Transcribe
            result = self.model.transcribe(file_path, **options)

            # Extract and return text
            text = result.get('text', '').strip()
            return text if text else None

        except Exception as e:
            print(f"Whisper native file transcription error: {e}")
            return None

    @property
    def supports_streaming(self) -> bool:
        """Whisper native does not support streaming transcription."""
        return False

    def health_check(self) -> None:
        """
        Validate Whisper native transcriber.

        Raises:
            RuntimeError: If validation fails
        """
        if self.model is None:
            raise RuntimeError("Whisper model not loaded")

        # Create a tiny silent audio file for testing
        temp_path = None
        try:
            import wave

            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
                with wave.open(temp_path, 'wb') as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16000)
                    # 160 frames = 10ms of silence
                    wav.writeframes(b'\x00\x00' * 160)

            # Try to transcribe (should work even with silence)
            result = self.model.transcribe(temp_path, fp16=False)

            # We don't care about the result, just that it didn't raise
            print("✓ Whisper native transcriber ready")

        except Exception as e:
            raise RuntimeError(f"Whisper native validation failed: {e}")
        finally:
            # Clean up temp file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
