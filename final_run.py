import os
import time
import subprocess
from pyngrok import ngrok

def run():
    # Set authtoken
    token = "3AXg7AEkSB0wqnAeMcaPCbIOh02_herGg4VQjayoQJWmB44i"
    print(f"Setting authtoken...")
    ngrok.set_auth_token(token)
    
    # Start tunnel
    print("Opening tunnel on port 8080...")
    public_url = ngrok.connect(8080).public_url
    print(f"\n* PUBLIC URL: {public_url}\n")
    
    # Write URL to file for easy access
    with open("ngrok_status.txt", "w") as f:
        f.write(public_url)
    
    # Start Flask app
    print("Starting Flask application...")
    # Use the same python executable
    flask_process = subprocess.Popen(["python", "main.py"], cwd=os.getcwd())
    
    print("\nServer and tunnel are running. Do not close this terminal.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        ngrok.disconnect(public_url)
        flask_process.terminate()

if __name__ == "__main__":
    run()
