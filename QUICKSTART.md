# AudioScribe Quick Start Guide

Get started with AudioScribe in 5 minutes!

## 🚀 Installation

### Option 1: Using pip (Recommended)

```bash
# Clone the repository
git clone https://github.com/rodolfonobrega/audioscribe.git
cd audioscribe

# Install the package
pip install -e .
```

### Option 2: Using Makefile

```bash
# Install with make
make install

# Or install development dependencies
make install-dev
```

### Option 3: Using Docker

```bash
# Build and run with Docker
docker-compose up
```

---

## ⚙️ Configuration

### Step 1: Get API Key

AudioScribe uses **LiteLLM** which supports 100+ AI providers. Choose one:

- **Groq** (recommended for speed & free tier) - [console.groq.com](https://console.groq.com/)
- **OpenAI** - [platform.openai.com](https://platform.openai.com/)
- **Google** - [console.cloud.google.com](https://console.cloud.google.com/)
- **Anthropic** - [console.anthropic.com](https://console.anthropic.com/)

### Step 2: Configure Environment Variables

```bash
# Copy example environment file
cp env.example .env

# Edit .env and add your API key
# For Groq (recommended):
# GROQ_API_KEY=gsk_...

# For OpenAI:
# OPENAI_API_KEY=sk-...

# For Google:
# GOOGLE_API_KEY=...
```

### Step 3: Choose Your Provider

```bash
# Use Groq (default, fast & free)
python main.py

# Use OpenAI
python main.py --transcription-model openai/whisper-1 --llm-model openai/gpt-4

# Use Google Gemini
python main.py --transcription-model google/whisper --llm-model google/gemini-pro
```

### Step 3: Verify Installation

```bash
# Test your API key
python test_groq.py
```

---

## 🎤 Basic Usage

### 1. Keyboard Mode (Push-to-Talk)

```bash
# Start with keyboard listener
python main.py

# Press F9 to start recording
# Press F9 again to stop
# Transcription will appear in console
```

### 2. Record with Timeout

```bash
# Record for 10 seconds
python main.py --timeout 10
```

### 3. Transcribe File

```bash
# Transcribe existing audio file
python main.py --file audio.wav
```

### 4. Toggle Mode

```bash
# Use toggle mode (press hotkey to start/stop)
python main.py --mode toggle
```

---

## 🔧 Advanced Configuration

### Using YAML Config

Create `config.yaml`:

```yaml
# Both transcription and LLM use LiteLLM as unified API
# Change the provider by modifying the model name prefix

audio:
  sample_rate: 16000

transcription:
  provider: litellm
  model: groq/whisper-large-v3-turbo  # or openai/whisper-1, google/whisper
  api_key: ${GROQ_API_KEY}  # or ${OPENAI_API_KEY}, ${GOOGLE_API_KEY}
  language: auto

llm:
  provider: litellm
  model: groq/meta-llama/llama-guard-4-12b  # or openai/gpt-4, google/gemini-pro
  api_key: ${GROQ_API_KEY}
  temperature: 0.7

keyboard:
  hotkey: ctrl+space
  mode: push_to_talk

output:
  handlers:
    - stdout
    - clipboard
```

Then run:

```bash
python main.py --config config.yaml
```

### Custom Hotkey

```bash
# Use custom hotkey combination
python main.py --hotkey "ctrl+shift+t"
```

### Multiple Outputs

```bash
# Output to console, clipboard, and file
python main.py --output stdout,clipboard,file
```

---

## 🌍 Supported Providers

AudioScribe uses **LiteLLM** as a unified API, giving you access to 100+ AI providers through a single interface.

### Popular Providers

| Provider | Best For | API Key | Model Examples |
|----------|-----------|----------|---------------|
| **Groq** | ⚡ Speed, free tier | GROQ_API_KEY | `groq/whisper-large-v3`, `groq/llama-3.3-70b` |
| **OpenAI** | 🧠 Quality, GPT-4 | OPENAI_API_KEY | `openai/whisper-1`, `openai/gpt-4` |
| **Google** | 🌐 Multilingual, Gemini | GOOGLE_API_KEY | `google/whisper`, `google/gemini-pro` |
| **Anthropic** | 🎯 Accuracy, Claude | ANTHROPIC_API_KEY | `anthropic/claude-3-opus` |
| **Azure** | 🏢 Enterprise | AZURE_API_KEY | `azure/whisper`, `azure/gpt-4` |

### Switching Providers

Simply change the model name prefix:

```bash
# Groq (default)
python main.py

# OpenAI
python main.py --transcription-model openai/whisper-1 --llm-model openai/gpt-4

# Google Gemini
python main.py --transcription-model google/whisper --llm-model google/gemini-pro

# Anthropic Claude
python main.py --llm-model anthropic/claude-3-opus
```

For the complete list of supported providers, visit [LiteLLM Documentation](https://docs.litellm.ai/)

---

## 🎯 Common Use Cases

### Use Case 1: Quick Voice Notes

```bash
# Record and copy to clipboard
python main.py --output clipboard --timeout 5
```

### Use Case 2: Meeting Transcription

```bash
# Use toggle mode for long recordings
python main.py --mode toggle --hotkey "ctrl+t"
```

### Use Case 3: Batch File Processing

```bash
# Transcribe multiple files
python main.py --file meeting1.wav
python main.py --file meeting2.wav
python main.py --file interview.wav
```

### Use Case 4: Real-Time Typing (Windows)

```bash
# Type transcribed text automatically
python main.py --output autoit
```

---

## 🤖 Custom LLM Prompts

### What is the LLM Post-Processing?

By default, AudioScribe uses an LLM to improve your transcriptions:
- Fixes grammar and spelling errors
- Adds proper punctuation
- Improves readability

### Disable LLM Processing

If you only want raw transcription without any processing:

```bash
# Disable LLM post-processing
python main.py --no-llm
```

### Use Custom Prompt

You can customize the LLM behavior for different tasks:

```bash
# Translate to English
python main.py --llm-prompt "Translate the following text to English. Return only the translation."

# Summarize the text
python main.py --llm-prompt "Summarize the following text in 3 bullet points."

# Extract action items
python main.py --llm-prompt "Extract all action items from the following text. Format as a numbered list."

# Professional tone
python main.py --llm-prompt "Rewrite the following text in a professional business tone."
```

### Example: English Translation

```bash
# Translate speech to English
python main.py --llm-prompt "You are a translator. Translate everything to English. Return only the translation."
```

### Example: Meeting Notes

```bash
# Create formatted meeting notes
python main.py --llm-prompt "Format the following as meeting notes with: Summary, Discussion Points, and Action Items."
```

---

## 🖥️ Platform-Specific

### Windows

```bash
# Use AutoIt for automatic text typing
python main.py --output autoit

# Or use standard Windows output
python main.py --output stdout,clipboard
```

### macOS

```bash
# Use AppleScript for automatic text typing
python main.py --output applescript

# Or use standard macOS output
python main.py --output stdout,clipboard
```

### Linux

```bash
# Use xdotool for automatic text typing
python main.py --output xdotool

# Or use standard Linux output
python main.py --output stdout,clipboard
```

---

## 🐛 Troubleshooting

### Issue: "API key not configured"

**Solution:**
```bash
# Make sure you set the environment variable
export GROQ_API_KEY="your-key-here"

# Or create .env file
echo "GROQ_API_KEY=your-key-here" > .env
```

### Issue: "No audio devices found"

**Solution:**
```bash
# List available devices
python -c "import sounddevice as sd; print(sd.query_devices())"

# Specify device index
python main.py --device 1
```

### Issue: "Permission denied" (Linux)

**Solution:**
```bash
# Add user to audio group
sudo usermod -a -G audio $USER

# Run with sudo for keyboard access
sudo python main.py
```

### Issue: "Import errors"

**Solution:**
```bash
# Reinstall dependencies
pip install -r requirements.txt

# Or upgrade pip
pip install --upgrade pip
```

---

## 📚 Next Steps

1. **Read the full documentation** - [README.md](README.md)
2. **Check examples** - [example_usage.py](example_usage.py)
3. **Explore configuration** - [config/defaults.yaml](config/defaults.yaml)
4. **Run tests** - `make test`
5. **Contribute** - Check [CONTRIBUTING.md](CONTRIBUTING.md)

---

## 💡 Tips

### Tip 1: Use Aliases

Create aliases in your shell:

```bash
# Add to ~/.bashrc or ~/.zshrc
alias transcribe='python ~/audioscribe/main.py'
alias transcribe-5='python ~/audioscribe/main.py --timeout 5'
```

### Tip 2: Create Scripts

Create custom scripts:

```bash
#!/bin/bash
# quick-record.sh
python main.py --timeout 5 --output clipboard
echo "Transcription copied to clipboard!"
```

### Tip 3: Use with Other Tools

```bash
# Pipe to other commands
python main.py --timeout 5 | grep "keyword"

# Save to file with timestamp
python main.py --timeout 5 >> transcripts_$(date +%Y%m%d).txt
```

---

## 🎓 Learning Resources

- **LiteLLM Documentation** - [docs.litellm.ai](https://docs.litellm.ai/) - 100+ supported providers
- **Groq Documentation** - [console.groq.com/docs](https://console.groq.com/docs)
- **OpenAI Documentation** - [platform.openai.com/docs](https://platform.openai.com/docs)
- **Google AI Documentation** - [ai.google.dev/docs](https://ai.google.dev/docs)
- **Whisper Models** - [github.com/openai/whisper](https://github.com/openai/whisper)

---

## ❓ Need Help?

- **Issues** - [github.com/rodolfonobrega/audioscribe/issues](https://github.com/rodolfonobrega/audioscribe/issues)
- **Discussions** - [github.com/rodolfonobrega/audioscribe/discussions](https://github.com/rodolfonobrega/audioscribe/discussions)
- **Email** - rodolfonobregar@gmail.com

---

## 🎉 You're Ready!

Start transcribing:

```bash
python main.py
```

Press **F9** and start speaking! 🎤

---

**Happy Transcribing!** 🚀
