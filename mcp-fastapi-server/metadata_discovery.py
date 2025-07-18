import httpx
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse


@dataclass
class OAuthMetadata:
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: Optional[str] = None
    introspection_endpoint: Optional[str] = None
    revocation_endpoint: Optional[str] = None
    jwks_uri: Optional[str] = None
    issuer: Optional[str] = None
    scopes_supported: list = None
    response_types_supported: list = None
    grant_types_supported: list = None
    token_endpoint_auth_methods_supported: list = None
    code_challenge_methods_supported: list = None


@dataclass
class MCPMetadata:
    name: str
    version: str
    oauth_metadata_url: Optional[str] = None
    oauth_authorization_endpoint: Optional[str] = None
    oauth_token_endpoint: Optional[str] = None
    oauth_registration_endpoint: Optional[str] = None
    supported_features: list = None
    description: Optional[str] = None


class MetadataDiscoveryService:
    def __init__(self):
        self.timeout = 30.0
    
    async def discover_mcp_metadata(self, mcp_server_url: str) -> MCPMetadata:
        """
        Discover MCP server metadata and OAuth configuration
        """
        # Normalize URL
        if not mcp_server_url.startswith(('http://', 'https://')):
            mcp_server_url = f"https://{mcp_server_url}"
        
        # Try standard metadata endpoints
        metadata_urls = [
            urljoin(mcp_server_url, "/.well-known/mcp-configuration"),
            urljoin(mcp_server_url, "/metadata"),
            urljoin(mcp_server_url, "/.well-known/oauth-authorization-server"),
            urljoin(mcp_server_url, "/oauth/metadata")
        ]
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for metadata_url in metadata_urls:
                try:
                    print(f"DEBUG: Trying metadata URL: {metadata_url}")
                    response = await client.get(metadata_url)
                    print(f"DEBUG: Response status: {response.status_code}")
                    if response.status_code == 200:
                        data = response.json()
                        print(f"DEBUG: Found metadata at {metadata_url}")
                        return self._parse_mcp_metadata(data, mcp_server_url)
                except Exception as e:
                    print(f"DEBUG: Exception for {metadata_url}: {e}")
                    continue
            
            # If no metadata found, try to construct from base URL
            print(f"DEBUG: No metadata found, constructing default for {mcp_server_url}")
            return self._construct_default_metadata(mcp_server_url)
    
    async def discover_oauth_metadata(self, oauth_metadata_url: str) -> OAuthMetadata:
        """
        Discover OAuth 2.1 metadata from the authorization server
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(oauth_metadata_url)
                response.raise_for_status()
                data = response.json()
                
                return OAuthMetadata(
                    authorization_endpoint=data["authorization_endpoint"],
                    token_endpoint=data["token_endpoint"],
                    registration_endpoint=data.get("registration_endpoint"),
                    introspection_endpoint=data.get("introspection_endpoint"),
                    revocation_endpoint=data.get("revocation_endpoint"),
                    jwks_uri=data.get("jwks_uri"),
                    issuer=data.get("issuer"),
                    scopes_supported=data.get("scopes_supported", ["read", "write"]),
                    response_types_supported=data.get("response_types_supported", ["code"]),
                    grant_types_supported=data.get("grant_types_supported", ["authorization_code", "refresh_token"]),
                    token_endpoint_auth_methods_supported=data.get("token_endpoint_auth_methods_supported", ["client_secret_basic"]),
                    code_challenge_methods_supported=data.get("code_challenge_methods_supported", ["S256"])
                )
            except Exception as e:
                raise Exception(f"Failed to discover OAuth metadata: {str(e)}")
    
    async def discover_full_configuration(self, mcp_server_url: str) -> Dict[str, Any]:
        """
        Discover both MCP and OAuth metadata in one call
        """
        # Step 1: Discover MCP metadata
        mcp_metadata = await self.discover_mcp_metadata(mcp_server_url)
        
        oauth_metadata = None
        if mcp_metadata.oauth_metadata_url:
            # Step 2: Discover OAuth metadata if URL is provided
            try:
                oauth_metadata = await self.discover_oauth_metadata(mcp_metadata.oauth_metadata_url)
            except Exception as e:
                # Fallback to constructing OAuth URLs from MCP metadata
                oauth_metadata = self._construct_oauth_from_mcp_metadata(mcp_metadata)
        else:
            # Construct OAuth metadata from MCP metadata
            oauth_metadata = self._construct_oauth_from_mcp_metadata(mcp_metadata)
        
        return {
            "mcp_metadata": {
                "name": mcp_metadata.name,
                "version": mcp_metadata.version,
                "description": mcp_metadata.description,
                "supported_features": mcp_metadata.supported_features or [],
                "server_url": mcp_server_url
            },
            "oauth_metadata": {
                "authorization_endpoint": oauth_metadata.authorization_endpoint,
                "token_endpoint": oauth_metadata.token_endpoint,
                "registration_endpoint": oauth_metadata.registration_endpoint,
                "introspection_endpoint": oauth_metadata.introspection_endpoint,
                "revocation_endpoint": oauth_metadata.revocation_endpoint,
                "issuer": oauth_metadata.issuer,
                "scopes_supported": oauth_metadata.scopes_supported,
                "response_types_supported": oauth_metadata.response_types_supported,
                "grant_types_supported": oauth_metadata.grant_types_supported,
                "token_endpoint_auth_methods_supported": oauth_metadata.token_endpoint_auth_methods_supported,
                "code_challenge_methods_supported": oauth_metadata.code_challenge_methods_supported
            }
        }
    
    def _parse_mcp_metadata(self, data: Dict[str, Any], server_url: str) -> MCPMetadata:
        """Parse MCP metadata from server response"""
        print(f"DEBUG: _parse_mcp_metadata called with data = {data}")
        
        # Handle OAuth metadata format (standard OAuth discovery response)
        if "authorization_endpoint" in data and "token_endpoint" in data:
            print("DEBUG: Detected OAuth metadata format, mapping to MCP format")
            result = MCPMetadata(
                name=data.get("name", f"MCP Server at {urlparse(server_url).netloc}"),
                version=data.get("version", "1.0.0"),
                oauth_metadata_url=data.get("oauth_metadata_url"),
                oauth_authorization_endpoint=data.get("authorization_endpoint"),
                oauth_token_endpoint=data.get("token_endpoint"),
                oauth_registration_endpoint=data.get("registration_endpoint"),
                supported_features=data.get("supported_features", ["tools", "resources", "prompts"]),
                description=data.get("description", f"MCP Server discovered at {server_url}")
            )
        else:
            # Handle MCP metadata format
            print("DEBUG: Detected MCP metadata format")
            result = MCPMetadata(
                name=data.get("name", "Unknown MCP Server"),
                version=data.get("version", "1.0.0"),
                oauth_metadata_url=data.get("oauth_metadata_url"),
                oauth_authorization_endpoint=data.get("oauth_authorization_endpoint"),
                oauth_token_endpoint=data.get("oauth_token_endpoint"),
                oauth_registration_endpoint=data.get("oauth_registration_endpoint"),
                supported_features=data.get("supported_features", ["tools", "resources", "prompts"]),
                description=data.get("description")
            )
        
        print(f"DEBUG: Created MCPMetadata with oauth_authorization_endpoint = {result.oauth_authorization_endpoint}")
        return result
    
    def _construct_default_metadata(self, server_url: str) -> MCPMetadata:
        """Construct default metadata when none is discovered"""
        parsed_url = urlparse(server_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        print(f"DEBUG: server_url = {server_url}")
        print(f"DEBUG: parsed_url = {parsed_url}")
        print(f"DEBUG: base_url = {base_url}")
        
        auth_endpoint = urljoin(base_url, "/oauth/authorize")
        token_endpoint = urljoin(base_url, "/oauth/token")
        registration_endpoint = urljoin(base_url, "/oauth/register")
        
        print(f"DEBUG: auth_endpoint = {auth_endpoint}")
        print(f"DEBUG: token_endpoint = {token_endpoint}")
        
        return MCPMetadata(
            name=f"MCP Server at {parsed_url.netloc}",
            version="1.0.0",
            oauth_authorization_endpoint=auth_endpoint,
            oauth_token_endpoint=token_endpoint,
            oauth_registration_endpoint=registration_endpoint,
            supported_features=["tools", "resources", "prompts"],
            description=f"MCP Server discovered at {server_url}"
        )
    
    def _construct_oauth_from_mcp_metadata(self, mcp_metadata: MCPMetadata) -> OAuthMetadata:
        """Construct OAuth metadata from MCP metadata"""
        return OAuthMetadata(
            authorization_endpoint=mcp_metadata.oauth_authorization_endpoint or "",
            token_endpoint=mcp_metadata.oauth_token_endpoint or "",
            registration_endpoint=mcp_metadata.oauth_registration_endpoint,
            scopes_supported=["read", "write", "admin"],
            response_types_supported=["code"],
            grant_types_supported=["authorization_code", "refresh_token", "urn:ietf:params:oauth:grant-type:token-exchange"],
            token_endpoint_auth_methods_supported=["client_secret_basic", "client_secret_post"],
            code_challenge_methods_supported=["S256"]
        )
    
    async def validate_endpoints(self, oauth_metadata: OAuthMetadata) -> Dict[str, bool]:
        """Validate that OAuth endpoints are accessible"""
        results = {}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Test authorization endpoint
            try:
                response = await client.get(oauth_metadata.authorization_endpoint, follow_redirects=False)
                results["authorization_endpoint"] = response.status_code in [200, 302, 400]  # 400 is OK for missing params
            except Exception:
                results["authorization_endpoint"] = False
            
            # Test token endpoint
            try:
                response = await client.post(oauth_metadata.token_endpoint, data={})
                results["token_endpoint"] = response.status_code in [400, 401]  # Should reject empty request
            except Exception:
                results["token_endpoint"] = False
            
            # Test registration endpoint if available
            if oauth_metadata.registration_endpoint:
                try:
                    response = await client.post(oauth_metadata.registration_endpoint, json={})
                    results["registration_endpoint"] = response.status_code in [400, 401]  # Should reject empty request
                except Exception:
                    results["registration_endpoint"] = False
            else:
                results["registration_endpoint"] = None
        
        return results