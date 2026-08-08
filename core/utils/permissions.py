"""
Permission Manager - Proactive OS-level permission requests (microphone, accessibility).
Provides cross-platform permission detection and user-friendly guidance.
"""

import os
import platform
import subprocess
import sys
from typing import Dict, Optional, Tuple


class PermissionManager:
    """Cross-platform permission detection and requesting for audio & accessibility."""

    def __init__(self):
        self.system = platform.system()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_microphone_permission(self) -> Tuple[bool, Optional[str]]:
        """
        Check if the app likely has microphone access.

        Returns:
            (has_permission, user_friendly_guidance_string_or_None)
        """
        checker = getattr(self, f"_check_mic_{self.system.lower()}", self._check_mic_unknown)
        return checker()

    def request_microphone_permission(self) -> Tuple[bool, str]:
        """
        Attempt to guide the user to grant microphone permission.

        Returns:
            (success, message)
        """
        requester = getattr(self, f"_request_mic_{self.system.lower()}", self._request_mic_unknown)
        return requester()

    def check_accessibility_permission(self) -> Tuple[bool, Optional[str]]:
        """
        Check if the app has accessibility / input-monitoring permission
        (needed for simulated typing / hotkeys on macOS).
        """
        if self.system != "Darwin":
            return True, None  # Only relevant on macOS
        return self._check_accessibility_macos()

    def request_accessibility_permission(self) -> Tuple[bool, str]:
        """Guide the user through granting accessibility permission."""
        if self.system != "Darwin":
            return True, "Accessibility permission not required on this platform."
        return self._request_accessibility_macos()

    def get_paste_tool_availability(self) -> Dict[str, bool]:
        """
        Check which paste/clipboard tools are available on this system.

        Returns dict mapping tool name → available (bool).
        """
        system = self.system.lower()
        result = {}

        # Cross-platform Python libraries
        try:
            import pyperclip
            result["pyperclip"] = True
        except ImportError:
            result["pyperclip"] = False

        try:
            import pyautogui
            result["pyautogui"] = True
        except ImportError:
            result["pyautogui"] = False

        # Platform-specific tools
        if system == "windows":
            import shutil
            result["powershell"] = shutil.which("powershell") is not None
            try:
                import win32clipboard
                result["win32clipboard"] = True
            except ImportError:
                result["win32clipboard"] = False
            try:
                import autoit
                result["autoit"] = True
            except ImportError:
                result["autoit"] = False

        elif system == "darwin":
            import shutil
            result["pbcopy"] = shutil.which("pbcopy") is not None
            result["osascript"] = shutil.which("osascript") is not None

        elif system == "linux":
            import shutil
            result["xclip"] = shutil.which("xclip") is not None
            result["xsel"] = shutil.which("xsel") is not None
            result["xdotool"] = shutil.which("xdotool") is not None

        return result

    # ------------------------------------------------------------------
    # Microphone – Windows
    # ------------------------------------------------------------------

    def _check_mic_windows(self) -> Tuple[bool, Optional[str]]:
        """
        On Windows, we can test by attempting to open a sounddevice stream.
        If that fails with a PortAudio 'Invalid device' or 'permission' error,
        we guide the user to the Privacy settings.
        """
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            input_devices = [d for d in devices if d.get('max_input_channels', 0) > 0]
            if not input_devices:
                return False, (
                    "Nenhum microfone detectado.\n"
                    "  • Verifique se o microfone está conectado e ligado.\n"
                    "  • Abra: Configurações > Privacidade e Segurança > Microfone\n"
                    "  • Certifique-se de que 'Acesso ao microfone' está ATIVADO.\n"
                    "  • Abaixo, verifique se o seu Terminal/Python está na lista e com permissão LIGADA."
                )

            # Try to actually open a stream on the first input device
            for dev in input_devices:
                try:
                    idx = dev.get('name')  # sounddevice 0.x returns name as index; try real index
                    # Actually, query_devices returns list, use enumerate
                    break
                except Exception:
                    continue

            # Attempt opening an actual input stream on available input devices
            last_error = None
            for i, dev in enumerate(devices):
                if dev.get('max_input_channels', 0) > 0:
                    for sr in [16000, 44100, 48000]:
                        for ch in [1, 2]:
                            try:
                                def _cb(*args): pass
                                with sd.InputStream(samplerate=sr, channels=ch, dtype='float32', device=i, callback=_cb):
                                    return True, None  # Success: verified working microphone stream
                            except Exception as e:
                                last_error = str(e)
                                continue

            return False, (
                f"O dispositivo de áudio está presente mas o fluxo não pôde ser aberto ({last_error}).\n"
                "  • Abra: Configurações > Privacidade e Segurança > Microfone\n"
                "  • Ative 'Acesso ao microfone'.\n"
                "  • Na lista de aplicativos, ative a permissão para 'Python' ou 'Terminal'."
            )

        except ImportError:
            return False, (
                "Biblioteca 'sounddevice' não encontrada.\n"
                "Execute: pip install sounddevice"
            )
        except Exception as e:
            return False, (
                f"Não foi possível verificar o microfone: {e}\n"
                "  • Verifique: Configurações > Privacidade e Segurança > Microfone"
            )

    def _request_mic_windows(self) -> Tuple[bool, str]:
        """Open Windows microphone privacy settings."""
        try:
            subprocess.run(["explorer.exe", "ms-settings:privacy-microphone"], check=False)
            return True, (
                "🔧 Aberto: Configurações > Privacidade > Microfone.\n"
                "   1. Ative 'Acesso ao microfone' (LIGADO).\n"
                "   2. Na lista de apps, ative para 'Python' ou seu Terminal.\n"
                "   3. Reinicie o AudioScribe após ativar."
            )
        except Exception as e:
            return False, (
                f"Não foi possível abrir as configurações automaticamente ({e}).\n"
                "Navegue manualmente: Configurações > Privacidade e Segurança > Microfone"
            )

    # ------------------------------------------------------------------
    # Microphone – macOS
    # ------------------------------------------------------------------

    def _check_mic_macos(self) -> Tuple[bool, Optional[str]]:
        """
        On macOS, check if Terminal has microphone permission via TCC database.
        Also attempt a sounddevice stream probe.
        """
        # First check: try sounddevice stream
        has_hardware = False
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                if dev.get('max_input_channels', 0) > 0:
                    has_hardware = True
                    try:
                        def _cb(*args):
                            pass
                        with sd.InputStream(samplerate=16000, channels=1, dtype='float32',
                                           device=i, callback=_cb):
                            pass
                        return True, None
                    except Exception as e:
                        err = str(e).lower()
                        if any(kw in err for kw in ['permission', 'not authorized', 'tcc', 'denied']):
                            return False, (
                                "❌ O Terminal não tem permissão de acesso ao microfone.\n"
                                "  • Abra: Ajustes do Sistema > Privacidade e Segurança > Microfone\n"
                                "  • Ative a chave ao lado do seu app de Terminal (Terminal, iTerm2, VS Code).\n"
                                "  • Reinicie o Terminal após ativar."
                            )
                        continue
                break
        except ImportError:
            pass
        except Exception:
            pass

        if not has_hardware:
            return False, (
                "Nenhum microfone detectado.\n"
                "  • Verifique se o microfone está conectado.\n"
                "  • Abra: Ajustes do Sistema > Privacidade e Segurança > Microfone"
            )

        # If we get here, assume permission is OK (stream opened or no clear error)
        return True, None

    def _request_mic_macos(self) -> Tuple[bool, str]:
        """Guide user to macOS microphone privacy settings."""
        try:
            subprocess.run([
                "open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
            ], check=False)
            return True, (
                "🔧 Aberto: Ajustes do Sistema > Privacidade > Microfone.\n"
                "   1. Ative a chave ao lado de 'Terminal' (ou iTerm2/VS Code).\n"
                "   2. Se o app não estiver listado, arraste-o para a lista ou clique '+'.\n"
                "   3. Reinicie o Terminal após ativar a permissão."
            )
        except Exception:
            return False, (
                "Abra manualmente: Ajustes do Sistema > Privacidade e Segurança > Microfone"
            )

    # ------------------------------------------------------------------
    # Microphone – Linux
    # ------------------------------------------------------------------

    def _check_mic_linux(self) -> Tuple[bool, Optional[str]]:
        """On Linux, ALSA/PulseAudio usually don't have per-app permission — just check hardware."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            input_devices = [d for d in devices if d.get('max_input_channels', 0) > 0]
            if not input_devices:
                return False, (
                    "Nenhum microfone detectado.\n"
                    "  • Verifique a conexão do microfone.\n"
                    "  • Teste com: arecord -d 5 test.wav\n"
                    "  • Se usar PulseAudio: pactl list sources short\n"
                    "  • Instale o PortAudio se necessário: sudo apt-get install libportaudio2"
                )

            # Probe first input device
            for i, dev in enumerate(devices):
                if dev.get('max_input_channels', 0) > 0:
                    try:
                        def _cb(*args):
                            pass
                        with sd.InputStream(samplerate=16000, channels=1, dtype='float32',
                                           device=i, callback=_cb):
                            pass
                        return True, None
                    except Exception as e:
                        return False, (
                            f"Microfone detectado mas não foi possível abrir o stream: {e}\n"
                            "  • Verifique permissões do dispositivo (/dev/snd/*).\n"
                            "  • Adicione seu usuário ao grupo 'audio': sudo usermod -aG audio $USER\n"
                            "  • Faça logout e login novamente."
                        )
        except ImportError:
            return False, (
                "Biblioteca 'sounddevice' não encontrada.\n"
                "Execute: pip install sounddevice"
            )
        except Exception as e:
            return False, (
                f"Erro ao acessar áudio: {e}\n"
                "  • Instale o PortAudio: sudo apt-get install libportaudio2\n"
                "  • Verifique se o microfone funciona com 'arecord -d 3 teste.wav'"
            )

        return True, None

    def _request_mic_linux(self) -> Tuple[bool, str]:
        """Linux typically doesn't need per-app mic permission, but guide on audio group."""
        import shutil
        if shutil.which("pavucontrol"):
            subprocess.Popen(["pavucontrol"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, (
                "🔧 Aberto: Pavucontrol (controle de volume PulseAudio).\n"
                "   Verifique na aba 'Input Devices' se o microfone está ativo e com volume > 0."
            )
        return True, (
            "ℹ️  No Linux, permissões de microfone são controladas via grupos de usuário.\n"
            "   Execute 'sudo usermod -aG audio $USER' e faça logout/login se houver problemas."
        )

    # ------------------------------------------------------------------
    # Microphone – Unknown platform
    # ------------------------------------------------------------------

    def _check_mic_unknown(self) -> Tuple[bool, Optional[str]]:
        return False, f"Plataforma '{self.system}' não é suportada para verificação automática."

    def _request_mic_unknown(self) -> Tuple[bool, str]:
        return False, f"Plataforma '{self.system}' não é suportada para solicitação de permissão."

    # ------------------------------------------------------------------
    # Accessibility – macOS
    # ------------------------------------------------------------------

    def _check_accessibility_macos(self) -> Tuple[bool, Optional[str]]:
        """Check if Terminal has Accessibility permission on macOS."""
        try:
            result = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get name of first process'],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode != 0:
                stderr_lower = result.stderr.lower()
                if "not allowed" in stderr_lower or "assistive" in stderr_lower:
                    return False, (
                        "❌ O Terminal não tem permissão de Acessibilidade.\n"
                        "  • Abra: Ajustes do Sistema > Privacidade e Segurança > Acessibilidade\n"
                        "  • Ative a chave ao lado do seu app de Terminal.\n"
                        "  • Se não estiver listado, clique '+' e adicione o app."
                    )
            return True, None
        except Exception as e:
            return False, f"Não foi possível verificar acessibilidade: {e}"

    def _request_accessibility_macos(self) -> Tuple[bool, str]:
        """Open macOS Accessibility privacy settings."""
        try:
            subprocess.run([
                "open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
            ], check=False)
            return True, (
                "🔧 Aberto: Ajustes do Sistema > Privacidade > Acessibilidade.\n"
                "   1. Clique no cadeado 🔒 e autentique para fazer alterações.\n"
                "   2. Ative a chave ao lado do seu Terminal (ou iTerm2/VS Code).\n"
                "   3. Reinicie o Terminal após ativar."
            )
        except Exception:
            return False, (
                "Abra manualmente: Ajustes do Sistema > Privacidade e Segurança > Acessibilidade"
            )
