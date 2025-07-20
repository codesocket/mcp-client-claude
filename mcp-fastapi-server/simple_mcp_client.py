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
        
        # No proxy session token needed for direct Azure connection
        
        # Prepare the JSON payload with Azure MCP format
        # Use simple integer ID for Azure compatibility  
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
        # params is already initialized above
        
        # Add _meta with progressToken for Azure MCP compatibility
        payload["params"]["_meta"] = {"progressToken": simple_id}
        
        # Check if this looks like an Azure MCP URL
        if 'azure-api.net' in self.server_url and '/cea-mcp/mcp' in self.server_url:
            # For Azure MCP, use streaming endpoint only since it returns text/event-stream
            possible_endpoints = [
                f"{self.server_url}?transportType=streamable-http"  # Azure requires streaming
            ]
        else:
            # Try different common MCP endpoint variations for direct servers
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
        print(f"DEBUG: Server URL: {self.server_url}")
        print(f"DEBUG: Request payload (will be sent as JSON body): {json.dumps(payload, indent=2)}")
        print(f"DEBUG: Request payload raw JSON string: {json.dumps(payload)}")
        
        async with httpx.AsyncClient() as client:
            for endpoint in possible_endpoints:
                try:
                    print(f"DEBUG: Trying endpoint: {endpoint}")
                    print(f"DEBUG: Request headers: {headers}")
                    print(f"DEBUG: Request timeout: {60.0 if 'azure-api.net' in endpoint else 30.0} seconds")
                    
                    # Use longer timeout for Azure since direct calls can be slow
                    timeout_val = 60.0 if 'azure-api.net' in endpoint else 30.0
                    
                    # Check if this is Azure streaming endpoint
                    if 'azure-api.net' in endpoint and 'transportType=streamable-http' in endpoint:
                        print(f"DEBUG: Using streaming request for Azure MCP")
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
                                            print(f"DEBUG: Processing line: '{line}'")
                                            if line.startswith('data: '):
                                                # Extract JSON data after 'data: '
                                                data_content = line[6:].strip()
                                                print(f"DEBUG: Extracted data content: '{data_content}'")
                                                if data_content and data_content != '[DONE]':
                                                    json_data_buffer += data_content
                                                    print(f"DEBUG: Updated JSON buffer: '{json_data_buffer}'")
                                            elif line.startswith('event: close') or line == '':
                                                # End of message, try to parse accumulated JSON
                                                if json_data_buffer:
                                                    try:
                                                        print(f"DEBUG: Attempting to parse JSON buffer: '{json_data_buffer}'")
                                                        data = json.loads(json_data_buffer)
                                                        print(f"DEBUG: SUCCESS! Parsed Azure streaming response: {data}")
                                                        return MCPResponse(**data)
                                                    except json.JSONDecodeError as e:
                                                        print(f"DEBUG: JSON parse error: {e}")
                                                        print(f"DEBUG: Failed JSON buffer: '{json_data_buffer}'")
                                                        print(f"DEBUG: Buffer length: {len(json_data_buffer)}")
                                                        print(f"DEBUG: Buffer bytes: {json_data_buffer.encode('utf-8')}")
                                                        json_data_buffer = ""  # Reset buffer
                                
                                # Final attempt to parse any remaining data
                                if json_data_buffer:
                                    try:
                                        data = json.loads(json_data_buffer)
                                        print(f"DEBUG: SUCCESS! Final parsed Azure response: {data}")
                                        return MCPResponse(**data)
                                    except Exception as e:
                                        print(f"DEBUG: Final parse failed: {e}")
                                        print(f"DEBUG: Final buffer content: {json_data_buffer}")
                                
                                print(f"DEBUG: Full streaming response received: {full_response}")
                                # Fallback: try to extract JSON from the full response
                                try:
                                    lines = full_response.strip().split('\n')
                                    for line in lines:
                                        line = line.strip()
                                        if line.startswith('data: '):
                                            json_data = line[6:].strip()
                                            if json_data and json_data != '[DONE]':
                                                data = json.loads(json_data)
                                                print(f"DEBUG: SUCCESS! Fallback parsed response: {data}")
                                                return MCPResponse(**data)
                                except Exception as e:
                                    print(f"DEBUG: Fallback parsing failed: {e}")
                            
                            return MCPResponse(jsonrpc="2.0", id="error", error={"code": -32603, "message": "Failed to parse streaming response"})
                    else:
                        # Regular JSON request for non-Azure endpoints
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
                        
                        # If we get a response from Azure server (even if error), don't try other endpoints  
                        if 'azure-api.net' in endpoint and response.status_code >= 400:
                            print(f"DEBUG: Azure server responded with error - stopping endpoint attempts")
                            raise ValueError(f"Azure MCP server error ({response.status_code}): {error_text}")
                        
                except ValueError as e:
                    # Re-raise ValueError (like auth errors) immediately
                    print(f"DEBUG: Auth error for {endpoint}: {e}")
                    raise e
                except Exception as e:
                    error_msg = str(e) if str(e) else f"Unknown error: {type(e).__name__}"
                    print(f"DEBUG: Exception for {endpoint}: {error_msg}")
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
        
        # No proxy session token needed for direct Azure connection
        
        # Prepare the JSON payload with Azure MCP format
        # Use simple integer ID for Azure compatibility  
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
        # params is already initialized above
        
        # Add _meta with progressToken for Azure MCP compatibility
        payload["params"]["_meta"] = {"progressToken": simple_id}
        
        # Check if this looks like an Azure MCP URL
        if 'azure-api.net' in self.server_url and '/cea-mcp/mcp' in self.server_url:
            # For Azure MCP, use streaming endpoint only since it returns text/event-stream
            possible_endpoints = [
                f"{self.server_url}?transportType=streamable-http"  # Azure requires streaming
            ]
        else:
            # Try different common MCP endpoint variations for direct servers
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
        print(f"DEBUG: Streaming request payload (will be sent as JSON body): {json.dumps(payload, indent=2)}")
        print(f"DEBUG: Streaming request payload raw JSON string: {json.dumps(payload)}")
        
        async with httpx.AsyncClient() as client:
            for endpoint in possible_endpoints:
                try:
                    print(f"DEBUG: Trying streaming endpoint: {endpoint}")
                    
                    # Check if this is Azure streaming endpoint
                    if 'azure-api.net' in endpoint and 'transportType=streamable-http' in endpoint:
                        print(f"DEBUG: Using streaming request for Azure MCP")
                        # Add Accept header for SSE
                        stream_headers = headers.copy()
                        stream_headers["Accept"] = "text/event-stream"
                        
                        async with client.stream(
                            "POST",
                            endpoint,
                            json=payload,
                            headers=stream_headers,
                            timeout=60.0 if 'azure-api.net' in endpoint else 30.0
                        ) as response:
                            print(f"DEBUG: Azure streaming response status for {endpoint}: {response.status_code}")
                            print(f"DEBUG: Azure streaming response headers: {dict(response.headers)}")
                            
                            if response.status_code == 200:
                                # Read the streaming response with Azure SSE format
                                full_response = ""
                                json_data_buffer = ""
                                
                                async for chunk in response.aiter_text():
                                    if chunk:
                                        full_response += chunk
                                        print(f"DEBUG: Azure streaming chunk: {chunk}")
                                        
                                        # Process each line in the chunk for Azure SSE format
                                        lines = chunk.split('\n')
                                        for line in lines:
                                            line = line.strip()
                                            if line.startswith('data: '):
                                                # Extract JSON data after 'data: '
                                                data_content = line[6:].strip()
                                                print(f"DEBUG: Extracted data content: '{data_content}'")
                                                if data_content and data_content != '[DONE]':
                                                    json_data_buffer += data_content
                                                    print(f"DEBUG: Updated JSON buffer: '{json_data_buffer}'")
                                            elif line.startswith('event: close') or line == '':
                                                # End of message, try to parse accumulated JSON
                                                if json_data_buffer:
                                                    try:
                                                        print(f"DEBUG: Attempting to parse streaming JSON buffer: '{json_data_buffer}'")
                                                        data = json.loads(json_data_buffer)
                                                        print(f"DEBUG: SUCCESS! Azure streaming parsed: {data}")
                                                        yield data
                                                        json_data_buffer = ""  # Reset buffer
                                                    except json.JSONDecodeError as e:
                                                        print(f"DEBUG: Azure streaming JSON parse error: {e}")
                                                        print(f"DEBUG: Failed streaming JSON buffer: '{json_data_buffer}'")
                                                        print(f"DEBUG: Streaming buffer length: {len(json_data_buffer)}")
                                                        print(f"DEBUG: Streaming buffer bytes: {json_data_buffer.encode('utf-8')}")
                                                        json_data_buffer = ""  # Reset buffer
                                
                                # Final attempt to parse any remaining data
                                if json_data_buffer:
                                    try:
                                        data = json.loads(json_data_buffer)
                                        print(f"DEBUG: Final Azure streaming parsed: {data}")
                                        yield data
                                    except Exception as e:
                                        print(f"DEBUG: Final Azure streaming parse failed: {e}")
                                
                                return  # Successfully streamed from Azure endpoint
                    else:
                        # Regular streaming for non-Azure endpoints
                        async with client.stream(
                            "POST",
                            endpoint,
                            json=payload,
                            headers=headers,
                            timeout=60.0 if 'azure-api.net' in endpoint else 30.0
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
                                
                                # If we get a response from Azure server (even if error), don't try other endpoints
                                if 'azure-api.net' in endpoint and response.status_code >= 400:
                                    print(f"DEBUG: Azure server responded with error - stopping endpoint attempts")
                                    raise ValueError(f"Azure MCP server error ({response.status_code}): {error_text.decode()[:400]}")
                        
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
        # Try to get real tools from MCP server first - skip initialize for Azure
        try:
            response = await self._make_request("tools/list")
            if response.result and "tools" in response.result:
                return response
        except Exception as e:
            print(f"DEBUG: Failed to get real tools, error: {e}")
        
        # Return empty tools list if real tools unavailable
        return MCPResponse(
            jsonrpc="2.0",
            id="empty_tools", 
            result={"tools": []}
        )
    
    async def call_tool(self, name: str, arguments: Dict[str, Any], delegated_user: Optional[str] = None) -> MCPResponse:
        # Try to call real tool on MCP server first
        try:
            params = {"name": name, "arguments": arguments}
            print(f"DEBUG: call_tool - name: {name}, arguments: {arguments}, delegated_user: {delegated_user}")
            print(f"DEBUG: call_tool - params: {params}")
            response = await self._make_request("tools/call", params, delegated_user)
            if response.result:
                return response
        except Exception as e:
            print(f"DEBUG: Failed to call real tool {name}, error: {e}")
        
        # Return error if tool unavailable
        return MCPResponse(
            jsonrpc="2.0",
            id=f"tool_error_{name}",
            error={"code": -32601, "message": f"Tool '{name}' not available"}
        )
    
    async def call_tool_stream(self, name: str, arguments: Dict[str, Any], delegated_user: Optional[str] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Call a tool with streaming response"""
        # Try to call real tool on MCP server first
        try:
            params = {"name": name, "arguments": arguments}
            print(f"DEBUG: call_tool_stream - name: {name}, arguments: {arguments}, delegated_user: {delegated_user}")
            print(f"DEBUG: call_tool_stream - params: {params}")
            async for chunk in self._make_streaming_request("tools/call", params, delegated_user):
                yield chunk
            return
        except Exception as e:
            print(f"DEBUG: Failed to stream tool {name}, error: {e}")
        
        # Return error if streaming tool unavailable
        yield {"type": "error", "error": f"Tool '{name}' not available for streaming"}
    
    async def list_resources(self) -> MCPResponse:
        # Try to get real resources from MCP server first
        try:
            response = await self._make_request("resources/list")
            if response.result and "resources" in response.result:
                return response
        except Exception as e:
            print(f"DEBUG: Failed to get real resources, error: {e}")
        
        # Return empty resources list if real resources unavailable
        return MCPResponse(
            jsonrpc="2.0",
            id="empty_resources",
            result={"resources": []}
        )
    
    async def read_resource(self, uri: str) -> MCPResponse:
        # Try to read real resource from MCP server first
        try:
            params = {"uri": uri}
            response = await self._make_request("resources/read", params)
            if response.result:
                return response
        except Exception as e:
            print(f"DEBUG: Failed to read real resource {uri}, error: {e}")
        
        # Return error if resource unavailable
        return MCPResponse(
            jsonrpc="2.0",
            id=f"resource_error_{uri}",
            error={"code": -32601, "message": f"Resource '{uri}' not available"}
        )
    
    async def list_prompts(self) -> MCPResponse:
        # Try to get real prompts from MCP server first
        try:
            response = await self._make_request("prompts/list")
            if response.result and "prompts" in response.result:
                return response
        except Exception as e:
            print(f"DEBUG: Failed to get real prompts, error: {e}")
        
        # Return empty prompts list if real prompts unavailable
        return MCPResponse(
            jsonrpc="2.0",
            id="empty_prompts",
            result={"prompts": []}
        )
    
    async def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> MCPResponse:
        # Try to get real prompt from MCP server first
        try:
            params = {"name": name}
            if arguments:
                params["arguments"] = arguments
            response = await self._make_request("prompts/get", params)
            if response.result:
                return response
        except Exception as e:
            print(f"DEBUG: Failed to get real prompt {name}, error: {e}")
        
        # Return error if prompt unavailable
        return MCPResponse(
            jsonrpc="2.0",
            id=f"prompt_error_{name}",
            error={"code": -32601, "message": f"Prompt '{name}' not available"}
        )