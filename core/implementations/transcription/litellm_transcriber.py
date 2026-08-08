"""
LiteLLM Universal Transcriber Implementation
Unified audio transcriber supporting 100+ AI providers (Groq, OpenAI, Google, Deepgram)
as well as local OpenAI-compatible endpoints (Ollama, LocalAI, vLLM via base_url).
"""

import os
import tempfile
import time
from typing import Optional, List, Dict

from core.utils.preflight import safe_print
from core.interfaces.transcriber import AbstractTranscriber
from core.utils.error_handler import should_retry, should_fallback, retry_with_backoff
from core.model_discovery import discover_models
from core.usage import extract_usage, response_cost, has_audio_data


class LiteLLMTranscriber(AbstractTranscriber):
    """Universal transcriber using LiteLLM for 100+ AI providers."""

    def __init__(self, config=None, api_key: Optional[str] = None,
                 base_url: Optional[str] = None):
        try:
            import litellm
            self.litellm = litellm
        except ImportError:
            raise ImportError(
                "LiteLLM is required. Install it with: pip install litellm"
            )

        self.config = config

        # Load from config if available
        if config:
            self._model = getattr(config, 'model', 'groq/whisper-large-v3-turbo')
            fallback_models = getattr(config, 'fallback_models', []) or []
            self.model_chain = [self._model] + list(fallback_models)
            self.max_retries = getattr(config, 'max_retries', 2)
            self.retry_delay = getattr(config, 'retry_delay', 1.0)
            self.api_key = api_key or getattr(config, 'api_key', None)
            self.base_url = base_url or getattr(config, 'base_url', None)
            self.temperature = getattr(config, 'temperature', 0.0)
            self.language = getattr(config, 'language', 'auto')
        else:
            self._model = 'groq/whisper-large-v3-turbo'
            self.model_chain = [self._model]
            self.max_retries = 2
            self.retry_delay = 1.0
            self.api_key = api_key
            self.base_url = base_url
            self.temperature = 0.0
            self.language = 'auto'

        # Track which model is currently active
        self._current_model_index = 0

        # Statistics tracking
        self._model_usage: Dict[str, int] = {}
        for m in self.model_chain:
            self._model_usage[m] = 0
        self._fallback_count = 0
        self.last_usage = None
        self.last_fallback_used = False

        if not self.model_chain:
            raise ValueError("At least one model must be configured for transcription.")

    @property
    def active_model(self) -> str:
        """Return the currently active model."""
        return self.model_chain[self._current_model_index]

    @property
    def model(self) -> str:
        """Return the primary model (for backward compatibility)."""
        return self.model_chain[0]

    @model.setter
    def model(self, value: str):
        self._model = value

    def get_stats(self) -> dict:
        """Get usage statistics for all models."""
        return {
            'model_usage': self._model_usage.copy(),
            'fallback_count': self._fallback_count,
        }

    def transcribe(self, audio_data: bytes, prompt: Optional[str] = None) -> Optional[str]:
        """Transcribe audio data, falling back through the model chain on failure."""
        if not has_audio_data(audio_data):
            return None

        # Write audio to temp file
        temp_path = None
        try:
            if isinstance(audio_data, bytes) and audio_data.startswith(b'OggS'):
                suffix = '.ogg'
            elif isinstance(audio_data, bytes) and audio_data[:4] == b'\x1a\x45\xdf\xa3':
                suffix = '.webm'
            else:
                suffix = '.wav'
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_path = temp_file.name

            result = self._transcribe_with_fallback(temp_path, prompt=prompt)
            return result
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def transcribe_with_vocabulary(self, audio_data: bytes, vocabulary: list[str]) -> Optional[str]:
        """Pass a bounded vocabulary hint to providers that support Whisper prompts."""
        terms = []
        seen = set()
        for term in vocabulary:
            value = str(term or "").strip()
            folded = value.casefold()
            if value and folded not in seen:
                seen.add(folded)
                terms.append(value)
            if len(terms) >= 100:
                break
        prompt = f"Vocabulary terms: {', '.join(terms)}" if terms else None
        return self.transcribe(audio_data, prompt=prompt)

    def _transcribe_with_fallback(self, file_path: str, prompt: Optional[str] = None) -> Optional[str]:
        """Try each model in chain with retry logic."""
        for model_idx, model in enumerate(self.model_chain):
            self._current_model_index = model_idx
            for retry_attempt in range(self.max_retries):
                try:
                    result = self._try_transcribe(model, file_path, prompt=prompt)

                    self._model_usage[model] += 1
                    if model_idx > 0:
                        self.last_fallback_used = True
                        safe_print(f"[OK] Fallback transcription successful: {model}")
                    return result

                except Exception as e:
                    if should_fallback(e):
                        safe_print(f"[X] Model {model} failed: {e}")
                        break
                    elif should_retry(e) and retry_attempt < self.max_retries - 1:
                        delay = retry_with_backoff(retry_attempt, self.retry_delay)
                        safe_print(
                            f"[X] Model {model} failed: {e}\n"
                            f"Retry {retry_attempt + 1}/{self.max_retries} for {model} after {delay}s"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        safe_print(f"[X] Model {model} failed: {e}")
                        break

            if model_idx < len(self.model_chain) - 1:
                next_model = self.model_chain[model_idx + 1]
                safe_print(f"-> Falling back to: {next_model}")
                self._fallback_count += 1

        safe_print("[X] All fallback transcription models exhausted")
        return None

    def _try_transcribe(self, model: str, file_path: str, prompt: Optional[str] = None) -> str:
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

            if prompt:
                kwargs['prompt'] = prompt

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

    def transcribe_file(self, file_path: str) -> Optional[str]:
        """Transcribe audio from a file path."""
        with open(file_path, 'rb') as f:
            audio_data = f.read()
        return self.transcribe(audio_data)

    def list_models(self):
        """Discover models from the configured endpoint when possible."""
        provider = str(getattr(self.config, "provider", "litellm"))
        return discover_models(self.base_url, self.api_key, provider)

    def health_check(self) -> None:
        """Validate models at startup."""
        if not self.api_key and not self.base_url:
            raise ValueError(
                "Nenhuma chave de API ou base_url local configurada para o servico de transcricao.\n"
                "Para usar o Groq (Gratuito e Ultra-rapido):\n"
                "   1. Obtenha a chave em: https://console.groq.com/keys\n"
                "   2. Adicione ao .env: GROQ_API_KEY=gsk_...\n"
                "Para usar um servidor local (Ollama):\n"
                "   Configure base_url='http://localhost:11434/v1'"
            )

        safe_print("Validando modelos de transcricao...")
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
                safe_print(f"[OK] {label} model validated: {model}")

            except Exception as e:
                label = "Primary" if model == self.model_chain[0] else "Fallback"
                raise RuntimeError(
                    f"{label} model validation failed for {model}: {e}\n"
                    "Verifique se a chave de API ou o servidor local (base_url) esta ativo."
                )
            finally:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass

        safe_print("[OK] Servico de transcricao pronto")
