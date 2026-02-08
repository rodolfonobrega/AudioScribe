"""
Fallback Transcriber - Manages multiple transcriber implementations with fallback.
Supports mixing different providers (LiteLLM, native Whisper, Vosk, etc.).
"""

import time
from typing import List, Optional

from core.interfaces.transcriber import AbstractTranscriber
from core.utils.error_handler import should_retry, should_fallback, retry_with_backoff


class FallbackTranscriber(AbstractTranscriber):
    """
    Transcriber that manages fallback between multiple implementations.

    This allows mixing different providers (Groq, Whisper native, Vosk, etc.)
    in a single fallback chain.

    Example:
        >>> groq = GroqTranscriber(config1)
        >>> whisper = WhisperNativeTranscriber(config2)
        >>> fallback = FallbackTranscriber([groq, whisper])
        >>> result = fallback.transcribe(audio_data)
    """

    def __init__(
        self,
        transcribers: List[AbstractTranscriber],
        max_retries: int = 2,
        retry_delay: float = 1.0
    ):
        """
        Initialize fallback transcriber.

        Args:
            transcribers: List of transcriber implementations (tried in order)
            max_retries: Number of retries per transcriber before falling back
            retry_delay: Base delay for exponential backoff in seconds
        """
        if not transcribers:
            raise ValueError("At least one transcriber must be provided")

        self.transcribers = transcribers
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Statistics tracking
        self._transcriber_usage = {
            transcriber.__class__.__name__: 0
            for transcriber in transcribers
        }
        self._fallback_count = 0

    @property
    def active_transcriber(self) -> str:
        """Return the class name of the currently active transcriber."""
        return self.transcribers[0].__class__.__name__

    def get_stats(self) -> dict:
        """
        Get usage statistics for all transcribers.

        Returns:
            Dictionary with transcriber usage and fallback count
        """
        return {
            'transcriber_usage': self._transcriber_usage.copy(),
            'fallback_count': self._fallback_count,
            'active_transcriber': self.active_transcriber,
            'num_transcribers': len(self.transcribers),
        }

    def transcribe(self, audio_data: bytes) -> Optional[str]:
        """
        Transcribe audio data with fallback across implementations.

        Args:
            audio_data: WAV audio data

        Returns:
            Transcribed text, or None if all transcribers failed
        """
        # Try each transcriber in the chain
        for idx, transcriber in enumerate(self.transcribers):
            transcriber_name = transcriber.__class__.__name__

            # Retry the current transcriber with exponential backoff
            for retry_attempt in range(self.max_retries):
                try:
                    result = transcriber.transcribe(audio_data)

                    if result is not None:
                        # Success - update stats and return
                        self._transcriber_usage[transcriber_name] += 1
                        if idx > 0:
                            print(f"✓ Fallback successful: {transcriber_name}")
                        return result

                except Exception as e:
                    # Determine if we should retry or fallback
                    if should_fallback(e):
                        print(f"✗ {transcriber_name} failed: {e}")
                        break  # Skip to next transcriber
                    elif should_retry(e) and retry_attempt < self.max_retries - 1:
                        delay = retry_with_backoff(retry_attempt, self.retry_delay)
                        print(
                            f"✗ {transcriber_name} failed: {e}\n"
                            f"Retry {retry_attempt + 1}/{self.max_retries} for {transcriber_name} after {delay}s"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        # Unknown error or final retry failed
                        print(f"✗ {transcriber_name} failed: {e}")
                        break

            # If we get here, the current transcriber failed after all retries
            if idx < len(self.transcribers) - 1:
                next_transcriber = self.transcribers[idx + 1].__class__.__name__
                print(f"→ Falling back to: {next_transcriber}")
                self._fallback_count += 1

        # All transcribers exhausted
        print("✗ All fallback transcribers exhausted")
        return None

    def transcribe_file(self, file_path: str) -> Optional[str]:
        """
        Transcribe audio file with fallback across implementations.

        Args:
            file_path: Path to WAV audio file

        Returns:
            Transcribed text, or None if all transcribers failed
        """
        # Try each transcriber in the chain
        for idx, transcriber in enumerate(self.transcribers):
            transcriber_name = transcriber.__class__.__name__

            # Retry the current transcriber with exponential backoff
            for retry_attempt in range(self.max_retries):
                try:
                    result = transcriber.transcribe_file(file_path)

                    if result is not None:
                        # Success - update stats and return
                        self._transcriber_usage[transcriber_name] += 1
                        if idx > 0:
                            print(f"✓ Fallback successful: {transcriber_name}")
                        return result

                except Exception as e:
                    # Determine if we should retry or fallback
                    if should_fallback(e):
                        print(f"✗ {transcriber_name} failed: {e}")
                        break  # Skip to next transcriber
                    elif should_retry(e) and retry_attempt < self.max_retries - 1:
                        delay = retry_with_backoff(retry_attempt, self.retry_delay)
                        print(
                            f"✗ {transcriber_name} failed: {e}\n"
                            f"Retry {retry_attempt + 1}/{self.max_retries} for {transcriber_name} after {delay}s"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        # Unknown error or final retry failed
                        print(f"✗ {transcriber_name} failed: {e}")
                        break

            # If we get here, the current transcriber failed after all retries
            if idx < len(self.transcribers) - 1:
                next_transcriber = self.transcribers[idx + 1].__class__.__name__
                print(f"→ Falling back to: {next_transcriber}")
                self._fallback_count += 1

        # All transcribers exhausted
        print("✗ All fallback transcribers exhausted")
        return None

    @property
    def supports_streaming(self) -> bool:
        """
        Check if any transcriber in the chain supports streaming.

        Returns:
            True if at least one transcriber supports streaming
        """
        return any(t.supports_streaming for t in self.transcribers)

    def health_check(self) -> None:
        """
        Validate all transcribers in the chain at startup.

        Raises:
            RuntimeError: If any transcriber fails validation
        """
        print("Validating transcriber chain...")

        for idx, transcriber in enumerate(self.transcribers):
            transcriber_name = transcriber.__class__.__name__
            try:
                transcriber.health_check()

                # Mark as validated
                is_primary = idx == 0
                label = "Primary" if is_primary else "Fallback"
                print(f"✓ {label} transcriber validated: {transcriber_name}")

            except Exception as e:
                label = "Primary" if idx == 0 else "Fallback"
                raise RuntimeError(
                    f"{label} transcriber validation failed for {transcriber_name}: {e}"
                )

        print("✓ Transcriber chain ready")
