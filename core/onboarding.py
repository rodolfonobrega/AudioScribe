"""
Onboarding Wizard - First-run guided setup for AudioScribe.
Walks new users through API key configuration, microphone validation,
output handler selection, and permission granting.
"""

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Optional

from core.utils.permissions import PermissionManager
from core.utils.preflight import safe_print

# ---------------------------------------------------------------------------
# Onboarding state persistence
# ---------------------------------------------------------------------------

ONBOARDING_MARKER_DIR = Path.home() / ".audioscribe"
ONBOARDING_MARKER_FILE = ONBOARDING_MARKER_DIR / ".onboarding_complete"


def is_onboarding_complete() -> bool:
    """Check if the onboarding wizard has been completed."""
    return ONBOARDING_MARKER_FILE.exists()


def mark_onboarding_complete() -> None:
    """Persist the flag that onboarding has been completed."""
    ONBOARDING_MARKER_DIR.mkdir(parents=True, exist_ok=True)
    ONBOARDING_MARKER_FILE.touch()


def reset_onboarding() -> None:
    """Remove the onboarding marker (allows re-running the wizard)."""
    if ONBOARDING_MARKER_FILE.exists():
        ONBOARDING_MARKER_FILE.unlink()


# ---------------------------------------------------------------------------
# Interactive input helper
# ---------------------------------------------------------------------------

def _prompt(prompt_text: str, default: str = "") -> str:
    """Prompt for user input. Returns stripped string."""
    try:
        if default:
            value = input(f"  {prompt_text} [{default}]: ").strip()
            return value if value else default
        return input(f"  {prompt_text}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n\nOnboarding interrompido. Use --no-onboarding para pular na próxima execução.")
        sys.exit(0)


def _prompt_yes_no(prompt_text: str, default_yes: bool = True) -> bool:
    """Prompt for a yes/no answer."""
    default_hint = "S/n" if default_yes else "s/N"
    answer = _prompt(f"{prompt_text} ({default_hint})", default="").lower()
    if not answer:
        return default_yes
    return answer in ("s", "sim", "y", "yes", "1")


# ---------------------------------------------------------------------------
# Onboarding wizard
# ---------------------------------------------------------------------------

class OnboardingWizard:
    """Guided first-run setup wizard for AudioScribe."""

    def __init__(self, config=None):
        self.config = config
        self.system = platform.system()
        self.perm_manager = PermissionManager()

        # Results collected during wizard
        self.api_key_set: bool = False
        self.mic_ok: bool = False
        self.accessibility_ok: bool = True  # Non-macOS defaults to True
        self.output_handler_configured: bool = False

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> bool:
        """
        Execute the full onboarding wizard.
        Returns True if the system is ready to proceed, False if critical blockers remain.
        """
        self._print_header()

        # Step 1: Check / request microphone permission
        self._step_microphone()

        # Step 2: Accessibility (macOS only)
        if self.system == "Darwin":
            self._step_accessibility()

        # Step 3: API key
        self._step_api_key()

        # Step 4: Output handler
        self._step_output_handler()

        # Step 5: Paste tools (Linux)
        if self.system == "Linux":
            self._step_paste_tools_linux()

        # Final summary
        ready = self._print_summary()

        if ready:
            mark_onboarding_complete()
        else:
            print("\n⚠️  Alguns passos precisam de atenção antes de usar o AudioScribe.")
            print("   Execute novamente para repetir a verificação.\n")

        return ready

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    def _step_microphone(self) -> None:
        """Step 1: Validate microphone access."""
        safe_print("\n" + "─" * 55)
        safe_print(" PASSO 1/4: VERIFICAÇÃO DO MICROFONE")
        safe_print("─" * 55)

        has_perm, guidance = self.perm_manager.check_microphone_permission()

        if has_perm:
            safe_print("✅ Microfone detectado e funcionando.\n")
            self.mic_ok = True
            return

        # Microphone issue detected
        safe_print(f"{guidance}\n")

        if self.system in ("Windows", "Darwin"):
            want_open = _prompt_yes_no(
                "Deseja abrir as configurações de privacidade agora?", default_yes=True
            )
            if want_open:
                ok, msg = self.perm_manager.request_microphone_permission()
                safe_print(f"\n{msg}\n")

        want_retry = _prompt_yes_no(
            "Após verificar, deseja testar o microfone novamente?", default_yes=True
        )
        if want_retry:
            has_perm, guidance = self.perm_manager.check_microphone_permission()
            if has_perm:
                safe_print("✅ Microfone agora está funcionando!\n")
                self.mic_ok = True
                return
            safe_print(f"Ainda com problema: {guidance}\n")

        self.mic_ok = has_perm

    def _step_accessibility(self) -> None:
        """Step 2 (macOS): Accessibility permission for simulated typing."""
        safe_print("\n" + "─" * 55)
        safe_print(" PASSO 2/4: PERMISSÃO DE ACESSIBILIDADE (macOS)")
        safe_print("─" * 55)

        has_perm, guidance = self.perm_manager.check_accessibility_permission()

        if has_perm:
            safe_print("✅ Permissão de Acessibilidade OK.\n")
            self.accessibility_ok = True
            return

        safe_print(f"{guidance}\n")
        want_open = _prompt_yes_no(
            "Deseja abrir as configurações de Acessibilidade agora?", default_yes=True
        )
        if want_open:
            _, msg = self.perm_manager.request_accessibility_permission()
            safe_print(f"\n{msg}\n")

        want_retry = _prompt_yes_no("Testar permissão novamente?", default_yes=True)
        if want_retry:
            has_perm, _ = self.perm_manager.check_accessibility_permission()
            self.accessibility_ok = has_perm
            if has_perm:
                safe_print("✅ Permissão de Acessibilidade OK.\n")
        else:
            self.accessibility_ok = False

    def _step_api_key(self) -> None:
        """Step 3: Help user configure an API key."""
        safe_print("\n" + "─" * 55)
        safe_print(" PASSO 3/4: CONFIGURAÇÃO DE API KEY")
        safe_print("─" * 55)

        # Check existing keys
        providers = {
            "groq": os.getenv("GROQ_API_KEY"),
            "openai": os.getenv("OPENAI_API_KEY"),
            "google": os.getenv("GOOGLE_API_KEY"),
            "anthropic": os.getenv("ANTHROPIC_API_KEY"),
        }
        configured = [k.upper() for k, v in providers.items() if v]

        if configured:
            safe_print(f"✅ Chave(s) já configurada(s): {', '.join(configured)}")
            safe_print("   (As chaves são detectadas via variáveis de ambiente)\n")

            if not _prompt_yes_no("Deseja adicionar/configurar outra chave?", default_yes=False):
                self.api_key_set = True
                return
        else:
            safe_print("ℹ️  Nenhuma chave de API detectada.\n")
            safe_print("   O AudioScribe usa LiteLLM e funciona com 100+ provedores.")
            safe_print("   Recomendação para começar: Groq (grátis, rápido).\n")
            safe_print("   ➜ Crie sua chave gratuita em: https://console.groq.com/keys\n")

        safe_print("   Formatos aceitos:")
        safe_print("     groq/...        → GROQ_API_KEY")
        safe_print("     openai/...      → OPENAI_API_KEY")
        safe_print("     google/...      → GOOGLE_API_KEY")
        safe_print("     anthropic/...   → ANTHROPIC_API_KEY")
        safe_print("     (Ou configure um endpoint local com TRANSCRIPTION_BASE_URL)\n")

        choice = _prompt("Digite o nome da variável (ex: GROQ_API_KEY) ou ENTER para pular",
                         default="GROQ_API_KEY").strip()

        if choice:
            key_value = _prompt(f"Cole sua chave para {choice}", default="").strip()
            if key_value:
                # Write to .env file
                env_path = Path.cwd() / ".env"
                env_exists = env_path.exists()

                # Read existing content
                existing_lines = {}
                if env_exists:
                    with open(env_path, "r") as f:
                        for line in f:
                            line = line.strip()
                            if "=" in line and not line.startswith("#"):
                                k, v = line.split("=", 1)
                                existing_lines[k.strip()] = v.strip()

                existing_lines[choice] = key_value

                with open(env_path, "w") as f:
                    for k, v in existing_lines.items():
                        f.write(f"{k}={v}\n")

                # Set in current process
                os.environ[choice] = key_value
                safe_print(f"\n✅ {choice} salva em {env_path}\n")
                self.api_key_set = True
                return

        self.api_key_set = len(configured) > 0
        if not self.api_key_set:
            safe_print("\n⚠️  Nenhuma chave configurada. O AudioScribe não funcionará sem API key.\n")

    def _step_output_handler(self) -> None:
        """Step 4: Select output handler."""
        safe_print("\n" + "─" * 55)
        safe_print(" PASSO 4/4: MÉTODO DE SAÍDA (OUTPUT)")
        safe_print("─" * 55)

        tools = self.perm_manager.get_paste_tool_availability()

        safe_print("   Como você quer que o texto transcrito seja entregue?\n")

        options = [
            ("1", "console", "Exibir apenas no terminal (mais simples)"),
            ("2", "clipboard", "Copiar para área de transferência (Ctrl+V manual)"),
        ]

        # PyAutoGUI is cross-platform
        if tools.get("pyautogui") and tools.get("pyperclip"):
            options.append(("3", "pyautogui", "Colar automaticamente no campo ativo (recomendado)"))

        if self.system == "Windows":
            if tools.get("autoit"):
                options.append(("4", "autoit", "AutoIt (Windows - rápido)"))
        elif self.system == "Darwin":
            if tools.get("osascript"):
                options.append(("4", "applescript", "AppleScript (macOS nativo)"))
        elif self.system == "Linux":
            if tools.get("xdotool"):
                options.append(("4", "xdotool", "xdotool (Linux X11)"))

        for num, handler, desc in options:
            safe_print(f"   [{num}] {desc} (--output {handler})")

        safe_print("")

        default_choice = "3" if len(options) >= 3 else "2"
        choice = _prompt("Escolha uma opção", default=default_choice)

        handler_map = {opt[0]: opt[1] for opt in options}
        selected_handler = handler_map.get(choice, "clipboard")

        # Patch config if available
        if self.config and hasattr(self.config, 'output'):
            self.config.output.handlers = [selected_handler]

        safe_print(f"\n✅ Saída configurada: {selected_handler}\n")
        self.output_handler_configured = True

    def _step_paste_tools_linux(self) -> None:
        """Linux bonus step: ensure paste tools are installed."""
        safe_print("\n" + "─" * 55)
        safe_print(" DEPENDÊNCIAS LINUX")
        safe_print("─" * 55)

        missing = []
        if not shutil.which("xclip") and not shutil.which("xsel"):
            missing.append("xclip (para clipboard)")
        if not shutil.which("xdotool"):
            missing.append("xdotool (para auto-digitação)")

        if missing:
            safe_print(f"⚠️  Ferramentas ausentes: {', '.join(missing)}")
            safe_print("   Instale com: sudo apt-get install xclip xdotool\n")
        else:
            safe_print("✅ Ferramentas de clipboard/input presentes.\n")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _print_summary(self) -> bool:
        """Print final summary and return True if ready."""
        safe_print("\n" + "=" * 55)
        safe_print(" RESUMO DO ONBOARDING")
        safe_print("=" * 55)

        items = [
            ("Microfone", self.mic_ok),
            ("Acessibilidade (macOS)", self.accessibility_ok),
            ("API Key", self.api_key_set),
            ("Método de saída", self.output_handler_configured),
        ]

        all_ok = True
        for name, status in items:
            if status:
                safe_print(f"  ✅ {name}")
            else:
                safe_print(f"  ❌ {name}")
                all_ok = False

        safe_print("")

        if not self.mic_ok:
            safe_print("⚠️  Microfone não configurado. O AudioScribe pode não conseguir capturar áudio.")
            all_ok = False

        if not self.api_key_set:
            safe_print("⚠️  Sem API key. Configure GROQ_API_KEY no arquivo .env para usar transcrição.")
            all_ok = False

        return all_ok

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _print_header(self) -> None:
        """Print welcome banner."""
        safe_print("\n")
        safe_print("╔" + "═" * 53 + "╗")
        safe_print("║" + "  🎤 Bem-vindo ao AudioScribe - Configuração Inicial  ".ljust(59) + "║")
        safe_print("╠" + "═" * 53 + "╣")
        safe_print("║" + "  Este assistente vai te guiar na configuração       ".ljust(59) + "║")
        safe_print("║" + "  do microfone, API key e método de saída.           ".ljust(59) + "║")
        safe_print("╚" + "═" * 53 + "╝")
        safe_print("")
        safe_print("  📝 A qualquer momento pressione Ctrl+C para sair.")
        safe_print("  🔄 Para refazer a configuração, delete o arquivo:")
        safe_print(f"     {ONBOARDING_MARKER_FILE}")
        safe_print("")


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def run_onboarding_if_needed(config=None, cli_args=None) -> bool:
    """
    Run the onboarding wizard if it hasn't been completed yet.
    Respects --no-onboarding flag and --server mode.

    Args:
        config: Optional Config object to patch during onboarding
        cli_args: Optional argparse.Namespace with user-provided flags

    Returns:
        True if ready to proceed, False if blocked.
    """
    # Skip if onboarding was already completed
    if is_onboarding_complete():
        return True

    # Skip if explicitly disabled
    if cli_args and getattr(cli_args, 'no_onboarding', False):
        return True

    # Skip in server/IPC mode (managed by Electron GUI)
    if cli_args and getattr(cli_args, 'server', False):
        return True

    # Skip if user is already passing a specific config or has keys set
    # (advanced users who bypass onboarding)
    if cli_args and getattr(cli_args, 'text', None):
        return True
    if cli_args and getattr(cli_args, 'file', None):
        return True

    # Check if user clearly has keys configured already
    keys_present = any([
        os.getenv("GROQ_API_KEY"),
        os.getenv("OPENAI_API_KEY"),
        os.getenv("GOOGLE_API_KEY"),
        os.getenv("ANTHROPIC_API_KEY"),
        os.getenv("LITELLM_API_KEY"),
    ])

    if keys_present and cli_args and getattr(cli_args, 'output', None):
        # User has both keys and output preference — they know what they're doing
        mark_onboarding_complete()
        return True

    wizard = OnboardingWizard(config=config)
    return wizard.run()
