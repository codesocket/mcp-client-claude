import asyncio
import json
import httpx
from typing import Dict, Any, Optional, AsyncGenerator
from pydantic import BaseModel


class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: str


class MCPResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


class SimpleMCPClient:
    def __init__(self, server_url: str, oauth_client=None):
        self.server_url = server_url
        self.oauth_client = oauth_client

    async def _make_request(self, method: str, params: Optional[Dict[str, Any]] = None, delegated_user: Optional[str] = None) -> MCPResponse:
        request = MCPRequest(
            method=method,
            params=params or {},
            id=f"req_{asyncio.get_event_loop().time()}"
        )
        
        # Add auth headers if available
        if hasattr(self.oauth_client, 'get_auth_headers'):
            try:
                headers = self.oauth_client.get_auth_headers(delegated_user)
                print(f"DEBUG: Using auth headers for {method}: {list(headers.keys())}")
            except Exception as e:
                print(f"DEBUG: Failed to get auth headers: {e}")
                headers = {"Content-Type": "application/json"}
        else:
            headers = {"Content-Type": "application/json"}
        
        # Prepare the JSON payload in standard MCP format
        # Use simple integer ID for better compatibility  
        try:
            simple_id = int(float(request.id.split('_')[-1])) % 1000
        except:
            simple_id = 1
            
        payload = {
            "method": request.method,
            "params": {},
            "jsonrpc": request.jsonrpc,
            "id": simple_id
        }
        
        if request.params is not None:
            payload["params"] = request.params.copy()
        
        # Add _meta with progressToken for streaming compatibility
        payload["params"]["_meta"] = {"progressToken": simple_id}
        
        # Try different common MCP endpoint variations
        base_url = self.server_url.rstrip('/')
        possible_endpoints = [
            base_url,  # Original URL
            f"{base_url}/jsonrpc",  # JSON-RPC endpoint
            f"{base_url}/rpc",  # Generic RPC endpoint
        ]
        
        # Add streaming transport variations for servers that support it
        if '?' in base_url:
            # URL already has query params
            possible_endpoints.append(f"{base_url}&transportType=streamable-http")
        else:
            possible_endpoints.append(f"{base_url}?transportType=streamable-http")
        
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
        print(f"DEBUG: Server URL: {self.server_url}")
        print(f"DEBUG: Request payload: {json.dumps(payload, indent=2)}")
        
        async with httpx.AsyncClient() as client:
            for endpoint in possible_endpoints:
                try:
                    print(f"DEBUG: Trying endpoint: {endpoint}")
                    print(f"DEBUG: Request headers: {headers}")
                    
                    # Use longer timeout for streaming endpoints
                    timeout_val = 60.0 if 'transportType=streamable-http' in endpoint else 30.0
                    print(f"DEBUG: Request timeout: {timeout_val} seconds")
                    
                    # Check if this is a streaming endpoint
                    if 'transportType=streamable-http' in endpoint:
                        print(f"DEBUG: Using streaming request for MCP server")
                        # Add Accept header for SSE
                        stream_headers = headers.copy()
                        stream_headers["Accept"] = "text/event-stream"
                        
                        async with client.stream(
                            "POST",
                            endpoint,
                            json=payload,
                            headers=stream_headers,
                            timeout=timeout_val
                        ) as response:
                            print(f"DEBUG: Streaming response status for {endpoint}: {response.status_code}")
                            print(f"DEBUG: Streaming response headers: {dict(response.headers)}")
                            
                            if response.status_code == 200:
                                # Read the streaming response
                                full_response = ""
                                json_data_buffer = ""
                                
                                async for chunk in response.aiter_text():
                                    if chunk:
                                        full_response += chunk
                                        print(f"DEBUG: Received chunk: {chunk}")
                                        
                                        # Process each line in the chunk
                                        lines = chunk.split('\n')
                                        for line in lines:
                                            line = line.strip()
                                            if line.startswith('data: '):
                                                # Extract JSON data after 'data: '
                                                data_content = line[6:].strip()
                                                if data_content and data_content != '[DONE]':
                                                    json_data_buffer += data_content
                                            elif line.startswith('event: close') or line == '':
                                                # End of message, try to parse accumulated JSON
                                                if json_data_buffer:
                                                    try:
                                                        data = json.loads(json_data_buffer)
                                                        print(f"DEBUG: SUCCESS! Parsed streaming response: {data}")
                                                        return MCPResponse(**data)
                                                    except json.JSONDecodeError as e:
                                                        print(f"DEBUG: JSON parse error: {e}")
                                                        json_data_buffer = ""  # Reset buffer
                                
                                # Final attempt to parse any remaining data
                                if json_data_buffer:
                                    try:
                                        data = json.loads(json_data_buffer)
                                        print(f"DEBUG: SUCCESS! Final parsed response: {data}")
                                        return MCPResponse(**data)
                                    except Exception as e:
                                        print(f"DEBUG: Final parse failed: {e}")
                                
                                print(f"DEBUG: Full streaming response received: {full_response}")
                            
                            return MCPResponse(jsonrpc="2.0", id="error", error={"code": -32603, "message": "Failed to parse streaming response"})
                    else:
                        # Regular JSON request for standard endpoints
                        response = await client.post(
                            endpoint,
                            json=payload,
                            headers=headers,
                            timeout=timeout_val
                        )
                        
                        print(f"DEBUG: Response status for {endpoint}: {response.status_code}")
                        print(f"DEBUG: Response headers: {dict(response.headers)}")
                        response_text = response.text
                        print(f"DEBUG: Response body: {response_text}")
                        
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
                        
                        # If we get a response from server (even if error), don't try other endpoints for streaming
                        if 'transportType=streamable-http' in endpoint and response.status_code >= 400:
                            print(f"DEBUG: Streaming server responded with error - stopping endpoint attempts")
                            raise ValueError(f"MCP server error ({response.status_code}): {error_text}")
                        
                except ValueError as e:
                    # Re-raise ValueError (like auth errors) immediately
                    print(f"DEBUG: Auth error for {endpoint}: {e}")
                    raise e
                except Exception as e:
                    error_msg = str(e) if str(e) else f"Unknown error: {type(e).__name__}"
                    print(f"DEBUG: Exception for {endpoint}: {error_msg}")
                    continue
            
            # If all endpoints failed, raise the last error
            raise ValueError("All MCP endpoints failed")

    async def _make_streaming_request(self, method: str, params: Optional[Dict[str, Any]] = None, delegated_user: Optional[str] = None) -> AsyncGenerator[Dict[str, Any], None]:
        request = MCPRequest(
            method=method,
            params=params or {},
            id=f"stream_{asyncio.get_event_loop().time()}"
        )
        
        # Add auth headers if available
        if hasattr(self.oauth_client, 'get_auth_headers'):
            try:
                headers = self.oauth_client.get_auth_headers(delegated_user)
                print(f"DEBUG: Using auth headers for streaming {method}: {list(headers.keys())}")
            except Exception as e:
                print(f"DEBUG: Failed to get auth headers: {e}")
                headers = {"Content-Type": "application/json"}
        else:
            headers = {"Content-Type": "application/json"}
        
        # Prepare the JSON payload in standard MCP format
        # Use simple integer ID for better compatibility  
        try:
            simple_id = int(float(request.id.split('_')[-1])) % 1000
        except:
            simple_id = 1
            
        payload = {
            "method": request.method,
            "params": {},
            "jsonrpc": request.jsonrpc,
            "id": simple_id
        }
        
        if request.params is not None:
            payload["params"] = request.params.copy()
        
        # Add _meta with progressToken for streaming compatibility
        payload["params"]["_meta"] = {"progressToken": simple_id}
        
        # Try different common MCP endpoint variations
        base_url = self.server_url.rstrip('/')
        possible_endpoints = [
            base_url,  # Original URL
            f"{base_url}/jsonrpc",  # JSON-RPC endpoint
            f"{base_url}/rpc",  # Generic RPC endpoint
        ]
        
        # Add streaming transport variations for servers that support it
        if '?' in base_url:
            # URL already has query params
            possible_endpoints.append(f"{base_url}&transportType=streamable-http")
        else:
            possible_endpoints.append(f"{base_url}?transportType=streamable-http")
        
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
        print(f"DEBUG: Streaming request payload: {json.dumps(payload, indent=2)}")
        
        async with httpx.AsyncClient() as client:
            for endpoint in possible_endpoints:
                try:
                    print(f"DEBUG: Trying streaming endpoint: {endpoint}")
                    
                    # Check if this is a streaming endpoint
                    if 'transportType=streamable-http' in endpoint:
                        print(f"DEBUG: Using streaming request for MCP server")
                        # Add Accept header for SSE
                        stream_headers = headers.copy()
                        stream_headers["Accept"] = "text/event-stream"
                        
                        async with client.stream(
                            "POST",
                            endpoint,
                            json=payload,
                            headers=stream_headers,
                            timeout=60.0
                        ) as response:
                            print(f"DEBUG: Streaming response status for {endpoint}: {response.status_code}")
                            print(f"DEBUG: Streaming response headers: {dict(response.headers)}")
                            
                            if response.status_code == 200:
                                # Read the streaming response with SSE format
                                json_data_buffer = ""
                                
                                async for chunk in response.aiter_text():
                                    if chunk:
                                        print(f"DEBUG: Streaming chunk: {chunk}")
                                        
                                        # Process each line in the chunk for SSE format
                                        lines = chunk.split('\n')
                                        for line in lines:
                                            line = line.strip()
                                            if line.startswith('data: '):
                                                # Extract JSON data after 'data: '
                                                data_content = line[6:].strip()
                                                if data_content and data_content != '[DONE]':
                                                    json_data_buffer += data_content
                                            elif line.startswith('event: close') or line == '':
                                                # End of message, try to parse accumulated JSON
                                                if json_data_buffer:
                                                    try:
                                                        data = json.loads(json_data_buffer)
                                                        print(f"DEBUG: SUCCESS! Streaming parsed: {data}")
                                                        yield data
                                                        json_data_buffer = ""  # Reset buffer
                                                    except json.JSONDecodeError as e:
                                                        print(f"DEBUG: Streaming JSON parse error: {e}")
                                                        json_data_buffer = ""  # Reset buffer
                                
                                # Final attempt to parse any remaining data
                                if json_data_buffer:
                                    try:
                                        data = json.loads(json_data_buffer)
                                        print(f"DEBUG: Final streaming parsed: {data}")
                                        yield data
                                    except Exception as e:
                                        print(f"DEBUG: Final streaming parse failed: {e}")
                                
                                return  # Successfully streamed from endpoint
                    else:
                        # Regular streaming for standard endpoints
                        async with client.stream(
                            "POST",
                            endpoint,
                            json=payload,
                            headers=headers,
                            timeout=30.0
                        ) as response:
                            print(f"DEBUG: Streaming response status for {endpoint}: {response.status_code}")
                            
                            if response.status_code == 200:
                                print(f"DEBUG: SUCCESS! Starting stream from {endpoint}")
                                
                                async for chunk in response.aiter_text():
                                    if chunk:
                                        try:
                                            # Try to parse each chunk as JSON
                                            data = json.loads(chunk)
                                            yield data
                                        except json.JSONDecodeError:
                                            # If not valid JSON, yield as text
                                            yield {"type": "text", "content": chunk}
                                
                                return  # Successfully streamed from this endpoint
                            else:
                                error_text = await response.aread()
                                print(f"DEBUG: {endpoint} returned {response.status_code}: {error_text.decode()[:400]}")
                        
                        # Don't continue trying other endpoints if we get 401 (auth required)
                        if response.status_code == 401:
                            print(f"DEBUG: Authentication required - stopping endpoint attempts")
                            raise ValueError(f"Authentication required. Please complete OAuth flow first.")
                        
                except ValueError as e:
                    # Re-raise ValueError (like auth errors) immediately
                    print(f"DEBUG: Streaming auth error for {endpoint}: {e}")
                    raise e
                except Exception as e:
                    error_msg = str(e) if str(e) else f"Unknown error: {type(e).__name__}"
                    print(f"DEBUG: Streaming exception for {endpoint}: {error_msg}")
                    continue
            
            # If all endpoints failed, raise the last error
            raise ValueError("All MCP streaming endpoints failed")

    async def initialize(self) -> MCPResponse:
        return await self._make_request("initialize")

    async def list_tools(self) -> MCPResponse:
        return await self._make_request("tools/list")

    async def call_tool(self, name: str, arguments: Dict[str, Any], delegated_user: Optional[str] = None) -> MCPResponse:
        return await self._make_request("tools/call", {"name": name, "arguments": arguments}, delegated_user)

    async def call_tool_stream(self, name: str, arguments: Dict[str, Any], delegated_user: Optional[str] = None) -> AsyncGenerator[Dict[str, Any], None]:
        async for chunk in self._make_streaming_request("tools/call", {"name": name, "arguments": arguments}, delegated_user):
            yield chunk

    async def list_resources(self) -> MCPResponse:
        return await self._make_request("resources/list")

    async def read_resource(self, uri: str) -> MCPResponse:
        return await self._make_request("resources/read", {"uri": uri})

    async def list_prompts(self) -> MCPResponse:
        return await self._make_request("prompts/list")

    async def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> MCPResponse:
        return await self._make_request("prompts/get", {"name": name, "arguments": arguments or {}})