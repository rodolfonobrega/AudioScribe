# AudioScribe

<div align="center">
  <img src="assets/llm_transcriber.png" alt="AudioScribe Logo" width="500">

  **A cross-platform, modular audio transcription system with LLM processing**

  [![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

  [Features](#-features) • [Quick Start](#-quick-start) • [Architecture](#-architecture) • [Documentation](#-documentation)

</div>

---

## ✨ Features

- 🎙️ **Real-time Audio Recording** - Cross-platform audio input support
- 🚀 **Fast Transcription** - Powered by LiteLLM with support for 100+ AI providers (OpenAI, Groq, Google, Anthropic, etc.)
- 🤖 **Context-Aware LLM Processing** - Smart post-processing that fixes transcription errors using context understanding
- 🌍 **Multi-Provider Support** - Switch between OpenAI, Groq, Google Gemini, Anthropic, Azure, and more
- 🌍 **Cross-Platform** - Works on Windows, macOS, and Linux
- 🔧 **Modular Architecture** - Easy to extend with new implementations
- 🎯 **Type-Safe Configuration** - YAML + Environment variables + CLI
- ✅ **Well-Tested** - Unit tests with 47% coverage
- 📝 **Customizable Prompts** - Use the LLM for translation, summarization, and more

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/rodolfonobrega/audioscribe.git
cd audioscribe

# Install dependencies
pip install -r requirements.txt

# Set your API key (Groq, OpenAI, Google, etc.)
# For Groq (recommended for speed and free tier):
export GROQ_API_KEY="your-api-key-here"

# For OpenAI:
export OPENAI_API_KEY="your-api-key-here"

# For Google:
export GOOGLE_API_KEY="your-api-key-here"
```

### Usage

```bash
# Start transcribing (uses default config)
python main.py

# Specify audio input device index (use if default fails)
python main.py --device 1

# Process an audio file instead of recording
python main.py --file path/to/audio.wav

# Process text directly (useful for testing LLM correction)
python main.py --text "Text to correct"

# Disable LLM post-processing (raw transcription only)
python main.py --no-llm

# Output to clipboard or other handlers
python main.py --output clipboard

# Disable keyboard listener (useful for automation/headless)
python main.py --no-keyboard

# Enable verbose logs
python main.py --verbose

# Use a specific configuration file
python main.py --config config/my_custom_config.yaml
```

### Output Handlers

AudioScribe supports multiple output methods:

| Handler | Platforms | Description |
|---------|-----------|-------------|
| **pyautogui** | Windows, macOS, Linux | Cross-platform keyboard typing (recommended, fast) |
| **autoit** | Windows only | Windows-specific automation (very fast) |
| **clipboard** | Windows, macOS, Linux | Copy to clipboard |
| **stdout** | All | Print to console only |
| **applescript** | macOS only | macOS-specific automation |
| **xdotool** | Linux only | Linux-specific automation |

Configure in `config/defaults.yaml`:
```yaml
output:
  handlers:
    - pyautogui  # or autoit, clipboard, etc.
```
```

### Configuration Hierarchy

AudioScribe loads configuration in the following order (last one wins):

1.  **`config/defaults.yaml`**: Base settings.
2.  **Environment Variables**: Overrides from `.env` or system.
    *   `GROQ_API_KEY`, `OPENAI_API_KEY`, etc.
    *   `TRANSCRIPTION_MODEL`, `LLM_MODEL`
3.  **CLI Arguments**: Command-line flags override everything.

### Customizing Models

To change the model, edit `config/defaults.yaml` or use environment variables:

```yaml
# config/defaults.yaml
transcription:
  model: groq/whisper-large-v3-turbo

llm:
  model: groq/meta-llama/llama-guard-4-12b
```

Or via environment variables:

```bash
export TRANSCRIPTION_MODEL="openai/whisper-1"
export LLM_MODEL="gpt-4"
python main.py
```

### Supported Providers via LiteLLM

Both transcription and LLM processing use **LiteLLM**, which provides a unified API for 100+ AI providers:

| Provider | Model Examples |
|----------|---------------|
| **OpenAI** | `openai/whisper-1`, `openai/gpt-4o`, `openai/gpt-3.5-turbo` |
| **Groq** | `groq/whisper-large-v3-turbo`, `groq/llama-3.1-8b-instant`, `groq/llama-3.3-70b-versatile` |
| **Google** | `google/gemini-2.5-flash`, `google/gemini-3-pro` |
| **Anthropic** | `anthropic/claude-3-5-sonnet` |
| **Azure** | `azure/gpt-4o` |
| **And 95+ more** | See [LiteLLM documentation](https://docs.litellm.ai/) |

To switch providers, simply change the model prefix (e.g., `openai/`, `google/`).

## 🧪 Testing

```bash
# Run tests
pytest tests/

# Run with coverage
pytest --cov=core --cov=config --cov-report=html

# View coverage report
open htmlcov/index.html  # macOS
start htmlcov/index.html  # Windows
xdg-open htmlcov/index.html  # Linux
```

## 🐳 Docker

```bash
# Build and run with Docker
docker-compose up --build

# Run with audio device support
docker run --device /dev/snd audioscribe
```

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Groq](https://groq.com/) - Fast inference platform
- [LiteLLM](https://github.com/BerriAI/litellm) - Unified LLM API
- [sounddevice](https://python-sounddevice.readthedocs.io/) - Audio I/O

---

<div align="center">

**Made with ❤️ by [Rodolfo](https://github.com/rodolfonobrega)**

[⬆ Back to Top](#audioscribe)

</div>
