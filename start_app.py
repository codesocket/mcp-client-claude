#!/usr/bin/env python3

import os
import sys
import subprocess
import time
import webbrowser
from pathlib import Path


def get_user_input(prompt: str, default: str = None) -> str:
    """Get user input with optional default value"""
    if default:
        user_input = input(f"{prompt} [{default}]: ").strip()
        return user_input if user_input else default
    else:
        while True:
            user_input = input(f"{prompt}: ").strip()
            if user_input:
                return user_input
            print("This field is required. Please enter a value.")


def setup_environment():
    """Configure environment variables for the application"""
    print("=== MCP Client Application Setup ===\n")
    
    print("Please provide the following configuration details:\n")
    
    # MCP Server Configuration
    print("1. MCP Server Configuration:")
    mcp_server_url = get_user_input("MCP Server URL", "https://mcp-server.example.com")
    
    # OAuth Configuration
    print("\n2. OAuth 2.1 Configuration:")
    oauth_registration_endpoint = get_user_input("OAuth Registration Endpoint", "https://auth.example.com/oauth/register")
    oauth_auth_url = get_user_input("OAuth Authorization URL", "https://auth.example.com/oauth/authorize")
    oauth_token_url = get_user_input("OAuth Token URL", "https://auth.example.com/oauth/token")
    oauth_delegation_endpoint = get_user_input("OAuth Delegation Endpoint", oauth_token_url)
    
    # Optional: Pre-registered client credentials
    print("\n3. Client Credentials (Optional - leave blank to use Dynamic Client Registration):")
    oauth_client_id = get_user_input("OAuth Client ID (optional)", "")
    oauth_client_secret = get_user_input("OAuth Client Secret (optional)", "")
    
    # Application Configuration
    print("\n4. Application Configuration:")
    redirect_uri = get_user_input("OAuth Redirect URI", "http://localhost:8000/auth/callback")
    fastapi_port = get_user_input("FastAPI Server Port", "8000")
    react_port = get_user_input("React UI Port", "3000")
    
    # Set environment variables
    env_vars = {
        "MCP_SERVER_URL": mcp_server_url,
        "OAUTH_REGISTRATION_ENDPOINT": oauth_registration_endpoint,
        "OAUTH_AUTH_URL": oauth_auth_url,
        "OAUTH_TOKEN_URL": oauth_token_url,
        "OAUTH_DELEGATION_ENDPOINT": oauth_delegation_endpoint,
        "OAUTH_REDIRECT_URI": redirect_uri,
        "FASTAPI_PORT": fastapi_port,
        "REACT_PORT": react_port
    }
    
    if oauth_client_id:
        env_vars["OAUTH_CLIENT_ID"] = oauth_client_id
    if oauth_client_secret:
        env_vars["OAUTH_CLIENT_SECRET"] = oauth_client_secret
    
    # Write .env file
    env_file = Path("mcp-fastapi-server/.env")
    with open(env_file, "w") as f:
        for key, value in env_vars.items():
            f.write(f"{key}={value}\n")
    
    print(f"\n✅ Configuration saved to {env_file}")
    return env_vars


def check_dependencies():
    """Check if required dependencies are installed"""
    print("\n=== Checking Dependencies ===")
    
    # Check Python dependencies for FastAPI
    try:
        import fastapi
        import uvicorn
        import httpx
        print("✅ Python dependencies for FastAPI are installed")
    except ImportError as e:
        print(f"❌ Missing Python dependency: {e}")
        print("Please run: cd mcp-fastapi-server && pip install -r requirements.txt")
        return False
    
    # Check Node.js and npm
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Node.js is installed: {result.stdout.strip()}")
        else:
            print("❌ Node.js is not installed")
            return False
    except FileNotFoundError:
        print("❌ Node.js is not installed")
        return False
    
    try:
        result = subprocess.run(["npm", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ npm is installed: {result.stdout.strip()}")
        else:
            print("❌ npm is not installed")
            return False
    except FileNotFoundError:
        print("❌ npm is not installed")
        return False
    
    return True


def install_react_dependencies():
    """Install React dependencies if needed"""
    node_modules = Path("mcp-react-ui/node_modules")
    if not node_modules.exists():
        print("\n=== Installing React Dependencies ===")
        print("Installing React dependencies...")
        
        try:
            subprocess.run(["npm", "install"], cwd="mcp-react-ui", check=True)
            print("✅ React dependencies installed successfully")
        except subprocess.CalledProcessError:
            print("❌ Failed to install React dependencies")
            return False
    else:
        print("✅ React dependencies already installed")
    
    return True


def start_servers(env_vars):
    """Start both FastAPI and React servers"""
    print("\n=== Starting Servers ===")
    
    # Start FastAPI server
    print("Starting FastAPI server...")
    fastapi_env = os.environ.copy()
    fastapi_env.update(env_vars)
    
    fastapi_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", env_vars["FASTAPI_PORT"], "--reload"],
        cwd="mcp-fastapi-server",
        env=fastapi_env
    )
    
    # Give FastAPI time to start
    time.sleep(3)
    
    # Start React development server
    print("Starting React development server...")
    react_env = os.environ.copy()
    react_env["PORT"] = env_vars["REACT_PORT"]
    
    react_process = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd="mcp-react-ui",
        env=react_env
    )
    
    # Give React time to start
    time.sleep(5)
    
    print(f"\n🚀 Application is starting!")
    print(f"FastAPI Server: http://localhost:{env_vars['FASTAPI_PORT']}")
    print(f"React UI: http://localhost:{env_vars['REACT_PORT']}")
    print("\nOpening React UI in your browser...")
    
    # Open browser
    try:
        webbrowser.open(f"http://localhost:{env_vars['REACT_PORT']}")
    except Exception as e:
        print(f"Could not open browser automatically: {e}")
    
    print("\n=== Application Started ===")
    print("Press Ctrl+C to stop both servers")
    
    try:
        # Wait for user interrupt
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n=== Stopping Servers ===")
        fastapi_process.terminate()
        react_process.terminate()
        
        # Wait for processes to terminate
        try:
            fastapi_process.wait(timeout=5)
            react_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            fastapi_process.kill()
            react_process.kill()
        
        print("✅ Servers stopped")


def main():
    """Main application entry point"""
    print("Welcome to the MCP Client Application!")
    print("This will set up and run both the FastAPI server and React UI.\n")
    
    # Check if we're in the right directory
    if not Path("mcp-fastapi-server").exists() or not Path("mcp-react-ui").exists():
        print("❌ Error: Please run this script from the project root directory")
        print("Expected directories: mcp-fastapi-server, mcp-react-ui")
        sys.exit(1)
    
    # Check dependencies
    if not check_dependencies():
        print("\n❌ Please install missing dependencies and try again")
        sys.exit(1)
    
    # Install React dependencies
    if not install_react_dependencies():
        print("\n❌ Failed to install React dependencies")
        sys.exit(1)
    
    # Setup environment
    env_vars = setup_environment()
    
    # Confirm before starting
    print(f"\n=== Configuration Summary ===")
    print(f"MCP Server: {env_vars['MCP_SERVER_URL']}")
    print(f"OAuth Auth URL: {env_vars['OAUTH_AUTH_URL']}")
    print(f"FastAPI Port: {env_vars['FASTAPI_PORT']}")
    print(f"React Port: {env_vars['REACT_PORT']}")
    
    confirm = input("\nStart the application with this configuration? (y/N): ").strip().lower()
    if confirm != 'y':
        print("Setup cancelled.")
        sys.exit(0)
    
    # Start servers
    start_servers(env_vars)


if __name__ == "__main__":
    main()