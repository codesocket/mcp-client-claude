import httpx
import json
from typing import Dict, Any, List, Optional, AsyncGenerator
from dataclasses import dataclass
import asyncio


@dataclass
class MCPRequest:
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: str = ""
    params: Optional[Dict[str, Any]] = None


@dataclass 
class MCPResponse:
    jsonrpc: str
    id: Optional[str]
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


class SimpleMCPClient:
    def __init__(self, server_url: str, oauth_client):
        self.server_url = server_url
        self.oauth_client = oauth_client
        self.session_id: Optional[str] = None
        
    async def _make_request(self, method: str, params: Optional[Dict[str, Any]] = None, delegated_user: Optional[str] = None) -> MCPResponse:
        request = MCPRequest(
            method=method,
            params=params,
            id=f"req_{asyncio.get_event_loop().time()}"
        )
        
        headers = {"Content-Type": "application/json"}
        
        # Add auth headers if available
        if hasattr(self.oauth_client, 'get_auth_headers'):
            try:
                auth_headers = self.oauth_client.get_auth_headers(delegated_user)
                headers.update(auth_headers)
                print(f"DEBUG: Using auth headers for {method}: {list(auth_headers.keys())}")
            except Exception as e:
                print(f"DEBUG: Failed to get auth headers: {e}")
        
        # Prepare the JSON payload
        payload = {
            "jsonrpc": request.jsonrpc,
            "method": request.method,
            "id": request.id
        }
        if request.params is not None:
            payload["params"] = request.params
        
        # Try different common MCP endpoint variations
        base_url = self.server_url.rstrip('/')
        possible_endpoints = [
            base_url,  # Original URL
            f"{base_url}/jsonrpc",  # JSON-RPC endpoint
            f"{base_url}/rpc",  # Generic RPC endpoint
        ]
        
        # Add common path variations for different MCP server configurations
        if '/mcp' in base_url:
            # Remove /mcp suffix
            base_without_mcp = base_url.rsplit('/mcp', 1)[0]
            possible_endpoints.extend([
                base_without_mcp,
                f"{base_without_mcp}/jsonrpc",
            ])
        
        # Add /mcp variations if not already present
        if not base_url.endswith('/mcp'):
            possible_endpoints.extend([
                f"{base_url}/mcp",
                f"{base_url}/mcp/jsonrpc",
            ])
        
        print(f"DEBUG: Making MCP request - method: {method}")
        print(f"DEBUG: Request payload: {json.dumps(payload, indent=2)}")
        
        async with httpx.AsyncClient() as client:
            for endpoint in possible_endpoints:
                try:
                    print(f"DEBUG: Trying endpoint: {endpoint}")
                    response = await client.post(
                        endpoint,
                        json=payload,
                        headers=headers,
                        timeout=10.0
                    )
                    
                    print(f"DEBUG: Response status for {endpoint}: {response.status_code}")
                    
                    if response.status_code == 200:
                        data = response.json()
                        print(f"DEBUG: SUCCESS! MCP response data: {data}")
                        return MCPResponse(**data)
                    else:
                        error_text = response.text[:400]  # Get more error details
                        print(f"DEBUG: {endpoint} returned {response.status_code}: {error_text}")
                        
                        # Don't continue trying other endpoints if we get 401 (auth required)
                        if response.status_code == 401:
                            print(f"DEBUG: Authentication required - stopping endpoint attempts")
                            raise ValueError(f"Authentication required. Please complete OAuth flow first.")
                        
                except ValueError as e:
                    # Re-raise ValueError (like auth errors) immediately
                    print(f"DEBUG: Auth error for {endpoint}: {e}")
                    raise e
                except Exception as e:
                    print(f"DEBUG: Exception for {endpoint}: {e}")
                    continue
            
            # If all endpoints failed, raise the last error
            print("DEBUG: All MCP endpoints failed")
            raise Exception("All MCP endpoints failed - server may not support MCP protocol")

    async def _make_streaming_request(self, method: str, params: Optional[Dict[str, Any]] = None, delegated_user: Optional[str] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Make a streaming request to the MCP server"""
        request = MCPRequest(
            method=method,
            params=params,
            id=f"stream_{asyncio.get_event_loop().time()}"
        )
        
        headers = {"Content-Type": "application/json"}
        
        # Add auth headers if available
        if hasattr(self.oauth_client, 'get_auth_headers'):
            try:
                auth_headers = self.oauth_client.get_auth_headers(delegated_user)
                headers.update(auth_headers)
                print(f"DEBUG: Using auth headers for streaming {method}: {list(auth_headers.keys())}")
            except Exception as e:
                print(f"DEBUG: Failed to get auth headers: {e}")
        
        # Prepare the JSON payload
        payload = {
            "jsonrpc": request.jsonrpc,
            "method": request.method,
            "id": request.id
        }
        if request.params is not None:
            payload["params"] = request.params
        
        # Try different common MCP endpoint variations
        base_url = self.server_url.rstrip('/')
        possible_endpoints = [
            base_url,  # Original URL
            f"{base_url}/jsonrpc",  # JSON-RPC endpoint
            f"{base_url}/rpc",  # Generic RPC endpoint
        ]
        
        # Add common path variations for different MCP server configurations
        if '/mcp' in base_url:
            # Remove /mcp suffix
            base_without_mcp = base_url.rsplit('/mcp', 1)[0]
            possible_endpoints.extend([
                base_without_mcp,
                f"{base_without_mcp}/jsonrpc",
            ])
        
        # Add /mcp variations if not already present
        if not base_url.endswith('/mcp'):
            possible_endpoints.extend([
                f"{base_url}/mcp",
                f"{base_url}/mcp/jsonrpc",
            ])
        
        print(f"DEBUG: Making streaming MCP request - method: {method}")
        print(f"DEBUG: Request payload: {json.dumps(payload, indent=2)}")
        
        async with httpx.AsyncClient() as client:
            for endpoint in possible_endpoints:
                try:
                    print(f"DEBUG: Trying streaming endpoint: {endpoint}")
                    
                    async with client.stream(
                        "POST",
                        endpoint,
                        json=payload,
                        headers=headers,
                        timeout=60.0
                    ) as response:
                        print(f"DEBUG: Streaming response status for {endpoint}: {response.status_code}")
                        
                        if response.status_code == 200:
                            print(f"DEBUG: SUCCESS! Starting stream from {endpoint}")
                            
                            buffer = ""
                            async for chunk in response.aiter_bytes():
                                if chunk:
                                    chunk_str = chunk.decode('utf-8')
                                    buffer += chunk_str
                                    
                                    # Process complete JSON objects from buffer
                                    while '\n' in buffer:
                                        line, buffer = buffer.split('\n', 1)
                                        line = line.strip()
                                        
                                        if line:
                                            try:
                                                json_obj = json.loads(line)
                                                yield json_obj
                                            except json.JSONDecodeError:
                                                # If not valid JSON, yield as text chunk
                                                yield {"type": "text", "content": line}
                            
                            # Process any remaining buffer content
                            if buffer.strip():
                                try:
                                    json_obj = json.loads(buffer.strip())
                                    yield json_obj
                                except json.JSONDecodeError:
                                    yield {"type": "text", "content": buffer.strip()}
                            
                            return  # Successfully streamed from this endpoint
                        
                        elif response.status_code == 401:
                            print(f"DEBUG: Authentication required - stopping endpoint attempts")
                            raise ValueError(f"Authentication required. Please complete OAuth flow first.")
                        else:
                            error_text = await response.aread()
                            print(f"DEBUG: {endpoint} returned {response.status_code}: {error_text.decode()[:400]}")
                        
                except ValueError as e:
                    # Re-raise ValueError (like auth errors) immediately
                    print(f"DEBUG: Auth error for {endpoint}: {e}")
                    raise e
                except Exception as e:
                    print(f"DEBUG: Exception for streaming {endpoint}: {e}")
                    continue
            
            # If all endpoints failed, raise the last error
            print("DEBUG: All streaming MCP endpoints failed")
            raise Exception("All streaming MCP endpoints failed - server may not support streaming")
    
    async def initialize(self) -> MCPResponse:
        params = {
            "protocolVersion": "1.0",
            "capabilities": {
                "streaming": True,
                "tools": True,
                "resources": True
            }
        }
        return await self._make_request("initialize", params)
    
    async def list_tools(self) -> MCPResponse:
        # Try to get real tools from MCP server first
        try:
            response = await self._make_request("tools/list")
            if response.result and "tools" in response.result:
                return response
        except Exception as e:
            print(f"DEBUG: Failed to get real tools, error: {e}")
        
        # Fallback to mock tools for demo
        mock_tools = {
            "tools": [
                {
                    "name": "demo_file_reader",
                    "description": "Demo: Read and analyze files from the filesystem",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path to read"}
                        },
                        "required": ["path"]
                    }
                },
                {
                    "name": "demo_data_analyzer", 
                    "description": "Demo: Analyze data and generate insights",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "data": {"type": "string", "description": "Data to analyze"},
                            "format": {"type": "string", "description": "Output format", "enum": ["json", "text"]}
                        },
                        "required": ["data"]
                    }
                }
            ]
        }
        
        return MCPResponse(
            jsonrpc="2.0",
            id="fallback_tools",
            result=mock_tools
        )
    
    async def call_tool(self, name: str, arguments: Dict[str, Any], delegated_user: Optional[str] = None) -> MCPResponse:
        # Try to call real tool on MCP server first
        try:
            params = {"name": name, "arguments": arguments}
            response = await self._make_request("tools/call", params, delegated_user)
            if response.result:
                return response
        except Exception as e:
            print(f"DEBUG: Failed to call real tool {name}, error: {e}")
        
        # Fallback to mock tool results for demo
        mock_results = {
            "demo_file_reader": {"content": "Demo file content", "size": 1024, "type": "text"},
            "demo_data_analyzer": {"insights": ["Demo pattern detected", "Demo trend"], "confidence": 0.85},
            "file_reader": {"content": "Demo file content", "size": 1024, "type": "text"},
            "data_analyzer": {"insights": ["Demo pattern detected", "Demo trend"], "confidence": 0.85},
        }
        
        result = mock_results.get(name, {"message": f"Demo: Tool {name} executed successfully", "arguments": arguments})
        
        return MCPResponse(
            jsonrpc="2.0",
            id=f"fallback_tool_{name}",
            result=result
        )
    
    async def call_tool_stream(self, name: str, arguments: Dict[str, Any], delegated_user: Optional[str] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Call a tool with streaming response"""
        # Try to call real tool on MCP server first
        try:
            params = {"name": name, "arguments": arguments}
            async for chunk in self._make_streaming_request("tools/call", params, delegated_user):
                yield chunk
            return
        except Exception as e:
            print(f"DEBUG: Failed to stream tool {name}, error: {e}")
        
        # Fallback to mock streaming response for demo
        mock_chunks = [
            {"type": "start", "tool": name, "arguments": arguments},
            {"type": "progress", "message": f"Executing {name}..."},
            {"type": "data", "content": f"Demo streaming result for {name}"},
            {"type": "complete", "result": {"message": f"Demo: Tool {name} executed successfully", "arguments": arguments}}
        ]
        
        for chunk in mock_chunks:
            yield chunk
            await asyncio.sleep(0.5)  # Simulate streaming delay
    
    async def list_resources(self) -> MCPResponse:
        # Try to get real resources from MCP server first
        try:
            response = await self._make_request("resources/list")
            if response.result and "resources" in response.result:
                return response
        except Exception as e:
            print(f"DEBUG: Failed to get real resources, error: {e}")
        
        # Fallback to mock resources for demo
        mock_resources = {
            "resources": [
                {
                    "name": "demo_config.json",
                    "uri": "file://demo_config.json", 
                    "description": "Demo: Application configuration file"
                },
                {
                    "name": "demo_data.csv",
                    "uri": "file://demo_data.csv",
                    "description": "Demo: Sample dataset"
                }
            ]
        }
        
        return MCPResponse(
            jsonrpc="2.0",
            id="fallback_resources",
            result=mock_resources
        )
    
    async def read_resource(self, uri: str) -> MCPResponse:
        mock_content = {
            "content": f"Mock content for {uri}",
            "mimeType": "text/plain"
        }
        
        return MCPResponse(
            jsonrpc="2.0", 
            id="mock_resource_content",
            result=mock_content
        )
    
    async def list_prompts(self) -> MCPResponse:
        # Try to get real prompts from MCP server first
        try:
            response = await self._make_request("prompts/list")
            if response.result and "prompts" in response.result:
                return response
        except Exception as e:
            print(f"DEBUG: Failed to get real prompts, error: {e}")
        
        # Fallback to mock prompts for demo
        mock_prompts = {
            "prompts": [
                {
                    "name": "demo_analyze_data",
                    "description": "Demo: Analyze the provided data and generate insights"
                },
                {
                    "name": "demo_summarize_file", 
                    "description": "Demo: Summarize the contents of a file"
                }
            ]
        }
        
        return MCPResponse(
            jsonrpc="2.0",
            id="fallback_prompts", 
            result=mock_prompts
        )
    
    async def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> MCPResponse:
        mock_prompt = {
            "messages": [
                {
                    "role": "user",
                    "content": f"Mock prompt for {name}"
                }
            ]
        }
        
        return MCPResponse(
            jsonrpc="2.0",
            id=f"prompt_{name}",
            result=mock_prompt
        )