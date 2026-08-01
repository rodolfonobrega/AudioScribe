"""
LiteLLM Universal Transcriber Implementation
Unified audio transcriber supporting 100+ AI providers (Groq, OpenAI, Google, Deepgram)
as well as local OpenAI-compatible endpoints (Ollama, LocalAI, vLLM via base_url).
"""

import os
import tempfile
import time
from typing import Optional, List, Dict

from core.interfaces.transcriber import AbstractTranscriber
from core.utils.error_handler import should_retry, should_fallback, retry_with_backoff
from core.model_discovery import discover_models
from core.usage import extract_usage, response_cost

try:
    import litellm
except ImportError:
    litellm = None


class LiteLLMTranscriber(AbstractTranscriber):
    """
    Universal Transcriber powered by LiteLLM.
    
    Supports:
      - Cloud API Providers: Groq, OpenAI, Google, Deepgram, Anthropic
      - Local Endpoints: Ollama, LocalAI, whisper.cpp server via base_url (e.g. http://localhost:11434/v1)
      - Fallback Chains: Tries fallback models in order if primary fails.
    """

    def __init__(self, config):
        """
        Initialize LiteLLM Universal Transcriber.

        Args:
            config: Transcription configuration
        """
        self.config = config
        self.api_key = getattr(config, 'api_key', None) or os.getenv('GROQ_API_KEY') or os.getenv('OPENAI_API_KEY') or os.getenv('LITELLM_API_KEY')
        self.base_url = getattr(config, 'base_url', None) or os.getenv('TRANSCRIPTION_BASE_URL')
        self.model_chain = getattr(config, 'model_chain', [config.model])
        self.max_retries = getattr(config, 'max_retries', 2)
        self.retry_delay = getattr(config, 'retry_delay', 1.0)
        self.language = getattr(config, 'language', 'auto')
        self.temperature = getattr(config, 'temperature', 0.0)

        # Track which model is currently active
        self._current_model_index = 0

        # Statistics tracking
        self._model_usage = {model: 0 for model in self.model_chain}
        self._fallback_count = 0
        self.last_usage = {"input_tokens": None, "output_tokens": None, "cost": None}

        if not self.model_chain:
            raise ValueError("At least one model must be configured for transcription.")

        if litellm is None:
            raise ImportError("litellm is required for transcription. Install with: pip install litellm")

        self.litellm = litellm

    @property
    def active_model(self) -> str:
        """Return the currently active model."""
        return self.model_chain[self._current_model_index]

    @property
    def model(self) -> str:
        """Return the primary model (for backward compatibility)."""
        return self.model_chain[0]

    def get_stats(self) -> dict:
        """Get usage statistics for all models."""
        return {
            'model_usage': self._model_usage.copy(),
            'fallback_count': self._fallback_count,
            'active_model': self.active_model,
        }

    def transcribe(self, audio_data: bytes) -> Optional[str]:
        """Transcribe audio bytes (saved to temporary file)."""
        try:
            with tempfile.NamedTemporaryFile(suffix='.flac', delete=False) as temp_file:
                temp_path = temp_file.name
                temp_file.write(audio_data)

            result = self.transcribe_file(temp_path)

            try:
                os.unlink(temp_path)
            except OSError:
                pass

            return result

        except Exception as e:
            print(f"Transcription error: {e}")
            return None

    def transcribe_file(self, file_path: str) -> Optional[str]:
        """Transcribe audio file with fallback chain support."""
        for model_idx, model in enumerate(self.model_chain):
            self._current_model_index = model_idx

            for retry_attempt in range(self.max_retries):
                try:
                    result = self._try_transcribe(model, file_path)

                    self._model_usage[model] += 1
                    if model_idx > 0:
                        print(f"✓ Fallback transcription successful: {model}")
                    return result

                except Exception as e:
                    if should_fallback(e):
                        print(f"✗ Model {model} failed: {e}")
                        break
                    elif should_retry(e) and retry_attempt < self.max_retries - 1:
                        delay = retry_with_backoff(retry_attempt, self.retry_delay)
                        print(
                            f"✗ Model {model} failed: {e}\n"
                            f"Retry {retry_attempt + 1}/{self.max_retries} for {model} after {delay}s"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        print(f"✗ Model {model} failed: {e}")
                        break

            if model_idx < len(self.model_chain) - 1:
                next_model = self.model_chain[model_idx + 1]
                print(f"→ Falling back to: {next_model}")
                self._fallback_count += 1

        print("✗ All fallback transcription models exhausted")
        return None

    def _try_transcribe(self, model: str, file_path: str) -> str:
        """Attempt transcription for a specific model using LiteLLM."""
        with open(file_path, 'rb') as audio_file:
            kwargs = {
                'model': model,
                'file': audio_file,
                'temperature': self.temperature
            }

            if self.api_key:
                kwargs['api_key'] = self.api_key

            if self.base_url:
                kwargs['api_base'] = self.base_url

            if self.language and self.language != 'auto':
                kwargs['language'] = self.language

            response = self.litellm.transcription(**kwargs)
            self.last_usage = {**extract_usage(response), "cost": response_cost(response)}

        if isinstance(response, dict):
            return response.get('text', '')
        elif hasattr(response, 'text'):
            return response.text
        else:
            return str(response)

    @property
    def supports_streaming(self) -> bool:
        """Streaming transcription support."""
        return False

    def list_models(self):
        """Discover models from the configured endpoint when possible."""
        provider = str(getattr(self.config, "provider", "litellm"))
        return discover_models(self.base_url, self.api_key, provider)

    def health_check(self) -> None:
        """Validate models at startup."""
        if not self.api_key and not self.base_url:
            raise ValueError(
                "Nenhuma chave de API ou base_url local configurada para o serviço de transcrição.\n"
                "💡 Para usar o Groq (Gratuito e Ultra-rápido):\n"
                "   1. Obtenha a chave em: https://console.groq.com/keys\n"
                "   2. Adicione ao .env: GROQ_API_KEY=gsk_...\n"
                "💡 Para usar um servidor local (Ollama):\n"
                "   Configure base_url='http://localhost:11434/v1'"
            )

        print("Validando modelos de transcrição...")
        temp_path = None
        for model in self.model_chain:
            try:
                import wave
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                    temp_path = temp_file.name
                    with wave.open(temp_path, 'wb') as wav:
                        wav.setnchannels(1)
                        wav.setsampwidth(2)
                        wav.setframerate(16000)
                        wav.writeframes(b'\x00\x00' * 160)

                with open(temp_path, 'rb') as audio_file:
                    kwargs = {
                        'model': model,
                        'file': audio_file,
                    }
                    if self.api_key:
                        kwargs['api_key'] = self.api_key
                    if self.base_url:
                        kwargs['api_base'] = self.base_url

                    self.litellm.transcription(**kwargs)

                is_primary = model == self.model_chain[0]
                label = "Primary" if is_primary else "Fallback"
                print(f"✓ {label} model validated: {model}")

            except Exception as e:
                label = "Primary" if model == self.model_chain[0] else "Fallback"
                raise RuntimeError(
                    f"{label} model validation failed for {model}: {e}\n"
                    "💡 Verifique se a chave de API ou o servidor local (base_url) está ativo."
                )
            finally:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass

        print("✓ Serviço de transcrição pronto")
