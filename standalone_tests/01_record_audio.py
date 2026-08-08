"""
Step 1: Standalone Audio Recorder Test (PyAudio Engine)
Records microphone audio on Windows reliably using PyAudio and saves to WAV.
"""

import sys
import time
import wave
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

try:
    import pyaudio
except ImportError:
    print("[X] ERROR: PyAudio not installed. Run 'python -m pip install pyaudio'")
    sys.exit(1)

def record_test_audio(duration_sec=5, output_file="standalone_tests/test_record.wav"):
    """Record test audio using PyAudio."""
    p = pyaudio.PyAudio()
    
    print("--- Available Audio Input Devices (PyAudio) ---")
    default_input_idx = None
    try:
        default_info = p.get_default_input_device_info()
        default_input_idx = default_info.get('index')
        print(f"Default Input Device: Index {default_input_idx} - '{default_info.get('name')}'")
    except Exception as e:
        print(f"Notice: Could not get default input device: {e}")

    device_idx = default_input_idx
    rates_to_try = [44100, 48000, 16000]
    stream = None
    actual_sr = 44100

    for sr in rates_to_try:
        try:
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=sr,
                input=True,
                input_device_index=device_idx,
                frames_per_buffer=1024
            )
            actual_sr = sr
            print(f"[OK] Opened audio stream at {sr} Hz!")
            break
        except Exception as e:
            print(f"Notice: Rate {sr} Hz failed: {e}")
            continue

    if not stream:
        print("[X] ERROR: Failed to open PyAudio input stream! Check Windows Privacy Settings for Microphone.")
        p.terminate()
        return False

    print(f"\n[*] RECORDING for {duration_sec} seconds... Speak into your mic now!")
    frames = []
    num_chunks = int(actual_sr / 1024 * duration_sec)
    
    for _ in range(num_chunks):
        try:
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)
        except Exception as e:
            print(f"Overflow warning: {e}")

    stream.stop_stream()
    stream.close()
    p.terminate()
    print("[*] Stopped recording.")

    if not frames:
        print("[X] ERROR: No audio frames collected!")
        return False

    raw_bytes = b''.join(frames)
    samples = np.frombuffer(raw_bytes, dtype=np.int16)
    float_samples = samples.astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(np.square(float_samples)))) if len(float_samples) > 0 else 0.0

    print(f"[*] Captured Audio Statistics:")
    print(f"   • Samples: {len(samples)}")
    print(f"   • Sample Rate: {actual_sr} Hz")
    print(f"   • Duration: {len(samples)/actual_sr:.2f} seconds")
    print(f"   • Signal RMS: {rms:.6f}")

    # Write WAV
    wf = wave.open(output_file, 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(actual_sr)
    wf.writeframes(raw_bytes)
    wf.close()

    print(f"[OK] Saved recorded audio to '{output_file}'!")
    return True

if __name__ == '__main__':
    record_test_audio()
