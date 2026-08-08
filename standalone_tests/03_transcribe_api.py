"""
Step 3: Standalone API Transcription Test
Sends recorded WAV audio to Groq/OpenAI Whisper API and prints transcription.
"""

import os
import sys
import time
import yaml

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def load_env_file():
    """Load environment variables from .env file if present."""
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip("'\"")

def get_api_config():
    """Load provider configuration."""
    load_env_file()
    
    config_path = "config.yaml"
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            transcription = data.get("transcription", {})
            return {
                "provider": transcription.get("provider", "groq"),
                "model": transcription.get("model", "groq/whisper-large-v3-turbo"),
                "api_key": transcription.get("api_key") or os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
            }
            
    return {
        "provider": "groq",
        "model": "groq/whisper-large-v3-turbo",
        "api_key": os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
    }

def test_transcription(audio_file="standalone_tests/test_record.wav"):
    """Test API transcription."""
    if not os.path.exists(audio_file):
        print(f"[X] ERROR: Audio file '{audio_file}' does not exist! Run 01_record_audio.py first.")
        return None
        
    cfg = get_api_config()
    print(f"--- Standalone API Transcription Test ---")
    print(f"Provider: {cfg['provider']}")
    print(f"Model: {cfg['model']}")
    print(f"Audio File: {audio_file} ({os.path.getsize(audio_file)} bytes)")
    
    if not cfg['api_key']:
        print("[X] ERROR: No API Key found in .env or environment variables!")
        return None
        
    try:
        import litellm
        start_time = time.perf_counter()
        
        with open(audio_file, "rb") as f:
            response = litellm.transcription(
                model=cfg["model"],
                file=f,
                api_key=cfg["api_key"]
            )
            
        latency_ms = round((time.perf_counter() - start_time) * 1000.0)
        text = getattr(response, "text", str(response))
        
        print(f"\n[OK] TRANSCRIPTION SUCCESS ({latency_ms} ms):")
        print(f"--------------------------------------------------")
        print(f"\"{text}\"")
        print(f"--------------------------------------------------")
        return text
        
    except Exception as e:
        print(f"[X] ERROR during transcription: {e}")
        return None

if __name__ == '__main__':
    test_transcription()
