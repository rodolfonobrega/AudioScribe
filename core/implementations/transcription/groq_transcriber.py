"""
Groq Transcriber Implementation (Legacy Wrapper around LiteLLMTranscriber).
Uses Groq's Whisper model for audio transcription via LiteLLM.
"""

from core.implementations.transcription.litellm_transcriber import LiteLLMTranscriber


class GroqTranscriber(LiteLLMTranscriber):
    """Transcriber implementation using Groq's Whisper model via LiteLLM."""

    def __init__(self, config):
        """
        Initialize Groq transcriber.

        Args:
            config: Transcription configuration
        """
        super().__init__(config)
        
        if not self.api_key and not self.base_url:
            raise ValueError(
                "Groq API key is required. Please set GROQ_API_KEY in your .env file or environment variables.\n"
                "💡 Obtain a free Groq API key at: https://console.groq.com/keys"
            )
