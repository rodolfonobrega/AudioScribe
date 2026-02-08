"""
Groq Transcriber Implementation
Uses Groq's Whisper model for audio transcription via LiteLLM.
"""

import os
import tempfile
from typing import Optional

from core.interfaces.transcriber import AbstractTranscriber


class GroqTranscriber(AbstractTranscriber):
    """Transcriber implementation using Groq's Whisper model."""
    
    def __init__(self, config):
        """
        Initialize Groq transcriber.
        
        Args:
            config: Transcription configuration
        """
        self.config = config
        self.api_key = config.api_key
        self.model = config.model
        self.language = config.language
        self.temperature = config.temperature
        
        if not self.api_key:
            raise ValueError("Groq API key is required. Please set GROQ_API_KEY in your .env file or environment variables.")
        
        # Import litellm
        try:
            import litellm
            self.litellm = litellm
        except ImportError:
            raise ImportError("litellm is required. Install with: pip install litellm")

    def transcribe(self, audio_data: bytes) -> Optional[str]:
        """
        Transcribe audio data.
        
        Args:
            audio_data: WAV audio data
            
        Returns:
            Transcribed text, or None if failed
        """
        try:
            # Save audio data to temporary file
            with tempfile.NamedTemporaryFile(suffix='.flac', delete=False) as temp_file:
                temp_path = temp_file.name
                temp_file.write(audio_data)
            
            # Transcribe the temporary file
            result = self.transcribe_file(temp_path)
            
            # Clean up
            try:
                os.unlink(temp_path)
            except:
                pass
            
            return result
            
        except Exception as e:
            print(f"Transcription error: {e}")
            return None

    def transcribe_file(self, file_path: str) -> Optional[str]:
        """
        Transcribe audio file.
        
        Args:
            file_path: Path to WAV audio file
            
        Returns:
            Transcribed text, or None if failed
        """
        try:
            # Open file for reading
            with open(file_path, 'rb') as audio_file:
                # Prepare transcription parameters
                kwargs = {
                    'model': self.model,
                    'file': audio_file,
                    'api_key': self.api_key,
                    'temperature': self.temperature
                }
                
                # Add language if not auto
                if self.language and self.language != 'auto':
                    kwargs['language'] = self.language
                
                # Call litellm directly (blocking call)
                response = self.litellm.transcription(**kwargs)
            
            # Extract text from response
            if isinstance(response, dict):
                return response.get('text', '')
            elif hasattr(response, 'text'):
                return response.text
            else:
                return str(response)
                
        except Exception as e:
            print(f"File transcription error: {e}")
            return None

    @property
    def supports_streaming(self) -> bool:
        """Groq does not support streaming transcription yet."""
        return False

    def health_check(self) -> None:
        """
        Validate Groq transcription service.
        """
        if not self.api_key:
            raise ValueError("Groq API key is missing.")
            
        temp_path = None
        try:
            # Create a tiny 10ms silent wav on disk
            import wave
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
                with wave.open(temp_file, 'wb') as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16000)
                    # 160 frames = 10ms
                    wav.writeframes(b'\x00\x00' * 160)
            
            # Use litellm direct call with file object
            # This verifies network, auth, and model access
            with open(temp_path, 'rb') as audio_file:
                self.litellm.transcription(
                    model=self.model,
                    file=audio_file,
                    api_key=self.api_key
                )
            
            # We don't care about the result text ("" or nonsense), just that it didn't raise
            
        except Exception as e:
            raise RuntimeError(f"Groq API validation failed: {e}")
        finally:
            # Clean up temp file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except:
                    pass
