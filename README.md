# MCP Client with FastAPI and React + LLM Tool Inference

This project consists of two applications with AI-powered natural language processing:

1. **MCP FastAPI Server** - A FastAPI application that acts as an MCP client with OAuth 2.1 authentication and LLM tool inference
2. **React UI** - A React frontend with natural language interface for intelligent MCP operations

## Architecture

```
React UI (Port 4000) → FastAPI Server (Port 8001) → Remote MCP Server (OAuth Protected)
```

## Features

### 🔐 **Advanced OAuth 2.1**
- **PKCE Security**: Code challenge/verifier for secure auth
- **Dynamic Client Registration (DCR)**: Runtime client setup 
- **User-on-behalf-of Delegation**: Proxy authentication
- **Automatic Token Refresh**: Seamless session management
- **Server Discovery**: Automatic metadata detection from MCP servers
- **Auto-Code Population**: Authorization codes automatically detected after consent
- **OAuth State Management**: Persistent authentication across server restarts

### 🤖 **LLM-Powered Tool Inference**
- **Natural Language Processing**: Ask questions in plain English
- **Intelligent Tool Selection**: AI chooses appropriate MCP tools
- **Automatic Argument Generation**: Converts natural language to tool parameters
- **Tool Chaining**: Executes multiple dependent tools automatically
- **Real-time Streaming**: Watch AI reasoning and execution in real-time
- **Context-Aware Conversations**: Maintains conversation history

### 🔧 **Complete MCP Protocol Support**
- **Tools**: List, call, and stream execution with AI assistance and dynamic forms
- **Resources**: Browse and read with intelligent suggestions
- **Prompts**: List and retrieve with natural language interface
- **Delegation**: Execute operations on behalf of other users
- **Streaming Responses**: Real-time updates via NDJSON streaming
- **Azure MCP Compatibility**: Native support for Azure API Gateway MCP deployments

## Recent Improvements ✨

### AI Chat Interface Fix
- **Fixed streaming communication**: Corrected NDJSON parsing in React client for proper AI chat responses
- **Enhanced tool inference**: AI now successfully detects and executes available MCP tools
- **Real-time execution**: See AI reasoning and tool execution in real-time

### Dynamic Form System
- **Schema-based forms**: Automatically generate UI forms from MCP tool input schemas
- **Smart validation**: Required field indicators and parameter descriptions
- **User-friendly interface**: No more manual JSON editing for simple tool calls

### Enhanced Azure MCP Support
- **Streaming protocol detection**: Automatic detection of Azure MCP streaming endpoints
- **Improved error handling**: Better error messages and debugging for Azure deployments
- **OAuth state management**: Authentication persists across server restarts

### Development Experience
- **Comprehensive logging**: Detailed debugging for tool execution and streaming
- **Better error handling**: More informative error messages throughout the application
- **Enhanced startup logic**: Automatic OAuth state restoration on server restart

## Quick Start

```bash
# Terminal 1: Start FastAPI Server
cd mcp-fastapi-server
uv run uvicorn main:app --host 0.0.0.0 --port 8001

# Terminal 2: Start React UI  
cd mcp-react-ui
npm run dev
```

Then open http://localhost:4000 and follow the OAuth setup wizard.

## Setup Instructions

### 1. FastAPI Server Setup

#### Option A: Using UV (Recommended)

```bash
cd mcp-fastapi-server

# Install UV if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Copy and configure environment variables (optional)
cp .env.example .env
# Edit .env with your MCP server URL and OpenAI API key

# Run the server (starts on port 8001)
uv run uvicorn main:app --host 0.0.0.0 --port 8001
```

#### Option B: Using Traditional pip

```bash
cd mcp-fastapi-server
pip install -r requirements.txt

# Copy and configure environment variables (optional)
cp .env.example .env
# Edit .env with your MCP server URL and OpenAI API key

# Run the server (starts on port 8001)
uvicorn main:app --host 0.0.0.0 --port 8001
```

### 2. React UI Setup

```bash
cd mcp-react-ui
npm install

# Run the development server (starts on port 4000)
npm run dev
```

## Environment Configuration

Update the `.env` file in `mcp-fastapi-server/` with your configuration:

```bash
# MCP Server
MCP_SERVER_URL=https://your-mcp-server.example.com

# LLM Configuration (Required for AI features)
OPENAI_API_KEY=your_openai_api_key

# Optional: Pre-configure OAuth client (otherwise uses dynamic registration)
OAUTH_CLIENT_ID=your_oauth_client_id
OAUTH_CLIENT_SECRET=your_oauth_client_secret
```

**Note**: OAuth endpoints (authorization, token, registration) are automatically discovered from the MCP server metadata. No manual configuration needed!

## Usage

### 🚀 **Getting Started**
1. Start both servers (FastAPI on port 8001, React on port 4000)
2. Open http://localhost:4000 in your browser
3. Enter your MCP server URL (or use the example URL provided)
4. Complete OAuth 2.1 authentication flow with automatic server discovery
5. Authorization codes are automatically populated after consent
6. Start using the AI-powered natural language interface!

### 🔐 **OAuth Setup Process**
The application includes a guided OAuth 2.1 setup wizard with **zero manual configuration**:

1. **Server Discovery**: Enter your MCP server URL
2. **Automatic Metadata Detection**: Discovers all OAuth endpoints from server
3. **Dynamic Client Registration**: Automatically registers OAuth client
4. **Authorization**: Opens popup/new tab for user consent
5. **Auto-Code Detection**: Authorization code automatically populated
6. **Token Exchange**: Completes authentication and enables MCP operations

**Note**: All OAuth endpoints (authorization, token, registration) are automatically discovered from the MCP server. No manual URL configuration required!

### 🤖 **AI Chat Interface**
- **Ask questions naturally**: "What tools are available?"
- **Request operations**: "Help me analyze the latest data"
- **Get suggestions**: Click "Get Tool Suggestions" for any query
- **Watch real-time execution**: See AI reasoning and tool execution live
- **Maintain context**: Conversation history helps with follow-up questions

### 🔧 **Manual Tool Operations** 
- View available MCP tools, resources, and prompts
- **Dynamic Forms**: Automatically generated forms based on tool schemas
- Execute tools with custom JSON arguments or user-friendly forms
- Use streaming tool execution for real-time updates
- Browse MCP resources and prompts manually
- **Smart Parameter Validation**: Forms validate required fields and provide descriptions

## API Endpoints

### Server Discovery & OAuth Flow
- `POST /discover/server` - Discover MCP server metadata and OAuth configuration
- `POST /oauth/start-flow` - Start complete OAuth 2.1 flow with DCR (streaming)
- `POST /oauth/complete` - Complete OAuth flow by exchanging authorization code
- `GET /oauth/status` - Get current OAuth flow status
- `POST /oauth/reset` - Reset OAuth flow to start over
- `GET /auth/callback` - OAuth callback endpoint (handles redirects and popups)

### Authentication (Legacy)
- `GET /auth/url` - Get OAuth authorization URL
- `POST /auth/token` - Exchange authorization code for token
- `POST /auth/refresh` - Refresh access token

### MCP Operations
- `POST /mcp/initialize` - Initialize MCP connection
- `GET /mcp/tools` - List available tools
- `POST /mcp/tools/call` - Execute a tool
- `POST /mcp/tools/call/stream` - Execute a tool with streaming
- `GET /mcp/resources` - List available resources
- `POST /mcp/resources/read` - Read a resource
- `GET /mcp/prompts` - List available prompts
- `POST /mcp/prompts/get` - Get a prompt

### AI-Powered Operations
- `POST /ai/query` - Process natural language queries with LLM inference
- `POST /ai/query/stream` - Stream natural language query processing with real-time updates
- `POST /ai/suggestions` - Get tool suggestions for a natural language query
- `POST /ai/clear-context` - Clear conversation context
- `GET /ai/status` - Get AI service status and configuration

### Health
- `GET /health` - Check server health, authentication status, and AI availability

## Security Features

- OAuth 2.1 compliant authentication
- Automatic token refresh
- CORS protection
- Secure token storage
- Environment-based configuration

## Development

The FastAPI server includes:
- **OAuth state persistence** with automatic restoration on server restart
- **Enhanced Azure MCP support** with streaming endpoint detection
- **Comprehensive error handling** with detailed debugging and logging
- **Intelligent tool execution** with LLM-powered natural language processing
- Automatic token refresh on 401 errors
- CORS middleware for React integration
- **NDJSON streaming support** for real-time AI responses
- Modular OAuth and MCP client classes

The React UI includes:
- **Real-time status updates** with authentication state management
- **Dynamic tool forms** generated from MCP tool schemas
- **Fixed streaming support** with proper NDJSON parsing
- **Enhanced AI chat interface** with real-time tool execution
- Tool execution with JSON argument input and user-friendly forms
- Streaming response display with proper error handling
- Resource and prompt browsing
- Clean, responsive interface with comprehensive CSS styling