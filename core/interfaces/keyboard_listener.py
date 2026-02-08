"""
Abstract Keyboard Listener Interface
Defines the contract for keyboard listener implementations.
"""

from abc import ABC, abstractmethod
from typing import Callable


class AbstractKeyboardListener(ABC):
    """Abstract base class for keyboard listeners."""
    
    @abstractmethod
    def start(self, on_press: Callable[[], None]) -> None:
        """
        Start listening for keyboard events.
        
        Args:
            on_press: Callback when hotkey is pressed
        """
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop listening for keyboard events."""
        pass
    
    # Properties
    @property
    @abstractmethod
    def is_running(self) -> bool:
        """Check if listener is running."""
        pass
    
    @property
    @abstractmethod
    def is_recording(self) -> bool:
        """Check if currently recording."""
        pass
    
    @property
    @abstractmethod
    def platform(self) -> str:
        """Get the platform name."""
        pass
    
    # Additional methods for compatibility
    @abstractmethod
    def register_hotkey(self, hotkey: str, callback: Callable) -> None:
        """Register a hotkey."""
        pass
    
    @abstractmethod
    def unregister_hotkey(self, hotkey: str) -> None:
        """Unregister a hotkey."""
        pass
