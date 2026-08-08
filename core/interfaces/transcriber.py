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

    def transcribe_with_vocabulary(self, audio_data: bytes, vocabulary: list[str]) -> Optional[str]:
        """Transcribe with optional vocabulary hints when the backend supports it.

        Implementations that do not support hints retain the normal
        transcription behaviour instead of silently changing the request.
        """
        return self.transcribe(audio_data)
    
    @property
    @abstractmethod
    def supports_streaming(self) -> bool:
        """Check if streaming transcription is supported."""
        pass
    
    # Additional method for compatibility
    def transcribe_file(self, file_path: str) -> Optional[str]:
        """
        Transcribe audio file.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Transcribed text, or None if transcription failed
        """
        try:
            with open(file_path, "rb") as f:
                return self.transcribe(f.read())
        except Exception:
            return None

    def health_check(self) -> None:
        """
        Validate transcription service.
        Raises exception if validation fails.
        """
        pass
