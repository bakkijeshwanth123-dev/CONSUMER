import time
import subprocess
from pyngrok import ngrok

def start_server_and_tunnel():
    print("Starting Flask server on port 8080...")
    flask_process = subprocess.Popen(["python", "main.py"], cwd=r"c:\Users\bakki\Music\New folder\jesh\OSN Serpent-Secure-System")
    
    # Wait a moment for the server to initialize
    time.sleep(5)
    
    print("Configuring ngrok authtoken...")
    ngrok.set_auth_token("3AoavDv97H0OnVL71zY4Hg7eADq_4fo4P5b3uqvha41FhWCGs")
    
    print("Opening ngrok tunnel...")
    public_url = ngrok.connect(8080).public_url
    print(f"\n * Public URL: {public_url}")
    print("\nPress Ctrl+C to stop the server and tunnel.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        ngrok.disconnect(public_url)
        flask_process.terminate()

if __name__ == "__main__":
    start_server_and_tunnel()
