"""
Component Factory - Creates configured components.
Simplifies component instantiation and dependency injection.
"""

import platform
from typing import Optional

from config.settings import Config
from core.implementations.audio.sounddevice_input import SoundDeviceInput
from core.implementations.transcription.groq_transcriber import GroqTranscriber
from core.implementations.llm.litellm_processor import LiteLLMProcessor
from core.implementations.output.output_handlers import (
    ConsoleOutputHandler,
    ClipboardOutputHandler,
    PyAutoGUIOutputHandler,
    AutoItOutputHandler,
    AppleScriptOutputHandler,
    XdotoolOutputHandler
)
from core.implementations.keyboard.keyboard_listener import KeyboardListener
from core.orchestrator import TranscriptionOrchestrator


class TranscriptionFactory:
    """
    Factory for creating transcription components.
    
    Benefits:
    - Centralized component creation
    - Type-safe configuration
    - Platform-specific handling
    """

    @staticmethod
    def create_audio_input(config: Config):
        """Create audio input component."""
        return SoundDeviceInput(config.audio)

    @staticmethod
    def create_transcriber(config: Config):
        """Create transcriber component."""
        return GroqTranscriber(config.transcription)

    @staticmethod
    def create_llm_processor(config: Config):
        """Create LLM processor component."""
        return LiteLLMProcessor(config.llm)

    @staticmethod
    def create_output_handlers(config: Config):
        """
        Create output handler components based on config.
        
        Returns list of output handlers.
        """
        handlers = []
        
        # Iterate over configured handlers (list of strings)
        # Defaults to ["stdout"] if not specified in config
        for handler_type in config.output.handlers:
            handler_type = handler_type.lower().strip()
            
            if handler_type in ["console", "stdout"]:
                handlers.append(ConsoleOutputHandler(config.output))
            elif handler_type == "clipboard":
                handlers.append(ClipboardOutputHandler(config.output))
            elif handler_type == "pyautogui":
                handlers.append(PyAutoGUIOutputHandler(config.output))
            elif handler_type == "autoit" and platform.system() == "Windows":
                handlers.append(AutoItOutputHandler(config.output))
            elif handler_type == "applescript" and platform.system() == "Darwin":
                handlers.append(AppleScriptOutputHandler(config.output))
            elif handler_type == "xdotool" and platform.system() == "Linux":
                handlers.append(XdotoolOutputHandler(config.output))
        
        # If no handlers created (e.g. empty list or invalid types), fallback to console
        if not handlers:
            handlers.append(ConsoleOutputHandler(config.output))
            
        return handlers

    @staticmethod
    def create_keyboard_listener(config: Config):
        """Create keyboard listener component."""
        return KeyboardListener(config.keyboard)

    @staticmethod
    def create_orchestrator(
        config: Config,
        audio_input=None,
        transcriber=None,
        llm_processor=None,
        output_handlers=None,
        keyboard_listener=None,
        ui=None
    ) -> TranscriptionOrchestrator:
        """
        Create fully configured orchestrator.
        
        Args:
            config: Configuration object
            audio_input: Optional custom audio input
            transcriber: Optional custom transcriber
            llm_processor: Optional custom LLM processor
            output_handlers: Optional custom output handlers (list)
            keyboard_listener: Optional custom keyboard listener
            ui: Optional UI instance
            
        Returns:
            Configured TranscriptionOrchestrator instance
        """
        # Create components if not provided
        if audio_input is None:
            audio_input = TranscriptionFactory.create_audio_input(config)
        
        if transcriber is None:
            transcriber = TranscriptionFactory.create_transcriber(config)
        
        if llm_processor is None and config.llm.enabled:
            llm_processor = TranscriptionFactory.create_llm_processor(config)
        
        # Output handler - use first one if multiple
        output_handler = None
        if output_handlers is None:
            handlers = TranscriptionFactory.create_output_handlers(config)
            output_handler = handlers[0] if handlers else None
        elif isinstance(output_handlers, list) and len(output_handlers) > 0:
            output_handler = output_handlers[0]
        
        if keyboard_listener is None:
            keyboard_listener = TranscriptionFactory.create_keyboard_listener(config)
        
        return TranscriptionOrchestrator(
            audio_input=audio_input,
            transcriber=transcriber,
            llm_processor=llm_processor,
            output_handler=output_handler,
            keyboard_listener=keyboard_listener,
            ui=ui
        )


def create_orchestrator(
    config_path: Optional[str] = None,
    use_env: bool = False,
    **kwargs
) -> TranscriptionOrchestrator:
    """
    Convenience function to create orchestrator.
    
    Args:
        config_path: Optional path to YAML config file
        use_env: If True, load config from environment variables
        **kwargs: Additional config overrides
        
    Returns:
        Configured TranscriptionOrchestrator instance
        
    Examples:
        >>> orchestrator = create_orchestrator(use_env=True)
        >>> orchestrator.start()
        
        >>> orchestrator = create_orchestrator(
        ...     config_path="config.yaml",
        ...     transcription_model="groq/whisper-large-v3"
        ... )
    """
    from config.settings import load_config
    
    config = load_config(path=config_path, use_env=use_env, **kwargs)
    return TranscriptionFactory.create_orchestrator(config)
