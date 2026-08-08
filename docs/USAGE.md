# AudioScribe Usage Guide

## Key Updates & Improvements

1. **Clean & Concise Terminal Output**
   - Streamlined output header removing noisy log dividers
   - Compact status layout displaying active transcription provider and engine settings
   - Output handler details clearly indicated without internal class names

2. **LLM Control Flags**
   - Configurable in `config/defaults.yaml` via `llm.enabled`
   - Dedicated CLI flag `--no-llm` to temporarily bypass LLM post-processing

3. **Audio Device Selection**
   - Displays "Device Default" when `--device` is omitted
   - Displays "Device X (Device Name)" when explicitly passing `--device X`

## How to Use

### Basic Usage (Console Output)
```bash
python main.py --no-keyboard
```

### With LLM Post-Processing Enabled
Edit `config/defaults.yaml` and set `enabled: true`:
```yaml
llm:
  enabled: true
```

Then run:
```bash
python main.py
```

### Output Handlers
```bash
python main.py --output clipboard
python main.py --output autoit
python main.py --output pyautogui
```

### Specific Input Device
```bash
python main.py --device 1
```

### Disable LLM via CLI
```bash
python main.py --no-llm
```

## Expected Startup Output

```
AudioScribe v1.0
----------------------------------------
Transcription: litellm / groq/whisper-large-v3-turbo
             (lang=auto, temp=0.0)
Audio        : 16000 // 1kHz | mono
Runtime      : LLM=off | Output=console
----------------------------------------
Hotkey: f9 | Ctrl+C to exit
```

## Command-Line Arguments

- `--config PATH` - Path to custom configuration YAML file
- `--output TYPE` - Output target (`console`, `clipboard`, `pyautogui`, `autoit`, `applescript`, `xdotool`)
- `--device INDEX` - Audio input device index
- `--no-keyboard` - Disable global hotkey listener
- `--file PATH` - Process existing audio file instead of live recording
- `--text TEXT` - Process text string directly through LLM post-processor
- `--no-llm` - Bypass LLM post-processing
- `--help` - Show help message

## Default Hotkeys
- Press **F9** to toggle recording
- **Ctrl+C** to exit

*Note: Hotkeys and dictation modes can be customized in `config/defaults.yaml`.*

