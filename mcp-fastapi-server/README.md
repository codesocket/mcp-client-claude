# MCP FastAPI Server

A FastAPI application that acts as an MCP client with OAuth 2.1 authentication and LLM tool inference.

## Features

- OAuth 2.1 compliant authentication with PKCE
- MCP protocol support (tools, resources, prompts)
- LLM-powered natural language processing
- Real-time streaming responses
- Automatic token refresh

## Installation

### Using UV (Recommended)

```bash
uv sync
uv run python main.py
```

### Using pip

```bash
pip install -r requirements.txt
python main.py
```

## Configuration

Copy `.env.example` to `.env` and configure your OAuth and MCP server details.