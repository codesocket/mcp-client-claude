#!/usr/bin/env python3

import os
import sys
import subprocess
import time
import webbrowser
from pathlib import Path


def setup_demo_environment():
    """Setup demo environment with example values"""
    print("=== Setting up Demo Environment ===")
    
    # Demo configuration - you can customize these values
    env_vars = {
        "MCP_SERVER_URL": "https://api.example.com/mcp",
        "OAUTH_REGISTRATION_ENDPOINT": "https://auth.example.com/oauth/register", 
        "OAUTH_AUTH_URL": "https://auth.example.com/oauth/authorize",
        "OAUTH_TOKEN_URL": "https://auth.example.com/oauth/token",
        "OAUTH_DELEGATION_ENDPOINT": "https://auth.example.com/oauth/token",
        "OAUTH_REDIRECT_URI": "http://localhost:8000/auth/callback",
        "FASTAPI_PORT": "8000",
        "REACT_PORT": "3000",
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "")
    }
    
    # Write .env file
    env_file = Path("mcp-fastapi-server/.env")
    with open(env_file, "w") as f:
        for key, value in env_vars.items():
            f.write(f"{key}={value}\n")
    
    print(f"✅ Demo configuration saved to {env_file}")
    print(f"MCP Server: {env_vars['MCP_SERVER_URL']}")
    print(f"OAuth Provider: {env_vars['OAUTH_AUTH_URL']}")
    
    return env_vars


def start_servers(env_vars):
    """Start both FastAPI and React servers"""
    print("\n=== Starting Demo Servers ===")
    
    # Start FastAPI server
    print("🚀 Starting FastAPI server...")
    fastapi_env = os.environ.copy()
    fastapi_env.update(env_vars)
    
    # Add python path for local packages
    fastapi_env["PATH"] = f"/Users/Abdul.Rehman/Library/Python/3.9/bin:{fastapi_env.get('PATH', '')}"
    
    try:
        fastapi_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", env_vars["FASTAPI_PORT"], "--reload"],
            cwd="mcp-fastapi-server",
            env=fastapi_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Give FastAPI time to start
        time.sleep(3)
        
        # Check if FastAPI started successfully
        poll = fastapi_process.poll()
        if poll is not None:
            stdout, stderr = fastapi_process.communicate()
            print(f"❌ FastAPI failed to start:")
            print(f"stdout: {stdout.decode()}")
            print(f"stderr: {stderr.decode()}")
            return None, None
        
        print(f"✅ FastAPI server started on port {env_vars['FASTAPI_PORT']}")
        
    except Exception as e:
        print(f"❌ Failed to start FastAPI server: {e}")
        return None, None
    
    # Start React development server
    print("🚀 Starting React development server...")
    react_env = os.environ.copy()
    react_env["PORT"] = env_vars["REACT_PORT"]
    
    try:
        react_process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd="mcp-react-ui",
            env=react_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Give React time to start
        time.sleep(5)
        
        print(f"✅ React development server started on port {env_vars['REACT_PORT']}")
        
    except Exception as e:
        print(f"❌ Failed to start React server: {e}")
        fastapi_process.terminate()
        return None, None
    
    print(f"\n🎉 Demo Application Started Successfully!")
    print(f"📡 FastAPI Server: http://localhost:{env_vars['FASTAPI_PORT']}")
    print(f"🌐 React UI: http://localhost:{env_vars['REACT_PORT']}")
    print(f"📖 API Docs: http://localhost:{env_vars['FASTAPI_PORT']}/docs")
    
    return fastapi_process, react_process


def main():
    """Main demo application entry point"""
    print("🎯 MCP Client Demo Application")
    print("This demo showcases OAuth 2.1 with DCR and delegation flows")
    print("connecting to a remote MCP server.\n")
    
    # Check if we're in the right directory
    if not Path("mcp-fastapi-server").exists() or not Path("mcp-react-ui").exists():
        print("❌ Error: Please run this script from the project root directory")
        print("Expected directories: mcp-fastapi-server, mcp-react-ui")
        sys.exit(1)
    
    # Setup demo environment
    env_vars = setup_demo_environment()
    
    print("\n=== Starting Demo ===")
    print("Note: This demo uses example OAuth endpoints.")
    print("In production, replace with your actual OAuth provider URLs.")
    
    # Start servers
    fastapi_process, react_process = start_servers(env_vars)
    
    if not fastapi_process or not react_process:
        print("\n❌ Failed to start servers")
        sys.exit(1)
    
    print("\n=== Demo Instructions ===")
    print("1. The React UI is now available at http://localhost:3000")
    print("2. FastAPI backend with OAuth 2.1 + DCR support at http://localhost:8000")
    print("3. API documentation at http://localhost:8000/docs")
    print("\n📋 Demo Features:")
    print("   • OAuth 2.1 with PKCE")
    print("   • Dynamic Client Registration (DCR)")
    print("   • User-on-behalf-of delegation")
    print("   • Streamable HTTP MCP transport")
    print("   • Full MCP protocol support")
    
    print("\n⚡ Press Ctrl+C to stop the demo")
    
    try:
        # Keep running until interrupted
        while True:
            # Check if processes are still running
            if fastapi_process.poll() is not None:
                print("\n❌ FastAPI server stopped unexpectedly")
                break
            if react_process.poll() is not None:
                print("\n❌ React server stopped unexpectedly")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping Demo Servers...")
        
        # Terminate processes
        if fastapi_process:
            fastapi_process.terminate()
        if react_process:
            react_process.terminate()
        
        # Wait for processes to terminate gracefully
        try:
            if fastapi_process:
                fastapi_process.wait(timeout=5)
            if react_process:
                react_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if fastapi_process:
                fastapi_process.kill()
            if react_process:
                react_process.kill()
        
        print("✅ Demo stopped successfully")


if __name__ == "__main__":
    main()