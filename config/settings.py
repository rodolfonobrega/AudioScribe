"""
Configuration Manager - Type-safe configuration management.
Handles YAML configs, environment variables, and CLI overrides.
"""

import os
from typing import Optional, List
from pathlib import Path
from dataclasses import dataclass, field
import yaml


@dataclass
class AudioConfig:
    """Audio input configuration."""
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024
    device_index: Optional[int] = None
    dtype: str = "float32"
    min_duration: float = 0.5


@dataclass
class TranscriptionConfig:
    """Transcription service configuration."""
    provider: str = "litellm"
    model: str = "groq/whisper-large-v3-turbo"
    fallback_models: List[str] = field(default_factory=list)
    max_retries: int = 2
    retry_delay: float = 1.0
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    language: str = "auto"
    temperature: float = 0.0

    @property
    def model_chain(self) -> List[str]:
        """Return the full model chain including fallbacks."""
        return [self.model] + self.fallback_models


@dataclass
class LLMConfig:
    """LLM processor configuration."""
    provider: str = "litellm"
    model: str = "groq/meta-llama/llama-4-maverick-17b-128e-instruct"
    fallback_models: List[str] = field(default_factory=list)
    max_retries: int = 2
    retry_delay: float = 1.0
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 1000
    system_prompt: Optional[str] = None
    enabled: bool = True

    @property
    def model_chain(self) -> List[str]:
        """Return the full model chain including fallbacks."""
        return [self.model] + self.fallback_models


@dataclass
class OutputConfig:
    """Output handler configuration."""
    handlers: List[str] = field(default_factory=lambda: ["stdout"])
    file_path: Optional[str] = None
    file_mode: str = "a"
    verbose: bool = True
    output_file: Optional[str] = None  # For FileOutputHandler


@dataclass
class KeyboardConfig:
    """Keyboard listener configuration."""
    enabled: bool = True
    hotkey: str = "f9"
    mode: str = "push_to_talk"
    verbose: bool = True


@dataclass
class OrchestratorConfig:
    """Orchestrator configuration."""
    verbose: bool = True
    log_level: str = "INFO"
    debug: bool = False


@dataclass
class Config:
    """Main configuration container."""
    audio: AudioConfig = field(default_factory=AudioConfig)
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    llm: Optional[LLMConfig] = None
    output: OutputConfig = field(default_factory=OutputConfig)
    keyboard: KeyboardConfig = field(default_factory=KeyboardConfig)
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)

    def __post_init__(self):
        """Initialize LLM config if not provided."""
        if self.llm is None:
            self.llm = LLMConfig()


def load_config(path: Optional[str] = None, use_env: bool = False, **kwargs) -> Config:
    """
    Load configuration from YAML file, environment variables, and overrides.

    Args:
        path: Optional path to YAML configuration file
        use_env: If True, load configuration from environment variables
        **kwargs: Additional configuration overrides

    Returns:
        Fully configured Config object

    Examples:
        >>> config = load_config(use_env=True)
        >>> config = load_config(path="config.yaml")
        >>> config = load_config(transcription_model="custom-model")
    """
    # Start with defaults
    config = Config()

    # Determine config path if not provided
    if path is None:
        possible_paths = [
            Path("config/defaults.yaml"),
            Path("defaults.yaml"),
            Path(__file__).parent / "defaults.yaml"
        ]
        for p in possible_paths:
            if p.exists():
                path = str(p)
                break

    # Load from YAML file if provided
    if path:
        config_path = Path(path)
        if config_path.exists():
            with open(config_path, 'r') as f:
                yaml_config = yaml.safe_load(f) or {}

            # Helper to substitute env vars in strings
            def substitute_env_vars(item):
                if isinstance(item, dict):
                    return {k: substitute_env_vars(v) for k, v in item.items()}
                elif isinstance(item, list):
                    return [substitute_env_vars(i) for i in item]
                elif isinstance(item, str):
                    # Use os.path.expandvars to handle ${VAR}
                    return os.path.expandvars(item)
                else:
                    return item

            yaml_config = substitute_env_vars(yaml_config)

            # Update configs from YAML
            if 'audio' in yaml_config:
                config.audio = AudioConfig(**yaml_config['audio'])
            if 'transcription' in yaml_config:
                config.transcription = TranscriptionConfig(**yaml_config['transcription'])
            if 'llm' in yaml_config:
                config.llm = LLMConfig(**yaml_config['llm'])
            if 'output' in yaml_config:
                config.output = OutputConfig(**yaml_config['output'])
            if 'keyboard' in yaml_config:
                config.keyboard = KeyboardConfig(**yaml_config['keyboard'])
            if 'orchestrator' in yaml_config:
                config.orchestrator = OrchestratorConfig(**yaml_config['orchestrator'])

    # Load from environment variables if requested
    if use_env:
        # Audio settings
        config.audio.sample_rate = int(os.getenv('AUDIO_SAMPLE_RATE', config.audio.sample_rate))
        config.audio.channels = int(os.getenv('AUDIO_CHANNELS', config.audio.channels))

        # Transcription settings
        config.transcription.provider = os.getenv('TRANSCRIPTION_PROVIDER', config.transcription.provider)
        transcription_model = os.getenv('TRANSCRIPTION_MODEL', config.transcription.model)
        if ',' in transcription_model:
            models = [m.strip() for m in transcription_model.split(',')]
            config.transcription.model = models[0]
            config.transcription.fallback_models = models[1:]
        else:
            config.transcription.model = transcription_model
        config.transcription.max_retries = int(os.getenv(
            'TRANSCRIPTION_MAX_RETRIES', str(config.transcription.max_retries)))
        config.transcription.retry_delay = float(os.getenv(
            'TRANSCRIPTION_RETRY_DELAY', str(config.transcription.retry_delay)))
        config.transcription.api_key = os.getenv(
            'TRANSCRIPTION_API_KEY', config.transcription.api_key) or os.getenv('GROQ_API_KEY')
        config.transcription.base_url = os.getenv('TRANSCRIPTION_BASE_URL', config.transcription.base_url)
        config.transcription.language = os.getenv('TRANSCRIPTION_LANGUAGE', config.transcription.language)

        # LLM settings
        if config.llm:
            config.llm.provider = os.getenv('LLM_PROVIDER', config.llm.provider)
            llm_model = os.getenv('LLM_MODEL', config.llm.model)
            if ',' in llm_model:
                models = [m.strip() for m in llm_model.split(',')]
                config.llm.model = models[0]
                config.llm.fallback_models = models[1:]
            else:
                config.llm.model = llm_model
            config.llm.max_retries = int(os.getenv('LLM_MAX_RETRIES', str(config.llm.max_retries)))
            config.llm.retry_delay = float(os.getenv('LLM_RETRY_DELAY', str(config.llm.retry_delay)))
            config.llm.api_key = os.getenv('LLM_API_KEY', config.llm.api_key) or os.getenv('LITELLM_API_KEY')
            config.llm.base_url = os.getenv('LLM_BASE_URL', config.llm.base_url)

        # Keyboard settings
        config.keyboard.hotkey = os.getenv('KEYBOARD_HOTKEY', config.keyboard.hotkey)
        config.keyboard.mode = os.getenv('KEYBOARD_MODE', config.keyboard.mode)

        # Output settings
        handlers_str = os.getenv('OUTPUT_HANDLERS')
        if handlers_str:
            config.output.handlers = [h.strip() for h in handlers_str.split(',')]

    # Apply kwargs overrides
    for key, value in kwargs.items():
        if hasattr(config, key):
            # Check if we should update a nested config object or overwrite
            current_val = getattr(config, key)
            if isinstance(value, dict) and current_val is not None and not isinstance(current_val, dict):
                # It's a nested config object (likely a dataclass), update its fields
                for sub_key, sub_val in value.items():
                    if hasattr(current_val, sub_key):
                        setattr(current_val, sub_key, sub_val)
            else:
                # Simple overwrite
                setattr(config, key, value)

    # Handle specific nested overrides logic is now redundant if we handle it generically above,
    # but let's keep specific handling if it does something special or just rely on the generic loop.
    # The generic loop above covers 'audio', 'transcription', 'llm', etc. if they are passed as dicts.
    # The existing specific blocks below (lines 164-178 in original) can be removed or left as fallback
    # if they were doing something else, but they look like simple updates.
    # We can remove them to clean up.

    return config
