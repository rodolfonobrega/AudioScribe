"""
AudioScribe Engine - Standalone entry point for Electron packaging.

This is a thin wrapper around main.py that PyInstaller uses to produce
the audioscribe_engine binary bundled inside the Electron app.
"""

import sys
import os

# When running inside a PyInstaller bundle, ensure the project root is
# on sys.path so that all core/ imports resolve correctly.
_bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
if _bundle_dir not in sys.path:
    sys.path.insert(0, _bundle_dir)

if __name__ == '__main__':
    # Forward all arguments to the real main
    from main import main
    main()
