"""
AudioScribe - A modular, cross-platform audio transcription system with LLM processing.
"""

__version__ = "2.0.0"
__author__ = "Rodolfo"
__email__ = "rodolfonobregar@gmail.com"

# Core exports
from core.orchestrator import TranscriptionOrchestrator
from core.factory import TranscriptionFactory, create_orchestrator

# Interfaces
from core.interfaces.audio_input import AbstractAudioInput
from core.interfaces.transcriber import AbstractTranscriber
from core.interfaces.llm_processor import AbstractLLMProcessor
from core.interfaces.output_handler import AbstractOutputHandler
from core.interfaces.keyboard_listener import AbstractKeyboardListener

# Implementations
from core.implementations.audio.sounddevice_input import SoundDeviceAudioInput
from core.implementations.transcription.groq_transcriber import GroqTranscriber
from core.implementations.llm.litellm_processor import LiteLLMProcessor
from core.implementations.output.output_handlers import (
    ClipboardOutputHandler,
    FileOutputHandler,
    StdoutOutputHandler,
    AutoItOutputHandler,
    AppleScriptOutputHandler,
    XdotoolOutputHandler
)
from core.implementations.keyboard.keyboard_listener import KeyboardListener, InteractionMode

# Config
from config.settings import Config, load_config

__all__ = [
    # Version
    "__version__",
    
    # Main
    "TranscriptionOrchestrator",
    "TranscriptionFactory",
    "create_orchestrator",
    
    # Interfaces
    "AbstractAudioInput",
    "AbstractTranscriber",
    "AbstractLLMProcessor",
    "AbstractOutputHandler",
    "AbstractKeyboardListener",
    
    # Implementations
    "SoundDeviceAudioInput",
    "GroqTranscriber",
    "LiteLLMProcessor",
    "ClipboardOutputHandler",
    "FileOutputHandler",
    "StdoutOutputHandler",
    "AutoItOutputHandler",
    "AppleScriptOutputHandler",
    "XdotoolOutputHandler",
    "KeyboardListener",
    "InteractionMode",
    
    # Config
    "Config",
    "load_config",
]
