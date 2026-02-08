"""
Abstract Output Handler Interface
Defines the contract for output handler implementations.
"""

from abc import ABC, abstractmethod
from typing import List, Optional


class AbstractOutputHandler(ABC):
    """Abstract base class for output handlers."""
    
    @abstractmethod
    def output(self, text: str, **kwargs) -> None:
        """
        Output text.
        
        Args:
            text: Text to output
            **kwargs: Additional output-specific parameters
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if handler is available on current platform.
        
        Returns:
            True if available, False otherwise
        """
        pass
    
    # Property for compatibility
    @property
    @abstractmethod
    def platform(self) -> str:
        """Get the platform name."""
        pass
    
    @property
    @abstractmethod
    def supported_platforms(self) -> List[str]:
        """Get list of supported platforms."""
        pass
