"""
Abstract Audio Input Interface
Defines the contract for audio input implementations.
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional, List, Dict, Any


class AbstractAudioInput(ABC):
    """Abstract base class for audio input implementations."""
    
    @abstractmethod
    def start_recording(self) -> None:
        """Start recording audio."""
        pass
    
    @abstractmethod
    def stop_recording(self) -> bytes:
        """
        Stop recording and return audio data.
        
        Returns:
            Raw audio data as bytes
        """
        pass
    
    @abstractmethod
    def list_devices(self) -> List[Dict[str, Any]]:
        """
        List available audio input devices.
        
        Returns:
            List of device information dictionaries
        """
        pass
    
    # Properties to maintain compatibility
    @property
    @abstractmethod
    def is_recording(self) -> bool:
        """Check if currently recording."""
        pass
    
    @property
    @abstractmethod
    def sample_rate(self) -> int:
        """Sample rate in Hz."""
        pass
    
    @property
    @abstractmethod
    def channels(self) -> int:
        """Number of audio channels."""
        pass
    
    @abstractmethod
    def get_device_list(self) -> List[Dict[str, Any]]:
        """Alias for list_devices() for backward compatibility."""
        return self.list_devices()
    
    @abstractmethod
    def set_device(self, device_index: int) -> None:
        """Set the audio input device."""
        pass

    def health_check(self) -> None:
        """
        Validate audio input device.
        Raises exception if validation fails.
        """
        pass
