import asyncio
import secrets
import webbrowser
from typing import Dict, Any, Optional, AsyncGenerator
from dataclasses import dataclass
from enum import Enum
import logging

from metadata_discovery import MetadataDiscoveryService, OAuthMetadata
from enhanced_oauth_client import EnhancedOAuth2Client, ClientRegistration


class FlowStep(Enum):
    DISCOVER_METADATA = "discover_metadata"
    REGISTER_CLIENT = "register_client"
    GET_AUTHORIZATION_URL = "get_authorization_url"
    WAIT_FOR_CODE = "wait_for_code"
    EXCHANGE_CODE = "exchange_code"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class FlowStatus:
    step: FlowStep
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    progress: int = 0  # 0-100
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            "step": self.step.value,
            "message": self.message,
            "data": self.data,
            "error": self.error,
            "progress": self.progress
        }


class OAuthFlowOrchestrator:
    def __init__(self):
        self.metadata_service = MetadataDiscoveryService()
        self.oauth_client: Optional[EnhancedOAuth2Client] = None
        self.discovered_config: Optional[Dict[str, Any]] = None
        self.client_registration: Optional[ClientRegistration] = None
        self.authorization_url: Optional[str] = None
        self.logger = logging.getLogger(__name__)
    
    async def start_full_oauth_flow(self, 
                                   mcp_server_url: str,
                                   client_name: str = "MCP Client Application",
                                   redirect_uri: str = "http://localhost:8001/auth/callback") -> AsyncGenerator[FlowStatus, None]:
        """
        Execute the complete OAuth 2.1 flow with Dynamic Client Registration
        """
        try:
            # Step 1: Discover metadata
            yield FlowStatus(
                step=FlowStep.DISCOVER_METADATA,
                message=f"Discovering metadata for {mcp_server_url}...",
                progress=10
            )
            
            self.discovered_config = await self.metadata_service.discover_full_configuration(mcp_server_url)
            print(f"DEBUG: discovered_config = {self.discovered_config}")
            
            yield FlowStatus(
                step=FlowStep.DISCOVER_METADATA,
                message="Metadata discovered successfully",
                data={
                    "mcp_server": self.discovered_config["mcp_metadata"],
                    "oauth_endpoints": {
                        "authorization": self.discovered_config["oauth_metadata"]["authorization_endpoint"],
                        "token": self.discovered_config["oauth_metadata"]["token_endpoint"],
                        "registration": self.discovered_config["oauth_metadata"]["registration_endpoint"]
                    }
                },
                progress=25
            )
            
            # Step 2: Initialize OAuth client
            oauth_metadata = self.discovered_config["oauth_metadata"]
            print(f"DEBUG: oauth_metadata = {oauth_metadata}")
            print(f"DEBUG: authorization_endpoint = {oauth_metadata.get('authorization_endpoint')}")
            self.oauth_client = EnhancedOAuth2Client(
                registration_endpoint=oauth_metadata["registration_endpoint"] or "",
                auth_url=oauth_metadata["authorization_endpoint"],
                token_url=oauth_metadata["token_endpoint"],
                delegation_endpoint=oauth_metadata["token_endpoint"],  # Use token endpoint for delegation
                redirect_uri=redirect_uri
            )
            
            # Step 3: Register client (if registration endpoint available)
            if oauth_metadata["registration_endpoint"]:
                yield FlowStatus(
                    step=FlowStep.REGISTER_CLIENT,
                    message="Registering OAuth client...",
                    progress=40
                )
                
                try:
                    self.client_registration = await self.oauth_client.register_client(
                        client_name=client_name,
                        redirect_uris=[redirect_uri],
                        grant_types=["authorization_code", "refresh_token"],
                        scope="read write"
                    )
                    
                    yield FlowStatus(
                        step=FlowStep.REGISTER_CLIENT,
                        message="Client registered successfully",
                        data={
                            "client_id": self.client_registration.client_id,
                            "expires_at": self.client_registration.client_secret_expires_at
                        },
                        progress=55
                    )
                except Exception as e:
                    # Client registration failed, but we can continue without it
                    yield FlowStatus(
                        step=FlowStep.REGISTER_CLIENT,
                        message=f"Client registration failed: {str(e)} - continuing with static client",
                        error=str(e),
                        progress=55
                    )
                    # Set up default client credentials for demo
                    self.oauth_client.client_id = "demo_client_id"
                    self.oauth_client.client_secret = "demo_client_secret"
            else:
                yield FlowStatus(
                    step=FlowStep.REGISTER_CLIENT,
                    message="No registration endpoint available - using default client configuration",
                    progress=55
                )
                # Set up default client credentials for demo
                self.oauth_client.client_id = "demo_client_id"
                self.oauth_client.client_secret = "demo_client_secret"
            
            # Step 4: Generate authorization URL
            yield FlowStatus(
                step=FlowStep.GET_AUTHORIZATION_URL,
                message="Generating authorization URL...",
                progress=70
            )
            
            self.authorization_url = self.oauth_client.get_authorization_url(
                scope="read write",
                state=secrets.token_urlsafe(32)
            )
            
            yield FlowStatus(
                step=FlowStep.GET_AUTHORIZATION_URL,
                message="Authorization URL generated - user consent required",
                data={
                    "authorization_url": self.authorization_url,
                    "instructions": "Visit the authorization URL to grant consent, then provide the authorization code"
                },
                progress=85
            )
            
            # Step 5: Wait for authorization code (this will be provided separately)
            yield FlowStatus(
                step=FlowStep.WAIT_FOR_CODE,
                message="Waiting for authorization code from user...",
                data={"authorization_url": self.authorization_url},
                progress=90
            )
            
        except Exception as e:
            self.logger.error(f"OAuth flow failed: {e}")
            yield FlowStatus(
                step=FlowStep.ERROR,
                message="OAuth flow failed",
                error=str(e),
                progress=0
            )
    
    async def complete_authorization(self, authorization_code: str) -> FlowStatus:
        """
        Complete the OAuth flow by exchanging the authorization code for tokens
        """
        if not self.oauth_client:
            return FlowStatus(
                step=FlowStep.ERROR,
                message="OAuth client not initialized",
                error="Must run start_full_oauth_flow first",
                progress=0
            )
        
        try:
            # Exchange authorization code for access token
            token_response = await self.oauth_client.exchange_code_for_token(authorization_code)
            
            return FlowStatus(
                step=FlowStep.COMPLETE,
                message="OAuth flow completed successfully",
                data={
                    "token_type": token_response.get("token_type", "Bearer"),
                    "expires_in": token_response.get("expires_in"),
                    "scope": token_response.get("scope"),
                    "has_refresh_token": "refresh_token" in token_response
                },
                progress=100
            )
            
        except Exception as e:
            self.logger.error(f"Token exchange failed: {e}")
            return FlowStatus(
                step=FlowStep.ERROR,
                message="Token exchange failed",
                error=str(e),
                progress=90
            )
    
    def get_current_oauth_client(self) -> Optional[EnhancedOAuth2Client]:
        """Get the configured OAuth client"""
        return self.oauth_client
    
    def get_discovered_config(self) -> Optional[Dict[str, Any]]:
        """Get the discovered configuration"""
        return self.discovered_config
    
    def get_client_registration(self) -> Optional[ClientRegistration]:
        """Get the client registration details"""
        return self.client_registration
    
    async def validate_configuration(self) -> Dict[str, Any]:
        """Validate the current OAuth configuration"""
        if not self.discovered_config:
            return {"valid": False, "error": "No configuration discovered"}
        
        oauth_metadata_dict = self.discovered_config["oauth_metadata"]
        oauth_metadata = OAuthMetadata(**oauth_metadata_dict)
        
        # Validate endpoints
        endpoint_status = await self.metadata_service.validate_endpoints(oauth_metadata)
        
        return {
            "valid": all(status for status in endpoint_status.values() if status is not None),
            "endpoint_status": endpoint_status,
            "has_registration": oauth_metadata.registration_endpoint is not None,
            "supported_features": self.discovered_config["mcp_metadata"]["supported_features"]
        }
    
    def reset_flow(self):
        """Reset the OAuth flow to start over"""
        self.oauth_client = None
        self.discovered_config = None
        self.client_registration = None
        self.authorization_url = None