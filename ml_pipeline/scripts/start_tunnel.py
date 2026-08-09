import subprocess
import time
import sys

def start_tunnel(port=8001):
    print(f"Starting Localtunnel on port {port}...")
    print("This will expose your local backend to the public internet securely.")
    print("WARNING: Anyone with the link can access the API.")
    print("Please wait while the tunnel URL is generated...\n")
    
    try:
        # Run localtunnel via npx
        process = subprocess.Popen(
            ["npx", "localtunnel", "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())
                if "your url is:" in output:
                    url = output.split("your url is:")[1].strip()
                    print("\n" + "="*50)
                    print(f"TUNNEL ACTIVE: {url}")
                    print("="*50)
                    print("\n1. Copy this URL.")
                    print("2. Open the NurseAssist AI Flutter App.")
                    print("3. Click the Settings icon in the top right.")
                    print("4. Paste the URL into the 'Backend URL' field and Save.")
                    print("\nPress Ctrl+C to close the tunnel.")
                    
    except KeyboardInterrupt:
        print("\nClosing tunnel...")
        process.terminate()
        sys.exit(0)
    except FileNotFoundError:
        print("Error: 'npx' command not found.")
        print("Please install Node.js and npm to use Localtunnel.")
        sys.exit(1)

if __name__ == "__main__":
    start_tunnel()
