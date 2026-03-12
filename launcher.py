"""
OSN Serpent-Secure System — Windows Desktop Launcher
-----------------------------------------------------
This launcher:
  1. Finds a free port
  2. Starts Flask in a background thread
  3. Opens the desktop browser automatically
  4. Shows a system tray icon (if pystray is installed)
"""

import os
import sys
import socket
import threading
import webbrowser
import time
import subprocess

# ─── Resolve asset paths (works both in dev and inside PyInstaller EXE) ───────
def resource_path(relative_path):
    """Get absolute path to resource — works for dev and PyInstaller."""
    try:
        base_path = sys._MEIPASS  # PyInstaller temp folder
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


# ─── Set working directory so Flask finds templates/static/db files ───────────
if getattr(sys, 'frozen', False):
    # Running inside PyInstaller EXE
    os.chdir(sys._MEIPASS)
else:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))


# ─── Find a free port ─────────────────────────────────────────────────────────
def find_free_port(default=8080):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', default))
            return default
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]


# ─── Flask Startup ────────────────────────────────────────────────────────────
def run_flask(port):
    from app import app
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)


# ─── Wait for Flask to be ready ───────────────────────────────────────────────
def wait_for_server(port, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.3)
    return False


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    port = find_free_port()
    url  = f'http://127.0.0.1:{port}'

    print(f'[SERPENT-SECURE] Starting server on {url}')

    # Start Flask server in background thread
    server_thread = threading.Thread(target=run_flask, args=(port,), daemon=True)
    server_thread.start()

    # Wait until Flask is accepting connections
    if wait_for_server(port):
        print('[SERPENT-SECURE] Server ready — opening browser...')
        webbrowser.open(url)
    else:
        print('[SERPENT-SECURE] ERROR: Server failed to start.')
        sys.exit(1)

    # Keep the launcher alive
    try:
        server_thread.join()
    except KeyboardInterrupt:
        print('[SERPENT-SECURE] Shutting down.')
        sys.exit(0)


if __name__ == '__main__':
    main()
