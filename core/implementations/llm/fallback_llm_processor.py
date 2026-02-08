"""
Fallback LLM Processor - Manages multiple LLM implementations with fallback.
Supports mixing different providers (LiteLLM, Ollama, local models, etc.).
"""

import time
from typing import List, Optional, Dict

from core.interfaces.llm_processor import AbstractLLMProcessor
from core.utils.error_handler import should_retry, should_fallback, retry_with_backoff


class FallbackLLMProcessor(AbstractLLMProcessor):
    """
    LLM processor that manages fallback between multiple implementations.

    This allows mixing different providers (LiteLLM, Ollama, custom, etc.)
    in a single fallback chain.

    Example:
        >>> litellm = LiteLLMProcessor(config1)
        >>> ollama = OllamaProcessor(config2)
        >>> fallback = FallbackLLMProcessor([litellm, ollama])
        >>> result = fallback.process(text)
    """

    def __init__(
        self,
        processors: List[AbstractLLMProcessor],
        max_retries: int = 2,
        retry_delay: float = 1.0
    ):
        """
        Initialize fallback LLM processor.

        Args:
            processors: List of LLM processor implementations (tried in order)
            max_retries: Number of retries per processor before falling back
            retry_delay: Base delay for exponential backoff in seconds
        """
        if not processors:
            raise ValueError("At least one processor must be provided")

        self.processors = processors
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Statistics tracking
        self._processor_usage = {
            processor.__class__.__name__: 0
            for processor in processors
        }
        self._fallback_count = 0

    @property
    def active_processor(self) -> str:
        """Return the class name of the currently active processor."""
        return self.processors[0].__class__.__name__

    def get_stats(self) -> dict:
        """
        Get usage statistics for all processors.

        Returns:
            Dictionary with processor usage and fallback count
        """
        return {
            'processor_usage': self._processor_usage.copy(),
            'fallback_count': self._fallback_count,
            'active_processor': self.active_processor,
            'num_processors': len(self.processors),
        }

    def _process_with_fallback(
        self,
        text: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Optional[str]:
        """
        Process text with fallback across implementations.

        Args:
            text: Input text to process
            history: Optional conversation history

        Returns:
            Processed text, or None if all processors failed
        """
        # Try each processor in the chain
        for idx, processor in enumerate(self.processors):
            processor_name = processor.__class__.__name__

            # Retry the current processor with exponential backoff
            for retry_attempt in range(self.max_retries):
                try:
                    # Call the appropriate method based on whether history is provided
                    if history:
                        result = processor.process_with_history(text, history)
                    else:
                        result = processor.process(text)

                    if result is not None:
                        # Success - update stats and return
                        self._processor_usage[processor_name] += 1
                        if idx > 0:
                            print(f"✓ Fallback successful: {processor_name}")
                        return result

                except Exception as e:
                    # Determine if we should retry or fallback
                    if should_fallback(e):
                        print(f"✗ {processor_name} failed: {e}")
                        break  # Skip to next processor
                    elif should_retry(e) and retry_attempt < self.max_retries - 1:
                        delay = retry_with_backoff(retry_attempt, self.retry_delay)
                        print(
                            f"✗ {processor_name} failed: {e}\n"
                            f"Retry {retry_attempt + 1}/{self.max_retries} for {processor_name} after {delay}s"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        # Unknown error or final retry failed
                        print(f"✗ {processor_name} failed: {e}")
                        break

            # If we get here, the current processor failed after all retries
            if idx < len(self.processors) - 1:
                next_processor = self.processors[idx + 1].__class__.__name__
                print(f"→ Falling back to: {next_processor}")
                self._fallback_count += 1

        # All processors exhausted
        print("✗ All fallback processors exhausted")
        return None

    def process(self, text: str) -> Optional[str]:
        """
        Process text with LLM.

        Args:
            text: Input text to process

        Returns:
            Processed text, or None if processing failed
        """
        return self._process_with_fallback(text)

    def process_with_history(self, text: str, history: List[Dict[str, str]]) -> Optional[str]:
        """
        Process text with conversation history.

        Args:
            text: Input text to process
            history: Conversation history

        Returns:
            Processed text, or None if processing failed
        """
        return self._process_with_fallback(text, history)

    def health_check(self) -> None:
        """
        Validate all processors in the chain at startup.

        Raises:
            RuntimeError: If any processor fails validation
        """
        print("Validating LLM processor chain...")

        for idx, processor in enumerate(self.processors):
            processor_name = processor.__class__.__name__
            try:
                processor.health_check()

                # Mark as validated
                is_primary = idx == 0
                label = "Primary" if is_primary else "Fallback"
                print(f"✓ {label} processor validated: {processor_name}")

            except Exception as e:
                label = "Primary" if idx == 0 else "Fallback"
                raise RuntimeError(
                    f"{label} processor validation failed for {processor_name}: {e}"
                )

        print("✓ LLM processor chain ready")
