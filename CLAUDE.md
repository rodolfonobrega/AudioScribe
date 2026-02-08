# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AudioScribe is a cross-platform, modular audio transcription system that combines real-time audio capture with LLM-enhanced post-processing. It uses LiteLLM to support 100+ AI providers (OpenAI, Groq, Google, Anthropic, etc.) for both transcription and text enhancement.

**Key workflow**: Microphone input → Audio transcription → LLM enhancement → Output (console/clipboard/auto-type)

## Development Commands

### Primary Commands
```bash
make install           # Install package in editable mode
make install-dev       # Install with dev dependencies
make run              # Start the application
make test             # Run pytest tests
make test-coverage    # Run with HTML coverage report (htmlcov/)
make lint             # Run flake8 linting
make format           # Format with black and isort
make mypy             # Type checking with mypy
make check            # Run all checks (lint, mypy, test)
```

### Running the Application
```bash
# Basic usage
python main.py

# Common flags
python main.py --device 1              # Specify audio input device
python main.py --file audio.wav        # Process audio file
python main.py --text "test"           # Process text directly
python main.py --no-llm                # Disable LLM post-processing
python main.py --no-keyboard           # Disable push-to-talk hotkey
python main.py --output clipboard      # Change output handler
python main.py --verbose               # Enable verbose logs
```

### Single Test Execution
```bash
pytest tests/test_orchestrator.py -v              # Specific file
pytest tests/test_orchestrator.py::test_name -v   # Specific test
pytest tests/ -m "unit"                           # By mark
```

## Architecture

### Component Design Patterns

The codebase follows **Dependency Injection** with abstract base classes. All components inherit from interfaces in `core/interfaces/`:

- `AbstractAudioInput` - Audio capture (SoundDeviceInput)
- `AbstractTranscriber` - Speech-to-text (GroqTranscriber via LiteLLM)
- `AbstractLLMProcessor` - Text enhancement (LiteLLMProcessor)
- `AbstractOutputHandler` - Output routing (Console, Clipboard, Auto-type)
- `AbstractKeyboardListener` - Push-to-talk control

### Key Components

**TranscriptionOrchestrator** (`core/orchestrator.py`)
- Central coordinator managing the entire workflow
- Uses a thread-safe queue for audio processing
- Coordinates hotkey recording → transcription → LLM → output
- Handles component lifecycle and error recovery

**TranscriptionFactory** (`core/factory.py`)
- Creates all components with dependency injection
- Platform-aware handler selection (Windows/macOS/Linux)
- Simplifies testing with mock injection

**Configuration System** (`config/settings.py`)
- Type-safe dataclasses for each component
- Layered precedence: CLI args → YAML → Environment variables → Defaults
- YAML base config: `config/defaults.yaml`

### Entry Point Flow

`main.py`:
1. Parses CLI arguments
2. Loads config via `load_config()` with overrides
3. Creates orchestrator via `TranscriptionFactory.create_orchestrator()`
4. **Fail-fast validation**: Calls `health_check()` on each component
5. Starts orchestrator (keyboard listener + processing thread)

## Configuration

### API Keys
Set via environment variables (LiteLLM auto-detects):
```bash
export GROQ_API_KEY="..."      # For Groq models
export OPENAI_API_KEY="..."    # For OpenAI models
export GOOGLE_API_KEY="..."    # For Google models
```

### Model Selection
Edit `config/defaults.yaml` or use env vars:
```bash
export TRANSCRIPTION_MODEL="groq/whisper-large-v3-turbo"
export LLM_MODEL="groq/llama-3.1-8b-instant"
```

### LiteLLM Model Format
Models follow the pattern: `provider/model-name`
- `openai/whisper-1`, `openai/gpt-4o`
- `groq/whisper-large-v3-turbo`, `groq/llama-3.1-8b-instant`
- `google/gemini-2.5-flash`
- `anthropic/claude-3-5-sonnet`

See [LiteLLM docs](https://docs.litellem.ai/) for 100+ provider options.

## Platform-Specific Handlers

| Handler | Platform | Purpose |
|---------|----------|---------|
| `pyautogui` | All | Cross-platform auto-typing (recommended) |
| `autoit` | Windows | Fast Windows-specific auto-typing |
| `applescript` | macOS | macOS system integration |
| `xdotool` | Linux | X11 automation |

Configure in `config/defaults.yaml` under `output.handlers`.

## Testing Guidelines

- Tests use `unittest.mock` for component mocking
- Health checks validate configuration before runtime
- Integration tests mark with `@pytest.mark.integration`
- Unit tests mark with `@pytest.mark.unit`

## Important Notes

- **Fail-fast validation**: Components must pass `health_check()` before starting
- **Thread-safe processing**: Audio queue processed in separate daemon thread
- **Hotkey recording**: Default push-to-talk uses configurable keyboard hotkey
- **Environment loading**: `.env` file auto-loaded via `python-dotenv`
