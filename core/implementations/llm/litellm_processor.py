"""
LiteLLM Processor Implementation
Uses LiteLLM for flexible LLM provider support with fallback support.
"""

import time
from typing import Optional, List, Dict

from core.interfaces.llm_processor import AbstractLLMProcessor
from core.utils.error_handler import should_retry, should_fallback, retry_with_backoff


class LiteLLMProcessor(AbstractLLMProcessor):
    """LLM processor implementation using LiteLLM with fallback support."""

    def __init__(self, config):
        """
        Initialize LiteLLM processor.

        Args:
            config: LLM configuration
        """
        self.config = config
        self.api_key = config.api_key
        self.model_chain = config.model_chain
        self.max_retries = getattr(config, 'max_retries', 2)
        self.retry_delay = getattr(config, 'retry_delay', 1.0)
        self.base_url = getattr(config, 'base_url', None)
        self.temperature = config.temperature
        self.max_tokens = config.max_tokens
        self.system_prompt = config.system_prompt

        # Track which model is currently active
        self._current_model_index = 0

        # Statistics tracking
        self._model_usage = {model: 0 for model in self.model_chain}
        self._fallback_count = 0

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

    def _prepare_messages(self, text: str, history: Optional[List[Dict[str, str]]] = None) -> List[Dict]:
        """
        Prepare messages for LLM completion.

        Args:
            text: Input text to process
            history: Optional conversation history

        Returns:
            List of message dictionaries
        """
        messages = []

        # Add system prompt if configured
        if self.system_prompt:
            messages.append({"content": self.system_prompt, "role": "system"})

        # Add conversation history if provided
        if history:
            messages.extend(history)

        # Add user message
        messages.append({"content": text, "role": "user"})

        return messages

    def _try_process(self, model: str, messages: List[Dict]) -> str:
        """
        Attempt to process messages with a specific model.

        Args:
            model: Model name to use
            messages: List of message dictionaries

        Returns:
            Processed text

        Raises:
            Exception: If processing fails
        """
        # Prepare completion parameters
        kwargs = {
            'model': model,
            'messages': messages,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens
        }

        # Add API key if provided
        if self.api_key:
            kwargs['api_key'] = self.api_key

        # Add base_url if provided
        if self.base_url:
            kwargs['base_url'] = self.base_url

        # Call litellm directly (blocking call)
        response = self.litellm.completion(**kwargs)

        # Extract text from response
        if hasattr(response, 'choices'):
            return response.choices[0].message.content
        elif isinstance(response, dict):
            return response.get('choices', [{}])[0].get('message', {}).get('content', '')
        else:
            return str(response)

    def _process_with_fallback(self, text: str, history: Optional[List[Dict[str, str]]] = None) -> Optional[str]:
        """
        Process text with retry and fallback support.

        Args:
            text: Input text to process
            history: Optional conversation history

        Returns:
            Processed text, or None if all models failed
        """
        messages = self._prepare_messages(text, history)

        # Try each model in the chain
        for model_idx, model in enumerate(self.model_chain):
            # Reset to current model for this processing attempt
            self._current_model_index = model_idx

            # Retry the current model with exponential backoff
            for retry_attempt in range(self.max_retries):
                try:
                    result = self._try_process(model, messages)

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
        Validate all models in the chain at startup.

        Raises:
            RuntimeError: If any model fails validation
        """
        print("Validating LLM models...")

        for model in self.model_chain:
            try:
                # Minimal request
                kwargs = {
                    'model': model,
                    'messages': [{"role": "user", "content": "hi"}],
                    'max_tokens': 1
                }

                if self.api_key:
                    kwargs['api_key'] = self.api_key

                if self.base_url:
                    kwargs['base_url'] = self.base_url

                self.litellm.completion(**kwargs)

                # Mark as validated
                is_primary = model == self.model_chain[0]
                label = "Primary" if is_primary else "Fallback"
                print(f"✓ {label} model validated: {model}")

            except Exception as e:
                label = "Primary" if model == self.model_chain[0] else "Fallback"
                raise RuntimeError(f"{label} model validation failed for {model}: {e}")

        print("✓ LLM service ready")
