# AudioScribe 🎙️

<div align="center">
  <img src="assets/llm_transcriber.png" alt="AudioScribe Logo" width="550">

  <h3>The Open-Source, Model-Agnostic AI Voice Dictation System</h3>
  <p><b>Stop paying monthly subscriptions for locked-in voice tools. Get 100% freedom, lightning speed, and total control over your AI models.</b></p>

  [![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
  [![Electron](https://img.shields.io/badge/Desktop-Electron-47858E.svg)](https://www.electronjs.org/)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![GitHub Release](https://img.shields.io/github/v/release/rodolfonobrega/AudioScribe)](https://github.com/rodolfonobrega/AudioScribe/releases)

  [Download Desktop App](#-get-started-in-60-seconds) • [Why AudioScribe?](#-why-audioscribe-vs-whisperflow--superwhisper) • [Features](#-key-features) • [Documentation](#-documentation)

</div>

---

## ⚡ Why AudioScribe? (vs. Whisper Flow & Superwhisper)

Proprietary apps like **Whisper Flow** or **Superwhisper** are great—until you get hit with **$10–$20/month subscription fees**, restrictive monthly minute caps, vendor lock-in, and zero control over your privacy or AI model choice.

**AudioScribe was built to set your dictation free:**

| Feature | **AudioScribe 🚀** | **Whisper Flow / Superwhisper 🔒** |
| :--- | :--- | :--- |
| **Price** | **100% Free & Open Source** | $10–$20/month subscription |
| **Model Choice** | **100+ AI Models** (Groq, OpenAI, Gemini, Local Ollama) | Locked to vendor's single default model |
| **Speed** | **Sub-500ms** Instant Response (via Groq) | Varies / Latency delays |
| **Privacy & Offline** | **100% Offline Capable** (Ollama / Localhost) | Cloud-locked |
| **Cross-Platform** | **Windows, macOS & Linux** | macOS-only or Windows-only |
| **Interface** | **Desktop GUI App & CLI Mode** | Closed GUI only |
| **Custom LLM Prompts** | **Fully Customizable** System Prompts | Fixed or non-existent |

---

## ✨ Key Features

- 🚀 **Sub-500ms Instant Transcription** - Powered by **Groq** (`whisper-large-v3-turbo`) for instant voice-to-text without paying a dime.
- 🔓 **Universal Provider Support** - Switch seamlessly between **Groq, OpenAI, Google Gemini, Deepgram, Anthropic**, or run **100% offline with Ollama** (`http://localhost:11434/v1`).
- 🤖 **Context-Aware LLM Refactoring** - Automatically cleans up filler words ("um", "ah"), fixes punctuation, and corrects grammar before auto-typing into your active window.
- 🎙️ **Flexible Dictation Modes**:
  - **Push-to-Talk**: Hold `F9` while speaking, release to type.
  - **Toggle Mode**: Press `F9` to start, press again to stop.
  - **Hands-Free VAD Mode**: Automatically detects your voice and pauses.
- ⚡ **RMS Noise Gate & Latency Monitor** - Filters out background silence automatically and displays real-time execution metrics (`⚡ 320ms`).
- 💻 **Desktop App (Electron) & CLI**:
  - **Non-Technical Users**: Beautiful System Tray Desktop GUI with one-click setup.
  - **Power Users**: Lightweight headless CLI (`python main.py`).

---

## 🚀 Get Started in 60 Seconds

### Option 1: Download the Pre-Compiled Desktop App (Easiest)

1. Go to **[GitHub Releases](https://github.com/rodolfonobrega/AudioScribe/releases)**.
2. Download the installer for your OS:
   - 🪟 **Windows**: `AudioScribe-Setup-1.0.0.exe`
   - 🍏 **macOS**: `AudioScribe-1.0.0.dmg`
   - 🐧 **Linux**: `AudioScribe-1.0.0.AppImage`
3. Get your **free API key** at **[console.groq.com/keys](https://console.groq.com/keys)**, paste it into the app, and press **F9** to dictate!

---

### Option 2: Run via CLI (For Developers & Power Users)

```bash
# 1. Clone repository & install dependencies
git clone https://github.com/rodolfonobrega/AudioScribe.git
cd AudioScribe
pip install -r requirements.txt

# 2. Set your free Groq API key
# Linux / macOS:
export GROQ_API_KEY="gsk_your_key_here"

# Windows PowerShell:
$env:GROQ_API_KEY="gsk_your_key_here"

# 3. Run Pre-flight Diagnostic Check (Optional)
python main.py --preflight-only

# 4. Start Dictating! (Press F9 to record)
python main.py
```

---

## 🛠️ Customizing AI Models & Providers

To change providers, simply edit `config/defaults.yaml` or set environment variables:

```bash
# Use OpenAI Whisper
export TRANSCRIPTION_MODEL="openai/whisper-1"
export OPENAI_API_KEY="sk-..."

# Use Local Ollama (100% Offline & Private)
export TRANSCRIPTION_BASE_URL="http://localhost:11434/v1"
export TRANSCRIPTION_MODEL="ollama/whisper"

python main.py
```

---

## 🖥️ Desktop App Screenshots

<div align="center">
  <p><i>Sleek Dark-Mode Dashboard with System Tray Integration, Device Selector & Live Latency Metrics</i></p>
</div>

---

## 🤝 Contributing

Contributions are welcome! Check out [CONTRIBUTING.md](CONTRIBUTING.md) for details on setting up your environment and submitting pull requests.

## 📄 License

AudioScribe is licensed under the [MIT License](LICENSE).
