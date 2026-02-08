# Core module exports
from .interfaces import (
    AbstractTranscriber,
    AbstractLLMProcessor,
    AbstractAudioInput,
    AbstractOutputHandler,
    AbstractKeyboardListener
)
try:
    from .implementations import (
        SoundDeviceInput,
        GroqTranscriber,
        LiteLLMProcessor,
        ConsoleOutputHandler,
        ClipboardOutputHandler,
        PyAutoGUIOutputHandler,
        AutoItOutputHandler,
        AppleScriptOutputHandler,
        XdotoolOutputHandler,
        KeyboardListener
    )
except ImportError:
    # Allow imports even if some implementations are missing
    pass
from .orchestrator import TranscriptionOrchestrator
from .factory import TranscriptionFactory, create_orchestrator

try:
    from .ui import TerminalUI
except ImportError:
    TerminalUI = None

__all__ = [
    # Interfaces
    "AbstractTranscriber",
    "AbstractLLMProcessor",
    "AbstractAudioInput",
    "AbstractOutputHandler",
    "AbstractKeyboardListener",
    # Implementations
    "SoundDeviceInput",
    "GroqTranscriber",
    "LiteLLMProcessor",
    "ConsoleOutputHandler",
    "ClipboardOutputHandler",
    "PyAutoGUIOutputHandler",
    "AutoItOutputHandler",
    "AppleScriptOutputHandler",
    "XdotoolOutputHandler",
    "KeyboardListener",
    # Core components
    "TranscriptionOrchestrator",
    "TerminalUI",
    "TranscriptionFactory",
    "create_orchestrator"
]
