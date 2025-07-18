#!/bin/bash
# MCP Client Setup Script

set -e

echo "🚀 Setting up MCP Client..."

# Check if we're in the right directory
if [ ! -f "README.md" ] || [ ! -d "mcp-fastapi-server" ] || [ ! -d "mcp-react-ui" ]; then
    echo "❌ Please run this script from the mcp-client-claude root directory"
    exit 1
fi

echo "📁 Current directory: $(pwd)"

# Setup FastAPI Server
echo ""
echo "🐍 Setting up FastAPI Server..."
cd mcp-fastapi-server

# Install UV if not present
if ! command -v uv &> /dev/null; then
    echo "📦 Installing UV package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

echo "📦 Installing Python dependencies with UV..."
uv sync

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️ Creating .env file from example..."
    cp .env.example .env
    echo "📝 Please edit .env file to add your OpenAI API key and configure other settings"
fi

cd ..

# Setup React UI
echo ""
echo "⚛️ Setting up React UI..."
cd mcp-react-ui

# Check if npm is available
if ! command -v npm &> /dev/null; then
    echo "❌ npm is required but not installed. Please install Node.js and npm"
    exit 1
fi

echo "📦 Installing Node.js dependencies..."
npm install

cd ..

echo ""
echo "✅ Setup complete!"
echo ""
echo "🚀 To start the application:"
echo ""
echo "Terminal 1 (FastAPI Server):"
echo "cd mcp-fastapi-server"
echo "uv run uvicorn main:app --host 0.0.0.0 --port 8001"
echo ""
echo "Terminal 2 (React UI):"
echo "cd mcp-react-ui"
echo "npm run dev"
echo ""
echo "Then open http://localhost:4000 in your browser"
echo ""
echo "📝 Don't forget to:"
echo "  1. Add your OpenAI API key to mcp-fastapi-server/.env"
echo "  2. Configure any other environment variables as needed"
echo ""
echo "🎉 Happy coding!"