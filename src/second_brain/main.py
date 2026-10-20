import sys
from second_brain.interface.web_server import start_web_server

def run_server():
    """The main entry point for the Second Brain Sovereign Web & Mobile System."""
    print("🧠 Initializing Second Brain System...")
    start_web_server()

if __name__ == "__main__":
    run_server()