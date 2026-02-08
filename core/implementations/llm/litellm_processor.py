"""
LiteLLM Processor Implementation
Uses LiteLLM for flexible LLM provider support.
"""

import os
from typing import Optional, List, Dict

from core.interfaces.llm_processor import AbstractLLMProcessor


class LiteLLMProcessor(AbstractLLMProcessor):
    """LLM processor implementation using LiteLLM."""
    
    def __init__(self, config):
        """
        Initialize LiteLLM processor.
        
        Args:
            config: LLM configuration
        """
        self.config = config
        self.api_key = config.api_key
        self.model = config.model
        self.base_url = getattr(config, 'base_url', None)
        self.temperature = config.temperature
        self.max_tokens = config.max_tokens
        self.system_prompt = config.system_prompt
        
        # Import litellm
        try:
            import litellm
            self.litellm = litellm
        except ImportError:
            raise ImportError("litellm is required. Install with: pip install litellm")

    def process(self, text: str) -> Optional[str]:
        """
        Process text with LLM.
        
        Args:
            text: Input text to process
            
        Returns:
            Processed text, or None if processing failed
        """
        try:
            messages = []
            
            # Add system prompt if configured
            if self.system_prompt:
                messages.append({"content": self.system_prompt, "role": "system"})
            
            # Add user message
            messages.append({"content": text, "role": "user"})
            
            # Prepare completion parameters
            kwargs = {
                'model': self.model,
                'messages': messages,
                'temperature': self.temperature,
                'max_tokens': self.max_tokens
            }
            
            # Add API key if provided
            if self.api_key:
                kwargs['api_key'] = self.api_key

            # Add base_url if provided
            if self.base_url:
                kwargs['base_url'] = self.base_url
            
            # Call litellm directly (blocking call)
            response = self.litellm.completion(**kwargs)
            
            # Extract text from response
            if hasattr(response, 'choices'):
                return response.choices[0].message.content
            elif isinstance(response, dict):
                return response.get('choices', [{}])[0].get('message', {}).get('content', '')
            else:
                return str(response)
                
        except Exception as e:
            print(f"LLM processing error: {e}")
            return None

    def process_with_history(self, text: str, history: List[Dict[str, str]]) -> Optional[str]:
        """
        Process text with conversation history.
        
        Args:
            text: Input text to process
            history: Conversation history
            
        Returns:
            Processed text, or None if processing failed
        """
        try:
            messages = []
            
            # Add system prompt if configured
            if self.system_prompt:
                messages.append({"content": self.system_prompt, "role": "system"})
            
            # Add conversation history
            messages.extend(history)
            
            # Add new user message
            messages.append({"content": text, "role": "user"})
            
            # Prepare completion parameters
            kwargs = {
                'model': self.model,
                'messages': messages,
                'temperature': self.temperature,
                'max_tokens': self.max_tokens
            }
            
            # Add API key if provided
            if self.api_key:
                kwargs['api_key'] = self.api_key

            # Add base_url if provided
            if self.base_url:
                kwargs['base_url'] = self.base_url
            
            # Call litellm directly (blocking call)
            response = self.litellm.completion(**kwargs)
            
            # Extract text from response
            if hasattr(response, 'choices'):
                return response.choices[0].message.content
            elif isinstance(response, dict):
                return response.get('choices', [{}])[0].get('message', {}).get('content', '')
            else:
                return str(response)
                
        except Exception as e:
            print(f"LLM processing with history error: {e}")
            return None

    def health_check(self) -> None:
        """
        Validate LLM processor.
        """
        if not self.api_key and not self.base_url:
            # Maybe local models don't need key? But assuming cloud.
            # If model is ollama, key might be optional. 
            # Let's just try the call.
            pass
            
        try:
            # Minimal request
            kwargs = {
                'model': self.model,
                'messages': [{"role": "user", "content": "hi"}],
                'max_tokens': 1
            }
            if self.api_key:
                kwargs['api_key'] = self.api_key

            if self.base_url:
                kwargs['base_url'] = self.base_url
                
            self.litellm.completion(**kwargs)
            
        except Exception as e:
            raise RuntimeError(f"LLM API validation failed ({self.model}): {e}")
