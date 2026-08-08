"""
Step 5: Combined Full End-to-End Pipeline (PyAudio & Direct Win32 Paste)
Combines Hotkey Listener -> PyAudio Recording -> API Transcription -> Direct Win32 Auto-Paste.
"""

import os
import sys
import time
import wave
import ctypes
import queue
import threading
import yaml
import numpy as np
import pyaudio
import keyboard
import pyperclip

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def win32_paste_direct():
    user32 = ctypes.windll.user32
    VK_CONTROL = 0x11
    VK_V = 0x56
    KEYEVENTF_KEYUP = 0x0002

    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_V, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

def load_env_file():
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip("'\"")

def get_api_key_and_model():
    load_env_file()
    if os.path.exists("config.yaml"):
        with open("config.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            transcription = data.get("transcription", {})
            return (
                transcription.get("model", "groq/whisper-large-v3-turbo"),
                transcription.get("api_key") or data.get("api_key") or os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
            )
    return "groq/whisper-large-v3-turbo", os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")

class StandaloneAudioScribeEngine:
    def __init__(self):
        self.is_recording = False
        self.audio_frames = []
        self.recording_thread = None
        self.stop_event = threading.Event()
        self.last_hotkey_time = 0.0
        self.model, self.api_key = get_api_key_and_model()

        print("==================================================")
        print("[*] Standalone AudioScribe Full Pipeline Engine")
        print("==================================================")
        print(f"Model: {self.model}")
        print(f"API Key: {'[OK] Configured' if self.api_key else '[X] MISSING'}")
        print("Press 'ctrl+windows' or 'f9' anywhere to START/STOP recording.")
        print("Press Ctrl+C to exit.\n")

    def toggle_recording(self):
        now = time.perf_counter()
        if (now - self.last_hotkey_time) < 0.4:
            return
        self.last_hotkey_time = now

        if self.is_recording:
            self.stop_recording_and_process()
        else:
            self.start_recording()

    def start_recording(self):
        if not self.api_key:
            print("[X] ERROR: Cannot record — API Key is missing!")
            return

        self.audio_frames = []
        self.stop_event.clear()
        self.is_recording = True
        
        self.recording_thread = threading.Thread(target=self._record_loop, daemon=True)
        self.recording_thread.start()
        print("\n[*] RECORDING STARTED... Speak into your mic now!")

    def _record_loop(self):
        p = pyaudio.PyAudio()
        stream = None
        actual_sr = 44100

        for sr in [44100, 48000, 16000]:
            try:
                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=sr,
                    input=True,
                    frames_per_buffer=1024
                )
                actual_sr = sr
                break
            except Exception:
                continue

        if not stream:
            print("[X] ERROR: Could not open PyAudio input stream!")
            self.is_recording = False
            p.terminate()
            return

        try:
            while not self.stop_event.is_set():
                try:
                    data = stream.read(1024, exception_on_overflow=False)
                    self.audio_frames.append(data)
                except Exception:
                    pass
        finally:
            try:
                stream.stop_stream()
                stream.close()
                p.terminate()
            except Exception:
                pass

        self._save_and_transcribe(actual_sr)

    def stop_recording_and_process(self):
        print("[*] RECORDING STOPPED. Transcribing audio...")
        self.stop_event.set()
        self.is_recording = False

    def _save_and_transcribe(self, sample_rate):
        if not self.audio_frames:
            print("[!] Warning: Empty audio captured (0 bytes).")
            return

        raw_bytes = b''.join(self.audio_frames)
        if len(raw_bytes) < 3200:
            print("[!] Warning: Recording too short.")
            return

        temp_wav = "standalone_tests/temp_pipeline.wav"
        wf = wave.open(temp_wav, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(raw_bytes)
        wf.close()

        threading.Thread(target=self._transcribe_and_paste, args=(temp_wav,), daemon=True).start()

    def _transcribe_and_paste(self, wav_path):
        try:
            import litellm
            start = time.perf_counter()
            with open(wav_path, "rb") as f:
                res = litellm.transcription(
                    model=self.model,
                    file=f,
                    api_key=self.api_key
                )
            latency = round((time.perf_counter() - start) * 1000.0)
            text = getattr(res, "text", str(res)).strip()

            if not text:
                print("[!] Silence Captured (empty transcription result).")
                return

            print(f"[OK] TRANSCRIBED ({latency}ms): \"{text}\"")

            # 1. Copy to Clipboard
            pyperclip.copy(text)
            
            # 2. Simulate Ctrl+V directly via Win32 Ctypes (no focus stealing!)
            win32_paste_direct()
            print("[OK] PASTED TEXT DIRECTLY INTO ACTIVE WINDOW!")

        except Exception as e:
            print(f"[X] ERROR in transcription/paste pipeline: {e}")
        finally:
            if os.path.exists(wav_path):
                try: os.unlink(wav_path)
                except OSError: pass

if __name__ == '__main__':
    engine = StandaloneAudioScribeEngine()
    keyboard.add_hotkey("ctrl+windows", engine.toggle_recording, suppress=False)
    keyboard.add_hotkey("f9", engine.toggle_recording, suppress=False)
    try:
        keyboard.wait()
    except KeyboardInterrupt:
        print("\n[OK] Engine stopped.")
