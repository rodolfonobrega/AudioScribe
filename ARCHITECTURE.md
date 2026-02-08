# AudioScribe - Architecture Diagram

## High-Level Architecture Overview

```
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                              AudioScribe v2.0.0                        │
 │                        Modular & Cross-Platform Architecture                │
 └─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACE                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │    CLI       │  │   Keyboard   │  │  Config YAML │  │    API       │  │
│  │   (main.py)  │  │  (Hotkeys)   │  │   (.yaml)    │  │  (future)    │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
└─────────┼──────────────────┼──────────────────┼──────────────────┼─────────┘
          │                  │                  │                  │
          └──────────────────┼──────────────────┼──────────────────┘
                             │                  │
                             ▼                  ▼
                    ┌─────────────────────────────────────────────┐
                    │         TranscriptionOrchestrator           │
                    │         (Core Coordination Layer)           │
                    │                                             │
                    │  • Manages component lifecycle              │
                    │  • Coordinates data flow                    │
                    │  • Handles errors and logging               │
                    │  • Routes outputs to handlers               │
                    └─────┬──────────────┬──────────────┬────────┘
                          │              │              │
         ┌────────────────┘              │              └────────────────┐
         │                                │                                │
         ▼                                ▼                                ▼
 ┌─────────────────┐           ┌─────────────────┐           ┌─────────────────┐
 │  Audio Input    │           │  Transcriber    │           │  LLM Processor  │
 │  (Implementation)│           │  (Implementation)│           │  (Implementation)│
 ├─────────────────┤           ├─────────────────┤           ├─────────────────┤
 │ • SoundDevice   │           │ • Groq (via LiteLLM)       │ • LiteLLM       │
 │ • PyAudio       │           │ • OpenAI (via LiteLLM)      │ • OpenAI (via)  │
 │ • CoreAudio     │           │ • Google (via LiteLLM)      │ • Anthropic (via)│
 │ • WASAPI        │           │ • Anthropic (via LiteLLM)    │ • Google (via)  │
 │                 │           │ • 100+ providers             │ • 100+ providers│
 └─────────────────┘           └─────────────────┘           └─────────────────┘
         │                                │                                │
         │                                │                                │
         └────────────────────────────────┼────────────────────────────────┘
                                         │
                                         ▼
                              ┌─────────────────┐
                              │ Output Handler  │
                              │ (Implementation)│
                              ├─────────────────┤
                              │ • Stdout        │
                              │ • Clipboard     │
                              │ • File          │
                              │ • AutoIt (Win)  │
                              │ • AppleScript   │
                              │ • Xdotool (Lin) │
                              └─────────────────┘
```

---

## Component Hierarchy

```
 AudioScribe
 │
 ├── Core Layer (core/)
│   ├── Interfaces (interfaces/)           # Abstract base classes
│   │   ├── AbstractAudioInput
│   │   ├── AbstractTranscriber
│   │   ├── AbstractLLMProcessor
│   │   ├── AbstractOutputHandler
│   │   └── AbstractKeyboardListener
│   │
│   ├── Orchestrator (orchestrator.py)     # Main coordinator
│   │   └── TranscriptionOrchestrator
│   │
│   ├── Factory (factory.py)               # Component creation
│   │   └── TranscriptionFactory
│   │
│   └── Implementations (implementations/) # Concrete implementations
│       ├── Audio/
│       │   ├── SoundDeviceAudioInput
│       │   ├── PyAudioAudioInput
│       │   ├── CoreAudioInput (macOS)
│       │   └── WasapiAudioInput (Windows)
│       │
 │       ├── Transcription/
 │       │   ├── GroqTranscriber (via LiteLLM - supports 100+ providers)
 │       │   └── [Future: Add more transcribers via LiteLLM]
 │       │
 │       ├── LLM/
 │       │   ├── LiteLLMProcessor (unified API for 100+ providers)
│       │
│       ├── Output/
│       │   ├── StdoutOutputHandler
│       │   ├── ClipboardOutputHandler
│       │   ├── FileOutputHandler
│       │   ├── AutoItOutputHandler (Windows)
│       │   ├── AppleScriptOutputHandler (macOS)
│       │   └── XdotoolOutputHandler (Linux)
│       │
│       └── Keyboard/
│           ├── KeyboardListener (cross-platform)
│           ├── PyObjCListener (macOS)
│           └── PynputListener (alternative)
│
├── Configuration Layer (config/)
│   ├── Settings (settings.py)             # Type-safe config
│   ├── AudioSettings
│   ├── TranscriptionSettings
│   ├── LLMSettings
│   ├── OutputSettings
│   ├── KeyboardSettings
│   └── OrchestratorSettings
│
├── Utilities Layer (utils/)
│   ├── Logger
│   └── AudioUtils
│
├── Entry Points
│   ├── main.py                            # CLI application
│   ├── example_usage.py                   # Usage examples
│   └── setup.py                           # Package setup
│
├── Testing Layer (tests/)
│   ├── test_core.py                       # Unit tests
│   ├── test_integration.py                # Integration tests
│   └── mocks/                             # Test mocks
│
└── Documentation
    ├── README.md                          # Main documentation
    ├── QUICKSTART.md                      # Quick start guide
    ├── MIGRATION.md                       # Migration guide
    ├── CHANGELOG.md                       # Version history
    └── ARCHITECTURE.md                    # This file
```

---

## Data Flow Diagram

```
┌─────────────┐
│   User      │
│  (Speaker)  │
└──────┬──────┘
       │
       │ Audio
       │
       ▼
┌──────────────────────────────────────────────────────────────────┐
│                     TranscriptionOrchestrator                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Record Audio                                                 │
│  ┌──────────────┐                                               │
│  │ Audio Input  │ → Captures audio from microphone              │
│  └──────────────┘                                               │
│       │                                                         │
│       │ Audio bytes                                             │
│       ▼                                                         │
│                                                                  │
│  2. Transcribe                                                   │
│  ┌──────────────┐                                               │
│  │  Transcriber │ → Converts audio to text                      │
│  └──────────────┘                                               │
│       │                                                         │
│       │ Text                                                    │
│       ▼                                                         │
│                                                                  │
│  3. Process with LLM (optional)                                 │
│  ┌──────────────┐                                               │
│  │ LLM Processor │ → Enhances/corrects text                     │
│  └──────────────┘                                               │
│       │                                                         │
│       │ Processed text                                          │
│       ▼                                                         │
│                                                                  │
│  4. Output                                                      │
│  ┌──────────────┐                                               │
│  │Output Handler │ → Sends to multiple destinations             │
│  └──────────────┘                                               │
│       │                                                         │
│       ├─────────────┬─────────────┬─────────────┐               │
       │             │             │             │
       ▼             ▼             ▼             ▼
   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐
   │ Console │  │Clipboard│  │  File   │  │  App    │
   └─────────┘  └─────────┘  └─────────┘  └─────────┘
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## LiteLLM Multi-Provider Support

Both the Transcriber and LLM Processor use **LiteLLM** as a unified API, providing access to 100+ AI providers through a single interface.

### Supported Providers (Partial List)

| Category | Providers | Model Examples |
|----------|-----------|---------------|
| **Transcription** | OpenAI, Groq, Google, Azure, AssemblyAI | `openai/whisper-1`, `groq/whisper-large-v3`, `google/whisper` |
| **LLM** | OpenAI, Groq, Anthropic, Google, Azure, Cohere, HuggingFace | `openai/gpt-4`, `groq/llama-3`, `anthropic/claude-3`, `google/gemini-pro` |

### Provider Selection

To use a specific provider, simply change the model name prefix:

```yaml
# Use Groq (fast & free tier available)
transcription:
  model: groq/whisper-large-v3-turbo
llm:
  model: groq/meta-llama/llama-guard-4-12b

# Use OpenAI
transcription:
  model: openai/whisper-1
llm:
  model: openai/gpt-4

# Use Google
transcription:
  model: google/whisper
llm:
  model: google/gemini-pro

# Use Anthropic
llm:
  model: anthropic/claude-3-opus
```

For the complete list of supported providers, see: [LiteLLM Documentation](https://docs.litellm.ai/)

---

## Platform Support Matrix

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Platform Compatibility                       │
├─────────────────┬─────────┬─────────┬─────────┬────────────────────┤
│ Component       │ Windows │  macOS  │  Linux  │      Notes         │
├─────────────────┼─────────┼─────────┼─────────┼────────────────────┤
│ SoundDevice     │    ✓    │    ✓    │    ✓    │ Cross-platform     │
│ PyAudio         │    ✓    │    ✓    │    ✓    │ Alternative        │
│ CoreAudio       │    ✗    │    ✓    │    ✗    │ macOS native       │
│ WASAPI          │    ✓    │    ✗    │    ✗    │ Windows native     │
├─────────────────┼─────────┼─────────┼─────────┼────────────────────┤
│ Groq Transcriber│    ✓    │    ✓    │    ✓    │ Cloud API          │
│ Whisper Local   │    ✓    │    ✓    │    ✓    │ Local model        │
│ Azure           │    ✓    │    ✓    │    ✓    │ Cloud API          │
├─────────────────┼─────────┼─────────┼─────────┼────────────────────┤
│ LiteLLM         │    ✓    │    ✓    │    ✓    │ Multi-provider     │
│ OpenAI          │    ✓    │    ✓    │    ✓    │ Cloud API          │
│ Anthropic       │    ✓    │    ✓    │    ✓    │ Cloud API          │
├─────────────────┼─────────┼─────────┼─────────┼────────────────────┤
│ Stdout          │    ✓    │    ✓    │    ✓    │ Cross-platform     │
│ Clipboard       │    ✓    │    ✓    │    ✓    │ Cross-platform     │
│ File            │    ✓    │    ✓    │    ✓    │ Cross-platform     │
│ AutoIt          │    ✓    │    ✗    │    ✗    │ Windows only       │
│ AppleScript     │    ✗    │    ✓    │    ✗    │ macOS only         │
│ Xdotool         │    ✗    │    ✗    │    ✓    │ Linux only         │
├─────────────────┼─────────┼─────────┼─────────┼────────────────────┤
│ Keyboard        │    ✓    │    ✓    │    ✓*   │ *Requires sudo     │
└─────────────────┴─────────┴─────────┴─────────┴────────────────────┘
```

---

## Dependency Injection Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│                    Dependency Injection                         │
│                     (Constructor Injection)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Instead of:                                                   │
│  ┌─────────────────────────────────────┐                      │
│  │ orchestrator = Orchestrator()       │                      │
│  │ # Creates dependencies internally   │                      │
│  └─────────────────────────────────────┘                      │
│                                                                 │
│  We use:                                                       │
│  ┌─────────────────────────────────────┐                      │
│  │ audio = SoundDeviceAudioInput()     │                      │
│  │ transcriber = GroqTranscriber()     │                      │
│  │ llm = LiteLLMProcessor()            │                      │
│  │ output = StdoutOutputHandler()      │                      │
│  │                                     │                      │
│  │ orchestrator = Transcription        │                      │
│  │   .Orchestrator(                    │                      │
│  │     audio_input=audio,              │                      │
│  │     transcriber=transcriber,        │                      │
│  │     llm_processor=llm,              │                      │
│  │     output_handler=output           │                      │
│  │ )                                   │                      │
│  └─────────────────────────────────────┘                      │
│                                                                 │
│  Benefits:                                                     │
│  • Easy to test (inject mocks)                                 │
│  • Flexible composition                                        │
│  • Clear dependencies                                          │
│  • Better separation of concerns                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Extension Points

```
┌─────────────────────────────────────────────────────────────────┐
│                      Extension Points                           │
│                  (How to Extend the System)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. New Audio Input                                             │
│  ┌─────────────────────────────────────┐                      │
│  │ class MyAudioInput(AbstractAudioInput):                    │
│  │   async def start_recording(self):   │                      │
│  │     # Your implementation            │                      │
│  │   async def stop_recording(self):    │                      │
│  │     # Your implementation            │                      │
│  └─────────────────────────────────────┘                      │
│                                                                 │
│  2. New Transcriber                                             │
│  ┌─────────────────────────────────────┐                      │
│  │ class MyTranscriber(AbstractTranscriber):                 │
│  │   async def transcribe(self, audio): │                      │
│  │     # Your implementation            │                      │
│  └─────────────────────────────────────┘                      │
│                                                                 │
│  3. New LLM Processor                                           │
│  ┌─────────────────────────────────────┐                      │
│  │ class MyLLM(AbstractLLMProcessor):  │                      │
│  │   async def process(self, text):    │                      │
│  │     # Your implementation            │                      │
│  └─────────────────────────────────────┘                      │
│                                                                 │
│  4. New Output Handler                                          │
│  ┌─────────────────────────────────────┐                      │
│  │ class MyOutput(AbstractOutputHandler):                     │
│  │   async def output(self, text):      │                      │
│  │     # Your implementation            │                      │
│  └─────────────────────────────────────┘                      │
│                                                                 │
│  5. Register in Factory                                         │
│  ┌─────────────────────────────────────┐                      │
│  │ class TranscriptionFactory:         │                      │
│  │   @staticmethod                    │                      │
│  │   def create_audio_input(config):   │                      │
│  │     if config.type == "my_input":   │                      │
│  │       return MyAudioInput()         │                      │
│  └─────────────────────────────────────┘                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Configuration Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     Configuration Flow                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Load Configuration                                          │
│     │                                                           │
│     ├─→ Environment Variables (.env)                            │
│     ├─→ YAML File (config.yaml)                                 │
│     ├─→ CLI Arguments (--option value)                          │
│     │                                                           │
│     ▼                                                           │
│  2. Merge (Priority: CLI > YAML > Env > Defaults)              │
│     │                                                           │
│     ▼                                                           │
│  3. Validate (Type checking, required fields)                   │
│     │                                                           │
│     ▼                                                           │
│  4. Create Components (via Factory)                             │
│     │                                                           │
│     ├─→ Audio Input                                             │
│     ├─→ Transcriber                                             │
│     ├─→ LLM Processor                                           │
│     ├─→ Output Handler                                          │
│     └─→ Keyboard Listener                                       │
│     │                                                           │
│     ▼                                                           │
│  5. Initialize Orchestrator                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Testing Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│                      Testing Layers                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Unit Tests (tests/test_core.py)                         │   │
│  │ • Test individual components in isolation               │   │
│  │ • Use mocks for external dependencies                  │   │
│  │ • Fast execution                                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           │                                     │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Integration Tests (tests/test_integration.py)            │   │
│  │ • Test component interactions                           │   │
│  │ • Use real implementations where possible               │   │
│  │ • Slower execution                                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           │                                     │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ End-to-End Tests (future)                               │   │
│  │ • Test complete workflows                               │   │
│  │ • Real API calls (with test keys)                       │   │
│  │ • Slowest execution                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Summary

This architecture provides:

✅ **Modularity** - Each component has a single responsibility
✅ **Extensibility** - Easy to add new implementations
✅ **Testability** - Dependency injection enables easy mocking
✅ **Cross-platform** - Platform-specific code isolated
✅ **Type Safety** - Type hints throughout
✅ **Documentation** - Clear interfaces and docstrings
✅ **Configuration** - Flexible, layered configuration system
✅ **Error Handling** - Robust error handling at all levels

---

**Version:** 2.0.0
**Last Updated:** 2024
