import httpx
import json
from typing import Dict, Any, List, Optional, AsyncGenerator
from oauth_client import OAuth2Client
import asyncio
from dataclasses import dataclass


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


class MCPClient:
    def __init__(self, server_url: str, oauth_client: OAuth2Client):
        self.server_url = server_url
        self.oauth_client = oauth_client
        self.session_id: Optional[str] = None
        
    async def _make_request(self, method: str, params: Optional[Dict[str, Any]] = None, delegated_user: Optional[str] = None) -> MCPResponse:
        if not self.oauth_client.token:
            raise ValueError("OAuth token not available. Please authenticate first.")
            
        request = MCPRequest(
            method=method,
            params=params,
            id=f"req_{asyncio.get_event_loop().time()}"
        )
        
        headers = self.oauth_client.get_auth_headers(delegated_user)
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.server_url}/mcp",
                    json=request.__dict__,
                    headers=headers,
                    timeout=30.0
                )
                response.raise_for_status()
                
                data = response.json()
                return MCPResponse(**data)
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    await self.oauth_client.refresh_token()
                    headers = self.oauth_client.get_auth_headers(delegated_user)
                    
                    response = await client.post(
                        f"{self.server_url}/mcp",
                        json=request.__dict__,
                        headers=headers,
                        timeout=30.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    return MCPResponse(**data)
                else:
                    raise
    
    async def _stream_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> AsyncGenerator[str, None]:
        if not self.oauth_client.token:
            raise ValueError("OAuth token not available. Please authenticate first.")
            
        request = MCPRequest(
            method=method,
            params=params,
            id=f"stream_{asyncio.get_event_loop().time()}"
        )
        
        headers = self.oauth_client.get_auth_headers(delegated_user)
        headers["Accept"] = "text/event-stream"
        
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.server_url}/mcp/stream",
                json=request.__dict__,
                headers=headers,
                timeout=60.0
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            break
                        yield data
    
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
        return await self._make_request("tools/list")
    
    async def call_tool(self, name: str, arguments: Dict[str, Any], delegated_user: Optional[str] = None) -> MCPResponse:
        params = {
            "name": name,
            "arguments": arguments
        }
        return await self._make_request("tools/call", params, delegated_user)
    
    async def call_tool_stream(self, name: str, arguments: Dict[str, Any]) -> AsyncGenerator[str, None]:
        params = {
            "name": name,
            "arguments": arguments
        }
        async for chunk in self._stream_request("tools/call", params):
            yield chunk
    
    async def list_resources(self) -> MCPResponse:
        return await self._make_request("resources/list")
    
    async def read_resource(self, uri: str) -> MCPResponse:
        params = {"uri": uri}
        return await self._make_request("resources/read", params)
    
    async def list_prompts(self) -> MCPResponse:
        return await self._make_request("prompts/list")
    
    async def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> MCPResponse:
        params = {"name": name}
        if arguments:
            params["arguments"] = arguments
        return await self._make_request("prompts/get", params)