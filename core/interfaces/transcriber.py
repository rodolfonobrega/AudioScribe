"""
Abstract Transcriber Interface
Defines the contract for transcription services.
"""

from abc import ABC, abstractmethod
from typing import Optional


class AbstractTranscriber(ABC):
    """Abstract base class for transcription services."""
    
    @abstractmethod
    def transcribe(self, audio_data: bytes) -> Optional[str]:
        """
        Transcribe audio data.
        
        Args:
            audio_data: Audio data in WAV format
            
        Returns:
            Transcribed text, or None if transcription failed
        """
        pass
    
    @property
    @abstractmethod
    def supports_streaming(self) -> bool:
        """Check if streaming transcription is supported."""
        pass
    
    # Additional method for compatibility
    @abstractmethod
    def transcribe_file(self, file_path: str) -> Optional[str]:
        """
        Transcribe audio file.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Transcribed text, or None if transcription failed
        """
        pass

    def health_check(self) -> None:
        """
        Validate transcription service.
        Raises exception if validation fails.
        """
        pass
