"""
Preflight Checker - Validates environment, permissions, dependencies, and hardware before execution.
Provides user-friendly diagnostics and step-by-step resolution instructions.
"""

import os
import platform
import shutil
import subprocess
import sys
from typing import List, Dict, Tuple, Optional

from core.utils.permissions import PermissionManager


def safe_print(text: str) -> None:
    """Print text safely handling Windows terminal encoding issues."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Replace non-encodable emojis/characters with ASCII fallback
        clean_text = text.encode('ascii', errors='replace').decode('ascii')
        print(clean_text)


class PreflightChecker:
    """System and environment pre-flight validator."""

    def __init__(self, config=None):
        self.config = config
        self.system = platform.system()
        self.errors: List[Dict[str, str]] = []
        self.warnings: List[Dict[str, str]] = []

    def check_all(self) -> bool:
        """
        Run all pre-flight checks.
        
        Returns:
            True if system is ready (no critical errors), False otherwise.
        """
        self.errors.clear()
        self.warnings.clear()

        self.check_api_keys()
        self.check_audio_hardware()
        self.check_os_permissions()
        self.check_output_handlers()
        self.check_keyboard_listener()
        self.check_updates()

        return len(self.errors) == 0

    def check_desktop_engine(self) -> bool:
        """Check only services owned by the Python engine in desktop mode.

        Electron owns microphone permissions, device selection, and hotkeys.
        Keeping those probes out of the sidecar prevents Python/PortAudio from
        touching audio hardware in the non-CLI application.
        """
        self.errors.clear()
        self.warnings.clear()

        self.check_api_keys()
        self.check_output_handlers()
        self.check_updates()

        return len(self.errors) == 0

    def check_updates(self) -> None:
        """Check GitHub for new AudioScribe release."""
        try:
            from core.utils.updater import VersionChecker
            checker = VersionChecker()
            update = checker.check_for_updates(timeout=2.0)
            if update:
                self.warnings.append({
                    "component": "Update Available",
                    "issue": f"A new version of AudioScribe is available (v{update['latest_version']}). Current version: v{update['current_version']}.",
                    "remediation": f"Download latest release at {update['release_url']}"
                })
        except Exception:
            pass

    def check_api_keys(self) -> None:
        """Check if required API keys are configured."""
        groq_key = os.getenv("GROQ_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        litellm_key = os.getenv("LITELLM_API_KEY")
        
        if self.config:
            trans_key = getattr(self.config.transcription, 'api_key', None)
            trans_base_url = getattr(self.config.transcription, 'base_url', None) or os.getenv('TRANSCRIPTION_BASE_URL')
            llm = getattr(self.config, 'llm', None)
            llm_key = getattr(llm, 'api_key', None) if llm else None
            llm_base_url = getattr(llm, 'base_url', None) if llm else None
            llm_enabled = bool(llm and getattr(llm, 'enabled', True))
            local_transcription = str(getattr(self.config.transcription, 'provider', '')).lower() in {
                'local_whisper', 'whisper_local', 'whisper', 'parakeet', 'local_parakeet'
            }

            if not local_transcription and not trans_base_url and not trans_key and not groq_key and not openai_key and not litellm_key:
                self.errors.append({
                    "component": "API Keys / Transcrição",
                    "issue": "A transcrição não possui chave de API nem endpoint local configurado.",
                    "remediation": "Configure GROQ_API_KEY, OPENAI_API_KEY ou um endpoint de speech-to-text local."
                })

            if llm_enabled and not llm_base_url and not llm_key and not groq_key and not openai_key and not litellm_key:
                self.errors.append({
                    "component": "API Keys / LLM",
                    "issue": "O pós-processamento LLM está ativo, mas não possui chave ou endpoint configurado.",
                    "remediation": "Configure LLM_API_KEY/GROQ_API_KEY ou desative o pós-processamento."
                })
        else:
            keys_found = any([groq_key, openai_key, litellm_key])
            if not keys_found:
                if not self.config or getattr(self.config.transcription, 'base_url', None) is None:
                    self.warnings.append({
                        "component": "API Keys",
                        "issue": "No API keys detected in your environment.",
                        "remediation": (
                            "Get your free Groq API key at https://console.groq.com/keys "
                            "and add GROQ_API_KEY=gsk_... to your .env file."
                        )
                    })

    def check_audio_hardware(self) -> None:
        """Check microphone availability and sounddevice library."""
        try:
            import sounddevice as sd
            if sd is None:
                self.warnings.append({
                    "component": "Audio Input (sounddevice)",
                    "issue": "The 'sounddevice' library is not installed.",
                    "remediation": "Install dependencies by running: `pip install -r requirements.txt`"
                })
                return

            devices = sd.query_devices()
            input_devices = [d for d in devices if d.get('max_input_channels', 0) > 0]
            
            if not input_devices:
                self.errors.append({
                    "component": "Audio Input",
                    "issue": "No audio input device (microphone) was found.",
                    "remediation": (
                        "1. Verify that a microphone is connected and enabled.\n"
                        "2. If running inside Docker/VM, ensure audio passthrough (ALSA/PulseAudio) is configured.\n"
                        "3. On macOS, ensure Terminal has Microphone permission in System Settings."
                    )
                })
        except Exception as e:
            self.errors.append({
                "component": "Audio Input (sounddevice)",
                "issue": f"Failed to access audio subsystem: {e}",
                "remediation": (
                    "On Linux, install PortAudio: `sudo apt-get install libportaudio2`\n"
                    "On macOS, check microphone access under System Settings > Privacy & Security."
                )
            })

    def check_os_permissions(self) -> None:
        """Check OS-specific permissions: microphone, accessibility, display server."""
        perm_manager = PermissionManager()

        # --- Microphone permission (all platforms) ---
        has_mic, mic_guidance = perm_manager.check_microphone_permission()
        if not has_mic and mic_guidance:
            self.errors.append({
                "component": "Microphone Permission",
                "issue": mic_guidance.split('\n')[0] if '\n' in mic_guidance else mic_guidance,
                "remediation": mic_guidance[mic_guidance.index('•') if '•' in mic_guidance else 0:]
            })

        # --- Accessibility permission (macOS) ---
        if self.system == "Darwin":
            has_acc, acc_guidance = perm_manager.check_accessibility_permission()
            if not has_acc and acc_guidance:
                self.warnings.append({
                    "component": "macOS Permissions (Accessibility)",
                    "issue": "Terminal/Python lacks Accessibility permissions to simulate typing.",
                    "remediation": (
                        "1. Open: System Settings > Privacy & Security > Accessibility.\n"
                        "2. Toggle the switch ON for your Terminal app (e.g., Terminal, iTerm2, VS Code).\n"
                        "3. If your app is not listed, click '+' to add it manually."
                    )
                })

        # --- Display server (Linux) ---
        if self.system == "Linux":
            session_type = os.getenv("XDG_SESSION_TYPE", "").lower()
            if session_type == "wayland":
                self.warnings.append({
                    "component": "Linux Display Server (Wayland)",
                    "issue": "Wayland session detected. Simulated typing (xdotool/pyautogui) may be restricted.",
                    "remediation": (
                        "Recommended to use `clipboard` or `console` output handler:\n"
                        "  python main.py --output clipboard\n"
                        "Or launch your Linux session in Xorg/X11 mode from the login screen."
                    )
                })

    def check_output_handlers(self) -> None:
        """Check output handler availability based on config or defaults."""
        handlers = ["stdout"]
        if self.config and hasattr(self.config, 'output'):
            handlers = self.config.output.handlers

        for handler in handlers:
            h = handler.lower().strip()
            if h == "xdotool" and self.system == "Linux":
                if not shutil.which("xdotool"):
                    self.errors.append({
                        "component": "Output Handler (xdotool)",
                        "issue": "The 'xdotool' package is not installed on Linux.",
                        "remediation": "Install it by running: `sudo apt-get install xdotool` (Debian/Ubuntu) or `sudo dnf install xdotool` (Fedora)."
                    })
            elif h == "clipboard" and self.system == "Linux":
                if not shutil.which("xclip") and not shutil.which("xsel"):
                    self.warnings.append({
                        "component": "Output Handler (clipboard)",
                        "issue": "Neither 'xclip' nor 'xsel' was found on Linux.",
                        "remediation": "For clipboard support on Linux, install xclip: `sudo apt-get install xclip`"
                    })
            elif h == "autoit" and self.system != "Windows":
                self.errors.append({
                    "component": "Output Handler (AutoIt)",
                    "issue": "AutoIt handler is only supported on Windows.",
                    "remediation": "Use '--output pyautogui' or '--output clipboard'."
                })
            elif h == "applescript" and self.system != "Darwin":
                self.errors.append({
                    "component": "Output Handler (AppleScript)",
                    "issue": "AppleScript handler is only supported on macOS.",
                    "remediation": "Use '--output pyautogui' or '--output clipboard'."
                })

    def check_keyboard_listener(self) -> None:
        """Check if keyboard hotkey listener can run."""
        if self.system == "Linux":
            # Check if running as root for 'keyboard' module
            if os.geteuid() != 0:
                # Check if pynput is installed
                try:
                    import pynput
                except ImportError:
                    self.warnings.append({
                        "component": "Keyboard Listener (Linux)",
                        "issue": "The 'keyboard' package on Linux requires root (sudo) privileges for /dev/input/evdev.",
                        "remediation": (
                            "Install 'pynput' to listen for hotkeys without sudo:\n"
                            "  pip install pynput\n"
                            "Or run the app with sudo:\n"
                            "  sudo python main.py"
                        )
                    })

    def print_report(self) -> None:
        """Print stylized pre-flight report."""
        if not self.errors and not self.warnings:
            safe_print("[OK] Pre-flight Check: All systems ready.\n")
            return

        safe_print("\n" + "=" * 65)
        safe_print(" [PRE-FLIGHT CHECK] - SYSTEM DIAGNOSTICS")
        safe_print("=" * 65)

        if self.errors:
            safe_print(f"\n[CRITICAL ERRORS FOUND] ({len(self.errors)}):\n")
            for i, err in enumerate(self.errors, 1):
                safe_print(f" [{i}] Component  : {err['component']}")
                safe_print(f"     Issue      : {err['issue']}")
                safe_print("     Remediation:")
                for line in err['remediation'].split('\n'):
                    safe_print(f"       {line}")
                safe_print("")

        if self.warnings:
            safe_print(f"\n[CONFIGURATION WARNINGS] ({len(self.warnings)}):\n")
            for i, warn in enumerate(self.warnings, 1):
                safe_print(f" [{i}] Component  : {warn['component']}")
                safe_print(f"     Issue      : {warn['issue']}")
                safe_print("     Remediation:")
                for line in warn['remediation'].split('\n'):
                    safe_print(f"       {line}")
                safe_print("")

        safe_print("=" * 65 + "\n")
