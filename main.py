"""
AudioScribe - Cross-platform Audio Transcription Tool
"""

import argparse
import sys
import time
from typing import Optional

from config.settings import load_config
from core.factory import TranscriptionFactory
from core.ui import TerminalUI

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is not required


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='AudioScribe - Cross-platform Audio Transcription Tool'
    )
    
    parser.add_argument('--config', type=str, default=None, help='Path to configuration file')
    parser.add_argument('--output', type=str, choices=['console', 'clipboard', 'pyautogui', 'autoit', 'applescript', 'xdotool'], help='Output handler type')
    parser.add_argument('--device', type=int, help='Audio input device index')
    parser.add_argument('--no-keyboard', action='store_true', help='Disable keyboard listener')
    parser.add_argument('--file', type=str, help='Process audio file instead of recording')
    parser.add_argument('--text', type=str, help='Process text directly (for LLM enhancement only)')
    parser.add_argument('--no-llm', action='store_true', help='Disable LLM post-processing')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    
    args = parser.parse_args()
    
    # Create UI
    ui = TerminalUI()
    
    # Show banner
    ui.show_banner()
    
    # Prepare overrides from arguments
    overrides = {}
    
    # Audio overrides
    if args.device is not None:
        overrides.setdefault('audio', {})['device_index'] = args.device
        
    # Output overrides
    if args.output:
        overrides.setdefault('output', {})['handlers'] = [args.output]
        
    # LLM overrides
    if args.no_llm:
        overrides.setdefault('llm', {})['enabled'] = False
        
    # Keyboard overrides
    if args.no_keyboard:
        overrides.setdefault('keyboard', {})['enabled'] = False

    # Verbose override
    if args.verbose:
        overrides.setdefault('output', {})['verbose'] = True
        overrides.setdefault('orchestrator', {})['verbose'] = True
    
    # Load configuration
    try:
        config = load_config(path=args.config, use_env=True, **overrides)
    except Exception as e:
        ui.update_status(f"Configuration error: {e}")
        return

    if not config:
        print("Warning: No configuration loaded. Using defaults.")
    
    # Create orchestrator using factory
    try:
        orchestrator = TranscriptionFactory.create_orchestrator(config, ui=ui)
    except Exception as e:
        ui.update_status(f"Error creating components: {e}")
        # Print full traceback for debugging
        import traceback
        traceback.print_exc()
        return

    # Show config with audio device info
    # We can access the created audio_input directly from the orchestrator
    if config.orchestrator.verbose:
        ui.show_compact_config(config, args, orchestrator.audio_input)
    
    # FAIL-FAST: Validate components
    print("Validating components...")
    try:
        if orchestrator.audio_input:
            print(" - Checking Audio Input...", end=" ", flush=True)
            orchestrator.audio_input.health_check()
            print("OK")
            
        if orchestrator.transcriber:
            print(" - Checking Transcription Service...", end=" ", flush=True)
            orchestrator.transcriber.health_check()
            print("OK")
            
        if orchestrator.llm_processor:
            print(f" - Checking LLM Processor ({orchestrator.llm_processor.model})...", end=" ", flush=True)
            orchestrator.llm_processor.health_check()
            print("OK")
        
        if orchestrator.output_handler:
            print(f" - Checking Output Handler...", end=" ", flush=True)
            # Check if handler is available on current platform
            if not orchestrator.output_handler.is_available():
                handler_name = orchestrator.output_handler.__class__.__name__
                current_platform = orchestrator.output_handler.platform
                supported = orchestrator.output_handler.supported_platforms
                raise RuntimeError(
                    f"{handler_name} is not available on {current_platform}. "
                    f"Supported platforms: {', '.join(supported)}"
                )
            print("OK")
            
    except Exception as e:
        print(f"FAILED\n\nCRITICAL ERROR: {e}")
        print("Please check your configuration and try again.")
        sys.exit(1)
    
    try:
        orchestrator.start()
            
        if args.file:
            orchestrator.process_file(args.file)
            print("\nPress Ctrl+C to exit...")
        
        elif args.text:
            orchestrator.transcribe_text(args.text)
            print("\nPress Ctrl+C to exit...")
        
        else:
            # Normal running mode
            pass
            
        while orchestrator.is_running:
            time.sleep(0.1)
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    
    except Exception as e:
        print(f"\nRuntime error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if 'orchestrator' in locals():
            orchestrator.stop()


if __name__ == '__main__':
    main()
