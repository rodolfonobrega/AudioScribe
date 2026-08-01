# YAML Configuration for Multiple Providers (Different Implementations)

## Option 1: Configuration by Section (Recommended)

```yaml
# config/defaults.yaml

# Primary configuration (LiteLLM)
transcription:
  provider: litellm
  model: groq/whisper-large-v3-turbo
  fallback_models: []  # Empty, we'll use different implementations
  max_retries: 2
  retry_delay: 1.0
  api_key: ${GROQ_API_KEY}
  language: auto

# Configuration for fallback 1 (Whisper native)
transcription_fallback_1:
  provider: whisper_native
  enabled: true
  model_size: base  # tiny, base, small, medium, large
  device: cpu
  language: null

# Configuration for fallback 2 (Vosk local)
transcription_fallback_2:
  provider: vosk
  enabled: false  # Disabled for now
  model_path: /path/to/vosk/model
  language: pt-BR

# Fallback order
transcription_fallback_order:
  - transcription      # Primary
  - transcription_fallback_1
  - transcription_fallback_2
```

And in the code:

```python
# core/factory.py (updated method)

@staticmethod
def create_transcriber_with_mixed_providers(config: Config):
    """
    Create transcriber with fallback between different implementations
    based on YAML configuration.
    """
    from core.implementations.transcription.groq_transcriber import GroqTranscriber
    from core.implementations.transcription.whisper_native import (
        WhisperNativeTranscriber,
        WhisperNativeConfig
    )
    # from core.implementations.transcription.vosk_transcriber import VoskTranscriber

    transcribers = []
    fallback_order = getattr(config, 'transcription_fallback_order', ['transcription'])

    for section_name in fallback_order:
        section_config = getattr(config, section_name, None)

        if not section_config:
            continue

        provider = section_config.get('provider')

        # Primary section (LiteLLM)
        if provider == 'litellm' or section_name == 'transcription':
            transcribers.append(GroqTranscriber(config.transcription))

        # Whisper native
        elif provider == 'whisper_native' and section_config.get('enabled'):
            whisper_config = WhisperNativeConfig(
                model_size=section_config.get('model_size', 'base'),
                device=section_config.get('device', 'cpu'),
                language=section_config.get('language')
            )
            transcribers.append(WhisperNativeTranscriber(whisper_config))

        # Vosk
        elif provider == 'vosk' and section_config.get('enabled'):
            # vosk_config = VoskConfig(...)
            # transcribers.append(VoskTranscriber(vosk_config))
            pass

    # If there are multiple transcribers, create chain
    if len(transcribers) > 1:
        return TranscriptionFactory.create_transcriber_chain(transcribers)

    # Otherwise, return only the primary
    return transcribers[0] if transcribers else None
```

## Option 2: List of Configurations (More Compact)

```yaml
# config/defaults.yaml

transcription_chain:
  - provider: litellm
    model: groq/whisper-large-v3-turbo
    api_key: ${GROQ_API_KEY}
    max_retries: 2
    retry_delay: 1.0
    language: auto

  - provider: whisper_native
    model_size: base
    device: cpu
    language: null

  - provider: vosk
    enabled: false
    model_path: /path/to/model
    language: pt-BR
```

And in the code:

```python
# core/factory.py

@staticmethod
def create_transcriber_from_chain(config: Config):
    """Create transcriber from list of configurations."""
    transcribers = []
    chain_configs = getattr(config, 'transcription_chain', None)

    if not chain_configs:
        # Fallback to old configuration
        return GroqTranscriber(config.transcription)

    for chain_config in chain_configs:
        provider = chain_config.get('provider')

        if provider == 'litellm':
            # Create temporary config
            from config.settings import TranscriptionConfig
            temp_config = TranscriptionConfig(**chain_config)
            transcribers.append(GroqTranscriber(temp_config))

        elif provider == 'whisper_native':
            from core.implementations.transcription.whisper_native import (
                WhisperNativeTranscriber,
                WhisperNativeConfig
            )
            whisper_config = WhisperNativeConfig(
                model_size=chain_config.get('model_size', 'base'),
                device=chain_config.get('device', 'cpu'),
                language=chain_config.get('language')
            )
            transcribers.append(WhisperNativeTranscriber(whisper_config))

    if len(transcribers) > 1:
        return TranscriptionFactory.create_transcriber_chain(transcribers)

    return transcribers[0] if transcribers else None
```

## Option 3: Simplified Configuration (Easiest)

```yaml
# config/defaults.yaml

# Primary transcription
transcription:
  model: groq/whisper-large-v3-turbo
  api_key: ${GROQ_API_KEY}
  fallback_models:
    - openai/whisper-1    # LiteLLM fallback

# Enable fallback to Whisper native?
use_whisper_native_fallback: false
whisper_native:
  model_size: base
  device: cpu

# Enable fallback to Vosk?
use_vosk_fallback: false
vosk:
  model_path: /path/to/model
```

```python
# main.py

config = load_config()

transcribers = [GroqTranscriber(config.transcription)]

# Add fallbacks if enabled
if getattr(config, 'use_whisper_native_fallback', False):
    whisper = WhisperNativeTranscriber(config.whisper_native)
    transcribers.append(whisper)

if getattr(config, 'use_vosk_fallback', False):
    vosk = VoskTranscriber(config.vosk)
    transcribers.append(vosk)

# Create chain if there are multiple
if len(transcribers) > 1:
    transcriber = create_transcriber_chain(transcribers)
else:
    transcriber = transcribers[0]
```

## Recommendation

**For starting out**, use **Option 1** (separate sections). It's clearer and easier to maintain:

✓ **Advantages:**
- Easy to understand each section
- Can disable fallbacks individually
- Explicit order

**When your application grows**, you can refactor to **Option 2** (compact list).
