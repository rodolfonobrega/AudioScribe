"""
Simple Terminal UI for AudioScribe.
All ASCII, no unicode.
"""
import os
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass

class TerminalUI:
    """Simple terminal user interface."""
    
    def __init__(self, verbose: bool = True):
        """
        Initialize terminal UI.
        
        Args:
            verbose: Enable verbose output
        """
        self.verbose = verbose
    
    def show_banner(self):
        """Display ASCII art banner."""
        print("""
 █████╗ ██╗   ██╗██████╗ ██╗ ██████╗ ███████╗ ██████╗██████╗ ██╗██████╗ ███████╗
██╔══██╗██║   ██║██╔══██╗██║██╔═══██╗██╔════╝██╔════╝██╔══██╗██║██╔══██╗██╔════╝
███████║██║   ██║██║  ██║██║██║   ██║███████╗██║     ██████╔╝██║██████╔╝█████╗  
██╔══██║██║   ██║██║  ██║██║██║   ██║╚════██║██║     ██╔══██╗██║██╔══██╗██╔══╝  
██║  ██║╚██████╔╝██████╔╝██║╚██████╔╝███████║╚██████╗██║  ██║██║██████╔╝███████╗
╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═╝ ╚═════╝ ╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝╚═════╝ ╚══════╝
    """)
    
    def show_compact_config(self, config, args, audio_input=None):
        """Display detailed configuration."""
        if not self.verbose:
            return
        
        # Handle both dict (legacy) and Config object
        if isinstance(config, dict):
            # For brevity, only implementing full detail extraction for Config object 
            # as that's what we are migrating to. Legacy dict support can remain minimal or be removed.
            # But to be safe let's just cast to a dummy object structure or handle fields manually.
            pass
        
        # Helper to safely get nested attrs/keys
        def get_val(obj, path, default='N/A'):
            try:
                val = obj
                for p in path.split('.'):
                    if isinstance(val, dict):
                        val = val.get(p)
                    else:
                        val = getattr(val, p)
                return val if val is not None else default
            except:
                return default

        # Extract values
        trans_provider = get_val(config, 'transcription.provider')
        trans_model = get_val(config, 'transcription.model')
        trans_lang = get_val(config, 'transcription.language')
        trans_temp = get_val(config, 'transcription.temperature')
        
        audio_sr = get_val(config, 'audio.sample_rate')
        audio_ch = get_val(config, 'audio.channels')
        audio_format = 'mono' if audio_ch == 1 else 'stereo'
        
        # Audio Device Name
        device_name = 'Default/Auto'
        if audio_input:
            try:
                device_name = audio_input._get_device_name()
            except:
                pass

        # LLM Settings
        llm_enabled_conf = get_val(config, 'llm.enabled', False)
        llm_arg_disabled = getattr(args, 'no_llm', False)
        llm_active = llm_enabled_conf and not llm_arg_disabled
        
        llm_provider = get_val(config, 'llm.provider')
        llm_model = get_val(config, 'llm.model')
        llm_temp = get_val(config, 'llm.temperature')
        llm_tokens = get_val(config, 'llm.max_tokens')

        # Output & Keyboard
        out_handlers = str(get_val(config, 'output.handlers'))
        out_arg = getattr(args, 'output', None)
        if out_arg:
            out_handlers = f"['{out_arg}'] (Override)"
            
        kb_hotkey = get_val(config, 'keyboard.hotkey')
        kb_mode = get_val(config, 'keyboard.mode')

        print(f"AudioScribe Configuration")
        print("=" * 60)
        
        print(f" [Audio Input]")
        print(f"  Device       : {device_name} (Index: {get_val(config, 'audio.device_index', 'Auto')})")
        print(f"  Format       : {audio_sr}Hz | {audio_ch}ch ({audio_format})")
        
        print(f"\n [Transcription]")
        print(f"  Provider     : {trans_provider}")
        print(f"  Model        : {trans_model}")
        print(f"  Language     : {trans_lang}")
        print(f"  Temperature  : {trans_temp}")
        
        print(f"\n [LLM Processing]")
        if llm_active:
            print(f"  Status       : ENABLED")
            print(f"  Provider     : {llm_provider}")
            print(f"  Model        : {llm_model}")
            print(f"  Temperature  : {llm_temp}")
            print(f"  Max Tokens   : {llm_tokens}")
        else:
            print(f"  Status       : DISABLED")
            
        print(f"\n [Output & Control]")
        print(f"  Handlers     : {out_handlers}")
        print(f"  Hotkey       : {kb_hotkey}")
        print(f"  Mode         : {kb_mode}")
        print("=" * 60)
        print()
    
    def update_status(self, status: str):
        """
        Update status in place.
        
        Args:
            status: Status message
        """
        if not self.verbose:
            return
        
        # Clear line and write new status
        print(f"\r{' ' * 70}\r", end="", flush=True)
        print(f"\r[{status}]", end="", flush=True)
    
    def update_live_status(self, state: str, details: str = ""):
        """
        Update live status with emojis in a single line.
        
        Args:
            state: Current state (ready, recording, processing, etc.)
            details: Additional details to display
        """
        if not self.verbose:
            return
        
        # Define emoji states
        states = {
            "ready": "🎙️  Ready",
            "recording": "🔴 Recording",
            "processing": "⚙️  Processing",
            "transcribing": "📝 Transcribing",
            "llm": "🤖 LLM Processing",
            "done": "✅ Done",
            "error": "❌ Error"
        }
        
        emoji_state = states.get(state, f"• {state}")
        status_line = f"{emoji_state}"
        if details:
            status_line += f" | {details}"
        
        # Clear line and write new status
        print(f"\r{' ' * 100}\r{status_line}", end="", flush=True)
    
    def clear_status_line(self):
        """Clear the current status line."""
        if self.verbose:
            print(f"\r{' ' * 100}\r", end="", flush=True)
    
    def show_result(self, text: str, raw_text: str = None):
        """
        Display transcription result.
        
        Args:
            text: Final processed text
            raw_text: Optional raw transcription (before LLM processing)
        """
        if not self.verbose:
            return
        
        self.clear_status_line()
        
        # Show raw transcription if provided
        if raw_text and raw_text != text:
            print(f"\n📝 Transcription: {raw_text}")
            print(f"🤖 LLM Output:    {text}\n")
        else:
            print(f"\n✅ Result: {text}\n")
    
    def show_error(self, error: str):
        """
        Display error message.
        
        Args:
            error: Error message
        """
        self.clear_status_line()
        print(f"\n❌ ERROR: {error}\n")
    
    def show_warning(self, warning: str):
        """
        Display warning message.
        
        Args:
            warning: Warning message
        """
        self.clear_status_line()
        print(f"\n⚠️  WARNING: {warning}\n")
    
    def show_info(self, info: str):
        """
        Display info message.
        
        Args:
            info: Info message
        """
        self.clear_status_line()
        print(f"\nℹ️  {info}\n")
    
    def show_success(self, message: str):
        """
        Display success message.
        
        Args:
            message: Success message
        """
        self.clear_status_line()
        print(f"\n✅ SUCCESS: {message}\n")
