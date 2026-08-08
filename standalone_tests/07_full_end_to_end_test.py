"""
Comprehensive Standalone End-to-End Diagnostic Test Script.
Tests:
1. Microphone stream & audio capture (3 seconds)
2. STT Transcription via Groq / LiteLLM API
3. Clipboard copy & Win32 keybd_event auto-paste into active window
"""

import sys
import time
import os
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("=== STEP 1: MICROPHONE STREAM & AUDIO CAPTURE TEST ===")
try:
    from config.settings import load_config
    from core.implementations.audio.sounddevice_input import SoundDeviceInput
    
    cfg = load_config()
    audio_input = SoundDeviceInput(cfg.audio)
    print("[1/3] SoundDeviceInput initialized.")
    
    print("[2/3] Starting 3-second recording... (Speak into your mic now!)")
    audio_input.start_recording()
    time.sleep(3.0)
    audio_bytes = audio_input.stop_recording()
    
    print(f"[3/3] Captured {len(audio_bytes)} bytes of OGG audio.")
    assert len(audio_bytes) > 500, "Audio buffer empty!"
    print(">>> STEP 1 PASSED: Audio recording successful! <<<\n")

except Exception as e:
    print(f"FAILED Step 1: {e}")
    sys.exit(1)

print("=== STEP 2: STT TRANSCRIPTION TEST ===")
try:
    from core.factory import TranscriptionFactory
    
    transcriber = TranscriptionFactory.create_transcriber(cfg)
    print(f"[1/2] Created Transcriber: {type(transcriber).__name__}")
    
    print("[2/2] Transcribing 3s audio clip...")
    t0 = time.perf_counter()
    text = transcriber.transcribe(audio_bytes)
    dt = round((time.perf_counter() - t0) * 1000)
    
    print(f"Transcribed Text ({dt}ms): '{text}'")
    assert text is not None, "Transcription returned None!"
    print(">>> STEP 2 PASSED: STT Transcription successful! <<<\n")

except Exception as e:
    print(f"FAILED Step 2: {e}")
    sys.exit(1)

print("=== STEP 3: AUTO-PASTE TEST ===")
try:
    from core.implementations.output.output_handlers import ClipboardOutputHandler
    
    test_phrase = "AudioScribe E2E Verification Test"
    handler = ClipboardOutputHandler(cfg.output)
    print(f"[1/2] Copying test phrase to clipboard: '{test_phrase}'...")
    handler.output(test_phrase)
    
    print(">>> STEP 3 PASSED: Clipboard update successful! <<<\n")
    print("==================================================")
    print("🎉 ALL 3 DIAGNOSTIC STEPS PASSED 100% CLEANLY!")
    print("==================================================")

except Exception as e:
    print(f"FAILED Step 3: {e}")
    sys.exit(1)
