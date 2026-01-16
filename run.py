#!/usr/bin/env python3
"""
ElectriFix Diagnostics - Runner Script
Simple entry point to start the diagnostic server.
"""

import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent
BACKEND_DIR = BASE_DIR / "backend"
VENV_PYTHON = BASE_DIR / "venv" / "bin" / "python"


def check_venv():
    """Check if running in virtual environment."""
    return VENV_PYTHON.exists()


def check_dependencies():
    """Check if required packages are installed."""
    try:
        import fastapi
        import uvicorn
        import serial
        import anthropic
        return True
    except ImportError as e:
        print(f"Missing dependency: {e.name}")
        return False


def install_dependencies():
    """Install required packages."""
    print("Installing dependencies...")
    requirements = BASE_DIR / "requirements.txt"
    python = str(VENV_PYTHON) if check_venv() else sys.executable
    subprocess.run([python, "-m", "pip", "install", "-r", str(requirements)])


def main():
    """Main entry point."""
    print("="*50)
    print("  ElectriFix Diagnostics")
    print("  E-scooter UART Diagnostic Tool")
    print("="*50)
    print()
    
    # If venv exists but we're not using it, re-execute with venv python
    if check_venv() and sys.executable != str(VENV_PYTHON):
        print(f"Restarting with virtual environment...\n")
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), __file__] + sys.argv[1:])
        return
    
    # Check dependencies
    if not check_dependencies():
        print("Some dependencies are missing.")
        response = input("Install now? (y/n): ").strip().lower()
        if response == 'y':
            install_dependencies()
        else:
            print("Please run: pip install -r requirements.txt")
            sys.exit(1)
    
    # Check for API key
    env_file = BASE_DIR / ".env"
    if not env_file.exists() or "ANTHROPIC_API_KEY" not in env_file.read_text():
        print()
        print("NOTE: Claude API key not configured.")
        print("AI-powered diagnosis will be disabled.")
        print("You can configure it in Settings after starting.")
        print()
    
    # Start server
    print("Starting server on http://localhost:3003")
    print("Press Ctrl+C to stop")
    print()
    
    # Change to backend directory and run
    os.chdir(BACKEND_DIR)
    sys.path.insert(0, str(BACKEND_DIR))
    
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=3003,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
