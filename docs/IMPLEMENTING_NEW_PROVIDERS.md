# Implementing New Providers - Guide

This guide shows how to add new transcription/LLM providers that **don't use LiteLLM** and configure them to work with the fallback system.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│              FallbackTranscriber / FallbackLLMProcessor  │
│              (manages fallback between implementations)  │
└─────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │ Groq     │    │ Whisper  │    │ Vosk     │
    │ (LiteLLM)│    │ Native   │    │ Local    │
    └──────────┘    └──────────┘    └──────────┘
```

## Step 1: Create the New Implementation

Create a class that implements the `AbstractTranscriber` or `AbstractLLMProcessor` interface.

### Example: Whisper Native Transcriber

```python
# core/implementations/transcription/whisper_native.py

import os
from typing import Optional
from core.interfaces.transcriber import AbstractTranscriber
from dataclasses import dataclass


@dataclass
class WhisperNativeConfig:
    """Configuration for native Whisper (OpenAI)."""
    model_size: str = "base"  # tiny, base, small, medium, large
    device: str = "cpu"  # cpu, cuda
    language: Optional[str] = None


class WhisperNativeTranscriber(AbstractTranscriber):
    """Transcriber using native Whisper (non-LiteLLM)."""

    def __init__(self, config: WhisperNativeConfig):
        self.config = config

        # Import whisper (install with: pip install openai-whisper)
        try:
            import whisper
            self.whisper = whisper
        except ImportError:
            raise ImportError(
                "whisper is required. Install with: pip install openai-whisper"
            )

        # Load model
        print(f"Loading Whisper model: {config.model_size}...")
        self.model = self.whisper.load_model(config.model_size, device=config.device)
        print(f"Whisper model loaded successfully")

    def transcribe(self, audio_data: bytes) -> Optional[str]:
        """Transcribe audio data using native Whisper."""
        import tempfile

        try:
            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_path = f.name
                f.write(audio_data)

            # Transcribe
            result = self.transcribe_file(temp_path)

            # Cleanup
            try:
                os.unlink(temp_path)
            except OSError:
                pass

            return result

        except Exception as e:
            print(f"Whisper native transcription error: {e}")
            return None

    def transcribe_file(self, file_path: str) -> Optional[str]:
        """Transcribe audio file using native Whisper."""
        try:
            # Transcribe with options
            options = {
                'fp16': False,  # Use FP32 for compatibility
            }

            if self.config.language:
                options['language'] = self.config.language

            result = self.model.transcribe(file_path, **options)
            return result.get('text', '').strip()

        except Exception as e:
            print(f"Whisper native file transcription error: {e}")
            return None

    @property
    def supports_streaming(self) -> bool:
        """Native Whisper doesn't support streaming."""
        return False

    def health_check(self) -> None:
        """Validate that the model is loaded."""
        if self.model is None:
            raise RuntimeError("Whisper model not loaded")
        print("[OK] Whisper native transcriber ready")
```

## Step 2: Add Configuration

```yaml
# config/defaults.yaml

# Configuration for native Whisper (separate from LiteLLM)
whisper_native:
  model_size: base       # tiny, base, small, medium, large
  device: cpu            # cpu or cuda
  language: null         # null = auto-detect
```

## Step 3: Use in Factory

### Option A: Use FallbackTranscriber (Recommended for Multi-Provider)

```python
# In your main code or in a custom factory

from core.factory import TranscriptionFactory
from core.implementations.transcription.groq_transcriber import GroqTranscriber
from core.implementations.transcription.whisper_native import (
    WhisperNativeTranscriber,
    WhisperNativeConfig
)
from config.settings import load_config

# Load configuration
config = load_config(use_env=True)

# Create Groq transcriber (primary)
groq_transcriber = GroqTranscriber(config.transcription)

# Create native Whisper transcriber (fallback)
whisper_config = WhisperNativeConfig(
    model_size="base",
    device="cpu"
)
whisper_transcriber = WhisperNativeTranscriber(whisper_config)

# Create chain with fallback
transcriber = TranscriptionFactory.create_transcriber_chain(
    transcribers=[groq_transcriber, whisper_transcriber],
    max_retries=2,
    retry_delay=1.0
)

# Use in orchestrator
orchestrator = TranscriptionFactory.create_orchestrator(
    config=config,
    transcriber=transcriber  # Pass the chain
)
```

### Option B: Dynamic Configuration

```python
# Extended factory.py

class ExtendedTranscriptionFactory(TranscriptionFactory):

    @staticmethod
    def create_transcriber_with_fallback(config: Config):
        """
        Create transcriber with automatic fallback based on configuration.

        If the configuration has 'fallback_implementations', creates multiple
        implementations and chains them with FallbackTranscriber.
        """
        from core.implementations.transcription.whisper_native import (
            WhisperNativeTranscriber,
            WhisperNativeConfig
        )

        transcribers = []

        # Primary: always Groq (LiteLLM)
        transcribers.append(GroqTranscriber(config.transcription))

        # Fallbacks: check additional configuration
        if hasattr(config, 'whisper_native') and config.whisper_native:
            whisper_config = WhisperNativeConfig(
                model_size=getattr(config.whisper_native, 'model_size', 'base'),
                device=getattr(config.whisper_native, 'device', 'cpu'),
                language=getattr(config.whisper_native, 'language', None)
            )
            transcribers.append(WhisperNativeTranscriber(whisper_config))

        # If there are multiple transcribers, create chain
        if len(transcribers) > 1:
            return TranscriptionFactory.create_transcriber_chain(transcribers)

        # Otherwise, return only the primary
        return transcribers[0]
```

## Step 4: Configuration via YAML

```yaml
# config/defaults.yaml

transcription:
  provider: litellm
  model: groq/whisper-large-v3-turbo
  fallback_models:
    - openai/whisper-1    # Fallback via LiteLLM
  max_retries: 2
  retry_delay: 1.0

# Configuration for fallback via native implementation
whisper_native:
  enabled: true
  model_size: base
  device: cpu
  language: null
```

## Complete Example: main.py

```python
# main.py

from core.factory import TranscriptionFactory
from core.implementations.transcription.groq_transcriber import GroqTranscriber
from core.implementations.transcription.whisper_native import (
    WhisperNativeTranscriber,
    WhisperNativeConfig
)
from config.settings import load_config

def main():
    # Load configuration
    config = load_config(use_env=True)

    # Create transcribers
    transcribers = []

    # Primary: Groq via LiteLLM
    transcribers.append(GroqTranscriber(config.transcription))

    # Fallback: Native local Whisper
    whisper_config = WhisperNativeConfig(model_size="base", device="cpu")
    transcribers.append(WhisperNativeTranscriber(whisper_config))

    # Create chain with fallback
    transcriber = TranscriptionFactory.create_transcriber_chain(
        transcribers=transcribers,
        max_retries=2,
        retry_delay=1.0
    )

    # Create orchestrator with the transcriber chain
    orchestrator = TranscriptionFactory.create_orchestrator(
        config=config,
        transcriber=transcriber
    )

    # Health check will validate ALL transcribers
    print("Running health checks...")
    transcriber.health_check()

    # Start
    orchestrator.start()

if __name__ == "__main__":
    main()
```

## Expected Output

```bash
Running health checks...
Validating transcriber chain...
[OK] Primary transcriber validated: GroqTranscriber
[OK] Fallback transcriber validated: WhisperNativeTranscriber
[OK] Transcriber chain ready

[During use, if Groq fails]
[ERROR] GroqTranscriber failed: Rate limit exceeded
[Falling back to: WhisperNativeTranscriber]
[OK] Fallback successful: WhisperNativeTranscriber
```

## Advantages of This Architecture

1. **Decoupling**: Each implementation is independent
2. **Extensibility**: Adding new providers doesn't affect existing ones
3. **Flexibility**: Mix LiteLLM, native, local, cloud, etc.
4. **Maintainability**: Each provider has its own code
5. **Testability**: Easy to test each implementation separately

## Summary

- **LiteLLM models** (groq/, openai/, etc): Use `GroqTranscriber` with `model_chain`
- **Different implementations** (Groq + native Whisper + Vosk): Use `FallbackTranscriber`
- **Your choice**: Based on what you need (performance, cost, privacy, etc.)
