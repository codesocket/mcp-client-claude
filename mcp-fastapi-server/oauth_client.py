import httpx
from typing import Optional, Dict, Any
import json
from urllib.parse import urlencode


class OAuth2Client:
    def __init__(self, client_id: str, client_secret: str, auth_url: str, token_url: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.auth_url = auth_url
        self.token_url = token_url
        self.redirect_uri = redirect_uri
        self.token: Optional[Dict[str, Any]] = None
        
    def get_authorization_url(self, scope: str = "read") -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": scope,
            "state": "random_state_string"
        }
        return f"{self.auth_url}?{urlencode(params)}"
    
    async def exchange_code_for_token(self, authorization_code: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            data = {
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": self.redirect_uri,
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }
            
            response = await client.post(self.token_url, data=data)
            response.raise_for_status()
            
            self.token = response.json()
            return self.token
    
    async def refresh_token(self) -> Dict[str, Any]:
        if not self.token or "refresh_token" not in self.token:
            raise ValueError("No refresh token available")
            
        async with httpx.AsyncClient() as client:
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.token["refresh_token"],
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }
            
            response = await client.post(self.token_url, data=data)
            response.raise_for_status()
            
            self.token = response.json()
            return self.token
    
    def get_auth_headers(self) -> Dict[str, str]:
        if not self.token:
            raise ValueError("No access token available")
        
        return {
            "Authorization": f"Bearer {self.token['access_token']}",
            "Content-Type": "application/json"
        }