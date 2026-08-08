"""
SoundDevice Audio Input Implementation
Uses sounddevice and soundfile for cross-platform audio recording.
"""

import threading
import queue
from typing import List, Dict, Any, Optional

import sounddevice as sd
import soundfile as sf
import numpy as np

from core.interfaces.audio_input import AbstractAudioInput


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
            
            # Attempt 1: sounddevice InputStream
            opened = False
            last_err = None
            for sr in [self.sample_rate, 44100, 48000, 16000]:
                try:
                    kwargs = {'device': device_index} if device_index is not None else {}
                    stream = sd.InputStream(
                        samplerate=sr,
                        channels=self.channels,
                        dtype=self.dtype,
                        callback=self._recording_callback,
                        **kwargs
                    )
                    stream.start()
                    opened = True
                    self._actual_sample_rate = sr
                    try:
                        while not self._stop_event.is_set():
                            sd.sleep(100)
                    finally:
                        try:
                            stream.stop()
                            stream.close()
                        except Exception:
                            pass
                    break
                except Exception as e:
                    last_err = e
                    continue

            # Attempt 2: PyAudio fallback if sounddevice stream fails
            if not opened:
                try:
                    import pyaudio
                    p = pyaudio.PyAudio()
                    pa_stream = None
                    actual_sr = 44100
                    for sr in [44100, 48000, 16000]:
                        try:
                            pa_stream = p.open(
                                format=pyaudio.paInt16,
                                channels=1,
                                rate=sr,
                                input=True,
                                input_device_index=device_index,
                                frames_per_buffer=1024
                            )
                            actual_sr = sr
                            opened = True
                            self._actual_sample_rate = sr
                            break
                        except Exception:
                            continue

                    if pa_stream:
                        print(f"[SoundDeviceInput] Recording using PyAudio fallback at {actual_sr} Hz")
                        try:
                            while not self._stop_event.is_set():
                                try:
                                    data = pa_stream.read(1024, exception_on_overflow=False)
                                    # Convert int16 bytes to float32 numpy array
                                    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                                    self._audio_queue.put(samples[:, np.newaxis])
                                except Exception:
                                    pass
                        finally:
                            try:
                                pa_stream.stop_stream()
                                pa_stream.close()
                                p.terminate()
                            except Exception:
                                pass
                except Exception as py_err:
                    last_err = py_err

            if not opened:
                print(f"[SoundDeviceInput] Recording error: {last_err}")
                self._is_recording = False
        except Exception as e:
            print(f"[SoundDeviceInput] Recording error: {e}")
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
        actual_sr = getattr(self, '_actual_sample_rate', self.sample_rate)
        
        # Resample to 16000 Hz if recorded at a different hardware rate (e.g. 44100/48000 Hz)
        if actual_sr != 16000 and len(audio_data) > 0:
            flat_audio = audio_data.squeeze()
            duration = len(flat_audio) / float(actual_sr)
            target_len = int(round(duration * 16000))
            x_orig = np.linspace(0, duration, len(flat_audio), endpoint=False)
            x_target = np.linspace(0, duration, target_len, endpoint=False)
            audio_data = np.interp(x_target, x_orig, flat_audio).astype(np.float32)
        
        # Convert to OGG Vorbis bytes at 16000 Hz (with WAV fallback)
        import io
        buffer = io.BytesIO()
        try:
            sf.write(buffer, audio_data, 16000, format='OGG', subtype='VORBIS')
        except Exception:
            buffer = io.BytesIO()
            sf.write(buffer, audio_data, 16000, format='WAV')
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

    def _resolve_working_device_index(self) -> Optional[int]:
        """Find a working input device index."""
        # 1. Try PyAudio default input device
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            try:
                info = p.get_default_input_device_info()
                idx = info.get('index')
                p.terminate()
                return idx
            except Exception:
                p.terminate()
        except Exception:
            pass

        # 2. Fall back to sounddevice
        if sd is not None:
            try:
                default_in = sd.default.device[0]
                if default_in is not None and default_in >= 0:
                    return default_in
            except Exception:
                pass
        return None

    def health_check(self) -> None:
        """Validate audio input device by attempting to open a stream."""
        # Attempt 1: PyAudio stream check
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            pa_stream = None
            for sr in [44100, 48000, 16000]:
                try:
                    pa_stream = p.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=sr,
                        input=True,
                        input_device_index=self.device_index,
                        frames_per_buffer=1024
                    )
                    break
                except Exception:
                    continue
            if pa_stream:
                pa_stream.stop_stream()
                pa_stream.close()
                p.terminate()
                return  # PyAudio validated input device successfully!
            p.terminate()
        except Exception:
            pass

        # Attempt 2: sounddevice stream check
        try:
            device_index = self.device_index or self._resolve_working_device_index()
            opened = False
            last_err = None
            if device_index is not None and sd is not None:
                for sr in [self.sample_rate, 48000, 44100, 16000]:
                    for ch in [self.channels, 1, 2]:
                        try:
                            with sd.InputStream(samplerate=sr, channels=ch, dtype=self.dtype, device=device_index):
                                opened = True
                                break
                        except Exception as e:
                            last_err = e
                            continue
                    if opened:
                        break

            if not opened:
                raise RuntimeError(f"Failed to access audio input device: {last_err or 'No working device found'}")
                
        except Exception as e:
            raise RuntimeError(f"Audio input validation failed: {e}")

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


def calculate_rms(audio_data) -> float:
    """Calculate Root Mean Square (RMS) power of audio samples or WAV bytes."""
    if audio_data is None:
        return 0.0
    try:
        if isinstance(audio_data, bytes):
            if len(audio_data) <= 44:
                return 0.0
            import numpy as np
            payload = audio_data[44:] if audio_data[:4] == b"RIFF" and audio_data[8:12] == b"WAVE" else audio_data
            samples = np.frombuffer(payload, dtype=np.int16)
            if len(samples) == 0:
                return 0.0
            float_samples = samples.astype(np.float32) / 32768.0
            return float(np.sqrt(np.mean(np.square(float_samples))))
        elif hasattr(audio_data, 'dtype'):
            import numpy as np
            if len(audio_data) == 0:
                return 0.0
            return float(np.sqrt(np.mean(np.square(audio_data.astype(np.float32)))))
    except Exception:
        return 0.0
    return 0.0
