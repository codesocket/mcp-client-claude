import httpx
import json
import secrets
import base64
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib


@dataclass
class ClientRegistration:
    client_id: str
    client_secret: str
    client_id_issued_at: int
    client_secret_expires_at: int
    registration_access_token: str
    registration_client_uri: str


@dataclass
class DelegationToken:
    access_token: str
    token_type: str
    expires_in: int
    scope: str
    delegated_user: str
    issued_at: datetime


class EnhancedOAuth2Client:
    def __init__(self, 
                 registration_endpoint: str,
                 auth_url: str,
                 token_url: str,
                 delegation_endpoint: str,
                 redirect_uri: str,
                 client_id: Optional[str] = None,
                 client_secret: Optional[str] = None):
        self.registration_endpoint = registration_endpoint
        self.auth_url = auth_url
        self.token_url = token_url
        self.delegation_endpoint = delegation_endpoint
        self.redirect_uri = redirect_uri
        self.client_id = client_id
        self.client_secret = client_secret
        self.token: Optional[Dict[str, Any]] = None
        self.client_registration: Optional[ClientRegistration] = None
        self.delegation_tokens: Dict[str, DelegationToken] = {}
        self.pkce_verifier: Optional[str] = None
        self.pkce_challenge: Optional[str] = None
    
    def _generate_pkce_challenge(self) -> tuple[str, str]:
        """Generate PKCE code verifier and challenge for OAuth 2.1"""
        verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        return verifier, challenge
    
    async def register_client(self, 
                            client_name: str,
                            redirect_uris: List[str],
                            grant_types: List[str] = None,
                            scope: str = "read write",
                            token_endpoint_auth_method: str = "client_secret_basic") -> ClientRegistration:
        """
        Perform Dynamic Client Registration (DCR) as per RFC 7591
        """
        if grant_types is None:
            grant_types = ["authorization_code", "refresh_token", "urn:ietf:params:oauth:grant-type:token-exchange"]
        
        registration_data = {
            "client_name": client_name,
            "redirect_uris": redirect_uris,
            "grant_types": grant_types,
            "scope": scope,
            "token_endpoint_auth_method": token_endpoint_auth_method,
            "response_types": ["code"],
            "application_type": "web"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.registration_endpoint,
                json=registration_data,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            data = response.json()
            
            self.client_registration = ClientRegistration(
                client_id=data["client_id"],
                client_secret=data.get("client_secret"),
                client_id_issued_at=data.get("client_id_issued_at"),
                client_secret_expires_at=data.get("client_secret_expires_at"),
                registration_access_token=data.get("registration_access_token"),
                registration_client_uri=data.get("registration_client_uri")
            )
            
            self.client_id = self.client_registration.client_id
            self.client_secret = self.client_registration.client_secret
            
            return self.client_registration
    
    async def update_client_registration(self, updates: Dict[str, Any]) -> ClientRegistration:
        """Update client registration using the registration access token"""
        if not self.client_registration:
            raise ValueError("No client registration available")
        
        headers = {
            "Authorization": f"Bearer {self.client_registration.registration_access_token}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.put(
                self.client_registration.registration_client_uri,
                json=updates,
                headers=headers
            )
            response.raise_for_status()
            
            data = response.json()
            
            self.client_registration = ClientRegistration(
                client_id=data["client_id"],
                client_secret=data.get("client_secret"),
                client_id_issued_at=data.get("client_id_issued_at"),
                client_secret_expires_at=data.get("client_secret_expires_at"),
                registration_access_token=data.get("registration_access_token"),
                registration_client_uri=data.get("registration_client_uri")
            )
            
            return self.client_registration
    
    def get_authorization_url(self, scope: str = "read", state: Optional[str] = None) -> str:
        """Generate OAuth 2.1 authorization URL with PKCE"""
        if not self.client_id:
            raise ValueError("Client ID not available. Register client first.")
        
        # Handle empty auth_url - this should not happen in normal flow
        if not self.auth_url or self.auth_url.strip() == "":
            raise ValueError(f"Authorization URL is empty. This indicates a configuration issue. auth_url = '{self.auth_url}'")
        
        self.pkce_verifier, self.pkce_challenge = self._generate_pkce_challenge()
        
        if state is None:
            state = secrets.token_urlsafe(32)
        
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": scope,
            "state": state,
            "code_challenge": self.pkce_challenge,
            "code_challenge_method": "S256"
        }
        return f"{self.auth_url}?{urlencode(params)}"
    
    async def exchange_code_for_token(self, authorization_code: str) -> Dict[str, Any]:
        """Exchange authorization code for tokens using PKCE"""
        if not self.pkce_verifier:
            raise ValueError("PKCE verifier not available")
        
        data = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": self.pkce_verifier
        }
        
        # Add client authentication if client_secret is available
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if self.client_secret:
            auth_string = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            headers["Authorization"] = f"Basic {auth_string}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.token_url, data=data, headers=headers)
            response.raise_for_status()
            
            self.token = response.json()
            return self.token
    
    async def refresh_token(self) -> Dict[str, Any]:
        """Refresh access token"""
        if not self.token or "refresh_token" not in self.token:
            raise ValueError("No refresh token available")
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.token["refresh_token"]
        }
        
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if self.client_secret:
            auth_string = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            headers["Authorization"] = f"Basic {auth_string}"
        else:
            data["client_id"] = self.client_id
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.token_url, data=data, headers=headers)
            response.raise_for_status()
            
            self.token = response.json()
            return self.token
    
    async def exchange_token_for_delegation(self, 
                                          subject_token: str,
                                          target_user: str,
                                          scope: str = "read",
                                          audience: Optional[str] = None) -> DelegationToken:
        """
        Perform token exchange for user on behalf of flow (RFC 8693)
        """
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": subject_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "scope": scope,
            "actor_token": self.token["access_token"] if self.token else None,
            "actor_token_type": "urn:ietf:params:oauth:token-type:access_token"
        }
        
        if audience:
            data["audience"] = audience
        
        # Add custom parameter for target user
        data["target_user"] = target_user
        
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if self.client_secret:
            auth_string = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            headers["Authorization"] = f"Basic {auth_string}"
        else:
            data["client_id"] = self.client_id
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.delegation_endpoint, data=data, headers=headers)
            response.raise_for_status()
            
            token_data = response.json()
            
            delegation_token = DelegationToken(
                access_token=token_data["access_token"],
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=token_data.get("expires_in", 3600),
                scope=token_data.get("scope", scope),
                delegated_user=target_user,
                issued_at=datetime.utcnow()
            )
            
            self.delegation_tokens[target_user] = delegation_token
            return delegation_token
    
    async def get_user_consent_for_delegation(self, target_user: str, scope: str = "read") -> str:
        """
        Get user consent URL for delegation flow
        """
        state = secrets.token_urlsafe(32)
        
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": scope,
            "state": state,
            "delegation_target": target_user,
            "prompt": "consent"
        }
        
        return f"{self.auth_url}?{urlencode(params)}"
    
    def get_auth_headers(self, delegated_user: Optional[str] = None) -> Dict[str, str]:
        """Get authorization headers for API calls"""
        if delegated_user and delegated_user in self.delegation_tokens:
            delegation_token = self.delegation_tokens[delegated_user]
            # Check if token is expired
            if datetime.utcnow() > delegation_token.issued_at + timedelta(seconds=delegation_token.expires_in):
                raise ValueError(f"Delegation token for {delegated_user} has expired")
            
            return {
                "Authorization": f"{delegation_token.token_type} {delegation_token.access_token}",
                "Content-Type": "application/json",
                "X-Delegated-User": delegated_user
            }
        elif self.token:
            return {
                "Authorization": f"Bearer {self.token['access_token']}",
                "Content-Type": "application/json"
            }
        else:
            raise ValueError("No access token available")
    
    def is_delegation_token_valid(self, delegated_user: str) -> bool:
        """Check if delegation token is still valid"""
        if delegated_user not in self.delegation_tokens:
            return False
        
        delegation_token = self.delegation_tokens[delegated_user]
        return datetime.utcnow() < delegation_token.issued_at + timedelta(seconds=delegation_token.expires_in)
    
    def get_client_info(self) -> Optional[Dict[str, Any]]:
        """Get current client registration information"""
        if not self.client_registration:
            return None
        
        return {
            "client_id": self.client_registration.client_id,
            "client_secret_expires_at": self.client_registration.client_secret_expires_at,
            "registration_client_uri": self.client_registration.registration_client_uri,
            "has_registration_token": bool(self.client_registration.registration_access_token)
        }