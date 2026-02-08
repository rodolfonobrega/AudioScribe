"""
Groq Transcriber Implementation
Uses Groq's Whisper model for audio transcription via LiteLLM.
"""

import os
import tempfile
import time
from typing import Optional

from core.interfaces.transcriber import AbstractTranscriber
from core.utils.error_handler import should_retry, should_fallback, retry_with_backoff


class GroqTranscriber(AbstractTranscriber):
    """Transcriber implementation using Groq's Whisper model with fallback support."""

    def __init__(self, config):
        """
        Initialize Groq transcriber.

        Args:
            config: Transcription configuration
        """
        self.config = config
        self.api_key = config.api_key
        self.model_chain = config.model_chain
        self.max_retries = getattr(config, 'max_retries', 2)
        self.retry_delay = getattr(config, 'retry_delay', 1.0)
        self.language = config.language
        self.temperature = config.temperature

        # Track which model is currently active
        self._current_model_index = 0

        # Statistics tracking
        self._model_usage = {model: 0 for model in self.model_chain}
        self._fallback_count = 0

        if not self.api_key:
            raise ValueError(
                "Groq API key is required. Please set GROQ_API_KEY in your .env file or environment variables."
            )

        if not self.model_chain:
            raise ValueError("At least one model must be configured.")

        # Import litellm
        try:
            import litellm
            self.litellm = litellm
        except ImportError:
            raise ImportError("litellm is required. Install with: pip install litellm")

    @property
    def active_model(self) -> str:
        """Return the currently active model."""
        return self.model_chain[self._current_model_index]

    @property
    def model(self) -> str:
        """Return the primary model (for backward compatibility)."""
        return self.model_chain[0]

    def get_stats(self) -> dict:
        """
        Get usage statistics for all models.

        Returns:
            Dictionary with model usage and fallback count
        """
        return {
            'model_usage': self._model_usage.copy(),
            'fallback_count': self._fallback_count,
            'active_model': self.active_model,
        }

    def transcribe(self, audio_data: bytes) -> Optional[str]:
        """
        Transcribe audio data with retry and fallback support.

        Args:
            audio_data: WAV audio data

        Returns:
            Transcribed text, or None if all models failed
        """
        try:
            # Save audio data to temporary file
            with tempfile.NamedTemporaryFile(suffix='.flac', delete=False) as temp_file:
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
            print(f"Transcription error: {e}")
            return None

    def transcribe_file(self, file_path: str) -> Optional[str]:
        """
        Transcribe audio file with retry and fallback support.

        Args:
            file_path: Path to WAV audio file

        Returns:
            Transcribed text, or None if all models failed
        """
        # Try each model in the chain
        for model_idx, model in enumerate(self.model_chain):
            # Reset to current model for this transcription attempt
            self._current_model_index = model_idx

            # Retry the current model with exponential backoff
            for retry_attempt in range(self.max_retries):
                try:
                    result = self._try_transcribe(model, file_path)

                    # Success - update stats and return
                    self._model_usage[model] += 1
                    if model_idx > 0:
                        print(f"✓ Fallback successful: {model}")
                    return result

                except Exception as e:
                    # Determine if we should retry or fallback
                    if should_fallback(e):
                        print(f"✗ Model {model} failed: {e}")
                        break  # Skip to next model
                    elif should_retry(e) and retry_attempt < self.max_retries - 1:
                        delay = retry_with_backoff(retry_attempt, self.retry_delay)
                        print(
                            f"✗ Model {model} failed: {e}\n"
                            f"Retry {retry_attempt + 1}/{self.max_retries} for {model} after {delay}s"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        # Unknown error or final retry failed
                        print(f"✗ Model {model} failed: {e}")
                        break

            # If we get here, the current model failed after all retries
            if model_idx < len(self.model_chain) - 1:
                next_model = self.model_chain[model_idx + 1]
                print(f"→ Falling back to: {next_model}")
                self._fallback_count += 1

        # All models exhausted
        print("✗ All fallback models exhausted")
        return None

    def _try_transcribe(self, model: str, file_path: str) -> str:
        """
        Attempt to transcribe audio file with a specific model.

        Args:
            model: Model name to use
            file_path: Path to WAV audio file

        Returns:
            Transcribed text

        Raises:
            Exception: If transcription fails
        """
        # Open file for reading
        with open(file_path, 'rb') as audio_file:
            # Prepare transcription parameters
            kwargs = {
                'model': model,
                'file': audio_file,
                'api_key': self.api_key,
                'temperature': self.temperature
            }

            # Add language if not auto
            if self.language and self.language != 'auto':
                kwargs['language'] = self.language

            # Call litellm directly (blocking call)
            response = self.litellm.transcription(**kwargs)

        # Extract text from response
        if isinstance(response, dict):
            return response.get('text', '')
        elif hasattr(response, 'text'):
            return response.text
        else:
            return str(response)

    @property
    def supports_streaming(self) -> bool:
        """Groq does not support streaming transcription yet."""
        return False

    def health_check(self) -> None:
        """
        Validate all models in the chain at startup.

        Raises:
            RuntimeError: If any model fails validation
        """
        if not self.api_key:
            raise ValueError("Groq API key is missing.")

        print("Validating transcription models...")

        temp_path = None
        for model in self.model_chain:
            try:
                # Create a tiny 10ms silent wav on disk
                import wave

                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                    temp_path = temp_file.name
                    with wave.open(temp_path, 'wb') as wav:
                        wav.setnchannels(1)
                        wav.setsampwidth(2)
                        wav.setframerate(16000)
                        # 160 frames = 10ms
                        wav.writeframes(b'\x00\x00' * 160)

                # Use litellm direct call with file object
                # This verifies network, auth, and model access
                with open(temp_path, 'rb') as audio_file:
                    self.litellm.transcription(
                        model=model,
                        file=audio_file,
                        api_key=self.api_key
                    )

                # Mark as validated
                is_primary = model == self.model_chain[0]
                label = "Primary" if is_primary else "Fallback"
                print(f"✓ {label} model validated: {model}")

            except Exception as e:
                label = "Primary" if model == self.model_chain[0] else "Fallback"
                raise RuntimeError(f"{label} model validation failed for {model}: {e}")
            finally:
                # Clean up temp file
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass

        print("✓ Transcription service ready")
