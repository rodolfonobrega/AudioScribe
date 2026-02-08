"""
Abstract LLM Processor Interface
Defines the contract for LLM text processors.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict


class AbstractLLMProcessor(ABC):
    """Abstract base class for LLM text processors."""
    
    @abstractmethod
    def process(self, text: str) -> Optional[str]:
        """
        Process text with LLM.
        
        Args:
            text: Input text to process
            
        Returns:
            Processed text, or None if processing failed
        """
        pass
    
    # Additional method for compatibility
    @abstractmethod
    def process_with_history(self, text: str, history: List[Dict[str, str]]) -> Optional[str]:
        """
        Process text with conversation history.
        
        Args:
            text: Input text to process
            history: Conversation history
            
        Returns:
            Processed text, or None if processing failed
        """
        pass

    def health_check(self) -> None:
        """
        Validate LLM processor.
        Raises exception if validation fails.
        """
        pass
