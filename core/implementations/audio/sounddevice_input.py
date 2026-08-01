"""
SoundDevice Audio Input Implementation
Uses sounddevice and soundfile for cross-platform audio recording.
"""

import threading
import queue
from typing import List, Dict, Any, Optional

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    import soundfile as sf
except ImportError:
    sf = None

try:
    import numpy as np
except ImportError:
    np = None

from core.interfaces.audio_input import AbstractAudioInput


def calculate_rms(audio_data) -> float:
    """Calculate Root Mean Square (RMS) power of audio samples or WAV bytes."""
    if audio_data is None or np is None:
        return 0.0
    try:
        if isinstance(audio_data, bytes):
            if len(audio_data) <= 44:
                return 0.0
            samples = np.frombuffer(audio_data[44:], dtype=np.int16)
            if len(samples) == 0:
                return 0.0
            float_samples = samples.astype(np.float32) / 32768.0
            return float(np.sqrt(np.mean(np.square(float_samples))))
        elif hasattr(audio_data, 'dtype'):
            if len(audio_data) == 0:
                return 0.0
            return float(np.sqrt(np.mean(np.square(audio_data.astype(np.float32)))))
    except Exception:
        return 0.0
    return 0.0


class SoundDeviceInput(AbstractAudioInput):
    """Audio input implementation using sounddevice."""
    
    def __init__(self, config):
        """
        Initialize sounddevice audio input.
        
        Args:
            config: Audio configuration
        """
        self.config = config
        self.sample_rate = config.sample_rate
        self.channels = config.channels
        self.device_index = config.device_index
        self.dtype = config.dtype
        self._device_name = None  # Cache device name
        
        self._is_recording = False
        self._recording_thread = None
        self._audio_queue = queue.Queue()
        self._stream = None
        self._stop_event = threading.Event()
    
    def _get_device_name(self) -> str:
        """
        Get the current device name.
        
        Returns:
            String description of device (Name (Index N))
        """
        if sd is None:
            return "N/A (sounddevice ausente)"

        try:
            target_index = self.device_index
            
            # Resolve target index if auto
            if target_index is None:
                try:
                    default_in = sd.default.device[0]
                    if default_in >= 0:
                        target_index = default_in
                    else:
                        # Fallback search
                        devices = sd.query_devices()
                        for i, dev in enumerate(devices):
                            if dev.get('max_input_channels', 0) > 0:
                                target_index = i
                                break
                except:
                    pass

            if target_index is not None:
                # Get info for specific index
                try:
                    dev_info = sd.query_devices(target_index)
                    name = dev_info.get('name', 'Unknown')
                    return f"{name} (Index {target_index})"
                except:
                    return f"Unknown Device (Index {target_index})"
                    
            return "Default/Auto (No Input Found)"
            
        except Exception as e:
            return f"Error retrieving device info: {e}"
    
    def _recording_callback(self, indata, frames, time_info, status):
        """Callback for audio recording."""
        if status:
            print(f"Recording status: {status}")
        
        # Put audio data in queue
        self._audio_queue.put(indata.copy())
    
    def start_recording(self) -> None:
        """Start recording audio."""
        if self._is_recording:
            print("Already recording")
            return
        
        self._is_recording = True
        self._stop_event.clear()
        
        # Start recording in a separate thread
        self._recording_thread = threading.Thread(target=self._record_audio, daemon=True)
        self._recording_thread.start()
    
    def _record_audio(self):
        """Record audio in a separate thread."""
        try:
            # Setup device
            device_index = self.device_index
            
            # If no specific device is requested, check if default is valid
            if device_index is None:
                try:
                    default_in = sd.default.device[0]
                    if default_in == -1:
                        # No default device set, find first available input
                        devices = sd.query_devices()
                        for i, dev in enumerate(devices):
                            if dev.get('max_input_channels', 0) > 0:
                                device_index = i
                                print(f"Using fallback input device: {i} ({dev.get('name')})")
                                break
                except Exception:
                    pass

            device_kwargs = {}
            if device_index is not None:
                device_kwargs['device'] = device_index
            
            # Start audio stream
            
            # Start audio stream
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=self.dtype,
                callback=self._recording_callback,
                **device_kwargs
            ) as stream:
                self._stream = stream
                # Keep recording until stop event
                while not self._stop_event.is_set():
                    sd.sleep(100)
        except Exception as e:
            print(f"Recording error: {e}")
            self._is_recording = False
    
    def stop_recording(self) -> bytes:
        """
        Stop recording and return audio data.
        
        Returns:
            Raw audio data as bytes (WAV format)
        """
        if not self._is_recording:
            print("Not recording")
            return b''
        
        # Signal stop
        self._stop_event.set()
        
        # Wait for recording thread to finish
        if self._recording_thread:
            self._recording_thread.join(timeout=2.0)
        
        self._is_recording = False
        self._stream = None
        
        # Collect all audio data from queue
        audio_chunks = []
        while not self._audio_queue.empty():
            try:
                chunk = self._audio_queue.get_nowait()
                audio_chunks.append(chunk)
            except queue.Empty:
                break
        
        if not audio_chunks:
            return b''
        
        # Concatenate chunks
        audio_data = np.concatenate(audio_chunks, axis=0)
        
        # Convert to WAV bytes
        import io
        buffer = io.BytesIO()
        sf.write(buffer, audio_data, self.sample_rate, format='WAV')
        return buffer.getvalue()
    
    def list_devices(self) -> List[Dict[str, Any]]:
        """
        List available audio input devices.
        
        Returns:
            List of device information dictionaries
        """
        devices = []
        try:
            device_dict = sd.query_devices()
            
            if isinstance(device_dict, dict):
                # Single device
                if device_dict.get('max_input_channels', 0) > 0:
                    devices.append({
                        'index': device_dict.get('name', 'Unknown'),
                        'name': device_dict.get('name', 'Unknown'),
                        'channels': device_dict.get('max_input_channels', 0),
                        'sample_rate': device_dict.get('default_samplerate', 0)
                    })
            else:
                # Multiple devices
                for i, dev in enumerate(device_dict):
                    if dev.get('max_input_channels', 0) > 0:
                        devices.append({
                            'index': i,
                            'name': dev.get('name', 'Unknown'),
                            'channels': dev.get('max_input_channels', 0),
                            'sample_rate': dev.get('default_samplerate', 0)
                        })
        except Exception as e:
            print(f"Error listing devices: {e}")
        
        return devices
    
    def get_device_list(self) -> List[Dict[str, Any]]:
        """Alias for list_devices() for backward compatibility."""
        return self.list_devices()
    
    def set_device(self, device_index: int) -> None:
        """Set the audio input device."""
        self.device_index = device_index

    def health_check(self) -> None:
        """
        Validate audio input device by attempting to open a stream.
        """
        if sd is None or sf is None or np is None:
            raise RuntimeError(
                "Dependências de áudio ausentes (sounddevice, soundfile ou numpy).\n"
                "💡 Instale executando: pip install -r requirements.txt"
            )

        try:
            device_index = self.device_index
            if device_index is None:
                # Use same logic as _record_audio/get_device_name to find device
                try:
                    default_in = sd.default.device[0]
                    if default_in >= 0:
                        device_index = default_in
                    else:
                        devices = sd.query_devices()
                        for i, dev in enumerate(devices):
                            if dev.get('max_input_channels', 0) > 0:
                                device_index = i
                                break
                except:
                    pass
            
            if device_index is None:
                raise RuntimeError(
                    "Nenhum dispositivo de entrada de áudio (microfone) foi encontrado no sistema.\n"
                    "💡 Soluções:\n"
                    "  • Conecte um microfone.\n"
                    "  • No macOS: Conceda permissão em 'Ajustes do Sistema > Privacidade e Segurança > Microfone'.\n"
                    "  • No Linux: Verifique se o ALSA/PulseAudio está ativo (`sudo apt install libportaudio2`)."
                )

            # Test stream creation
            device_kwargs = {'device': device_index}
            try:
                with sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype=self.dtype,
                    **device_kwargs
                ):
                    pass
            except Exception as e:
                raise RuntimeError(
                    f"Falha ao acessar dispositivo de áudio (Index {device_index}): {e}\n"
                    "💡 Verifique se o microfone não está em uso exclusivo por outro aplicativo."
                )
                
        except Exception as e:
            raise RuntimeError(f"Validação do áudio de entrada falhou: {e}")

    @property
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._is_recording
    
    @property
    def sample_rate(self) -> int:
        """Sample rate in Hz."""
        return self._sample_rate
    
    @sample_rate.setter
    def sample_rate(self, value: int):
        self._sample_rate = value
    
    @property
    def channels(self) -> int:
        """Number of audio channels."""
        return self._channels
    
    @channels.setter
    def channels(self, value: int):
        self._channels = value
