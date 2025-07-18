from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Request
from fastapi.responses import StreamingResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import json
import asyncio
from enhanced_oauth_client import EnhancedOAuth2Client
from simple_mcp_client import SimpleMCPClient
from llm_inference import LLMInferenceService, LLMProvider
from intelligent_mcp_client import IntelligentMCPClient
from metadata_discovery import MetadataDiscoveryService
from oauth_flow_orchestrator import OAuthFlowOrchestrator
import os


app = FastAPI(title="MCP Client API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:4000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth_client = EnhancedOAuth2Client(
    registration_endpoint=os.getenv("OAUTH_REGISTRATION_ENDPOINT", "https://auth.example.com/oauth/register"),
    auth_url=os.getenv("OAUTH_AUTH_URL", "https://auth.example.com/oauth/authorize"),
    token_url=os.getenv("OAUTH_TOKEN_URL", "https://auth.example.com/oauth/token"),
    delegation_endpoint=os.getenv("OAUTH_DELEGATION_ENDPOINT", "https://auth.example.com/oauth/token"),
    redirect_uri=os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8001/auth/callback"),
    client_id=os.getenv("OAUTH_CLIENT_ID"),
    client_secret=os.getenv("OAUTH_CLIENT_SECRET")
)

mcp_client = SimpleMCPClient(
    server_url=os.getenv("MCP_SERVER_URL", "https://mcp-server.example.com"),
    oauth_client=oauth_client
)

# Initialize LLM inference service
llm_service = LLMInferenceService(
    provider=LLMProvider.OPENAI,
    api_key=os.getenv("OPENAI_API_KEY")
)

# Initialize intelligent MCP client
intelligent_mcp_client = IntelligentMCPClient(mcp_client, llm_service)

# Initialize services for new flow
metadata_service = MetadataDiscoveryService()
oauth_orchestrator = OAuthFlowOrchestrator()


class AuthRequest(BaseModel):
    authorization_code: str


class ToolCallRequest(BaseModel):
    name: str
    arguments: Dict[str, Any]


class ResourceRequest(BaseModel):
    uri: str


class PromptRequest(BaseModel):
    name: str
    arguments: Optional[Dict[str, Any]] = None


class ClientRegistrationRequest(BaseModel):
    client_name: str
    redirect_uris: List[str]
    grant_types: Optional[List[str]] = None
    scope: str = "read write"


class DelegationRequest(BaseModel):
    subject_token: str
    target_user: str
    scope: str = "read"
    audience: Optional[str] = None


class NaturalLanguageQueryRequest(BaseModel):
    query: str
    delegated_user: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class ToolSuggestionRequest(BaseModel):
    query: str


class ServerDiscoveryRequest(BaseModel):
    mcp_server_url: str


class OAuthFlowRequest(BaseModel):
    mcp_server_url: str
    client_name: str = "MCP Client Application"
    redirect_uri: str = "http://localhost:8001/auth/callback"


class CompleteAuthRequest(BaseModel):
    authorization_code: str


@app.get("/")
async def root():
    return {"message": "MCP Client API Server"}


@app.post("/discover/server")
async def discover_server_metadata(request: ServerDiscoveryRequest):
    """Discover MCP server metadata and OAuth configuration"""
    try:
        config = await metadata_service.discover_full_configuration(request.mcp_server_url)
        
        # Create OAuthMetadata object for validation
        from metadata_discovery import OAuthMetadata
        oauth_data = config["oauth_metadata"]
        oauth_metadata = OAuthMetadata(
            authorization_endpoint=oauth_data["authorization_endpoint"],
            token_endpoint=oauth_data["token_endpoint"],
            registration_endpoint=oauth_data.get("registration_endpoint"),
            scopes_supported=oauth_data.get("scopes_supported"),
            response_types_supported=oauth_data.get("response_types_supported"),
            grant_types_supported=oauth_data.get("grant_types_supported"),
            token_endpoint_auth_methods_supported=oauth_data.get("token_endpoint_auth_methods_supported"),
            code_challenge_methods_supported=oauth_data.get("code_challenge_methods_supported")
        )
        validation = await metadata_service.validate_endpoints(oauth_metadata)
        
        return {
            "success": True,
            "configuration": config,
            "endpoint_validation": validation
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Discovery failed: {str(e)}")


@app.post("/oauth/start-flow")
async def start_oauth_flow(request: OAuthFlowRequest):
    """Start the complete OAuth 2.1 flow with DCR"""
    async def generate_flow():
        try:
            async for status in oauth_orchestrator.start_full_oauth_flow(
                mcp_server_url=request.mcp_server_url,
                client_name=request.client_name,
                redirect_uri=request.redirect_uri
            ):
                yield json.dumps(status.to_dict()) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "error": str(e)}) + "\n"
    
    return StreamingResponse(
        generate_flow(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.post("/oauth/complete")
async def complete_oauth_flow(request: CompleteAuthRequest):
    """Complete OAuth flow by exchanging authorization code for tokens"""
    try:
        result = await oauth_orchestrator.complete_authorization(request.authorization_code)
        
        if result.step.value == "error":
            raise HTTPException(status_code=400, detail=result.error)
        
        # Update the global OAuth client and MCP client
        global oauth_client, mcp_client, intelligent_mcp_client
        
        new_oauth_client = oauth_orchestrator.get_current_oauth_client()
        if new_oauth_client:
            oauth_client = new_oauth_client
            
            # Update MCP client with new OAuth client
            discovered_config = oauth_orchestrator.get_discovered_config()
            if discovered_config:
                mcp_server_url = discovered_config["mcp_metadata"]["server_url"]
                mcp_client = SimpleMCPClient(mcp_server_url, oauth_client)
                intelligent_mcp_client = IntelligentMCPClient(mcp_client, llm_service)
        
        return {
            "success": True,
            "message": result.message,
            "data": result.data,
            "client_registered": oauth_orchestrator.get_client_registration() is not None
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth completion failed: {str(e)}")


@app.get("/oauth/status")
async def get_oauth_status():
    """Get current OAuth flow status"""
    try:
        config = oauth_orchestrator.get_discovered_config()
        client_reg = oauth_orchestrator.get_client_registration()
        validation = None
        
        if config:
            validation = await oauth_orchestrator.validate_configuration()
        
        return {
            "has_configuration": config is not None,
            "has_client_registration": client_reg is not None,
            "is_authenticated": oauth_client.token is not None if hasattr(oauth_client, 'token') else False,
            "configuration": config,
            "client_info": {
                "client_id": client_reg.client_id if client_reg else None,
                "expires_at": client_reg.client_secret_expires_at if client_reg else None
            } if client_reg else None,
            "validation": validation
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/oauth/reset")
async def reset_oauth_flow():
    """Reset the OAuth flow to start over"""
    try:
        oauth_orchestrator.reset_flow()
        return {"message": "OAuth flow reset successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/auth/callback")
async def oauth_callback(request: Request):
    """OAuth callback endpoint that redirects back to the client with the authorization code"""
    # Get query parameters
    query_params = request.query_params
    code = query_params.get("code")
    error = query_params.get("error")
    state = query_params.get("state")
    
    # Construct redirect URL to the React client
    client_url = "http://localhost:4000"
    
    if code:
        # Success - redirect to client with code
        redirect_url = f"{client_url}?code={code}"
        if state:
            redirect_url += f"&state={state}"
        
        # Return an HTML page that automatically redirects and closes popup
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authorization Successful</title>
            <script>
                // If this is a popup, send the code to parent and close
                if (window.opener) {{
                    window.opener.postMessage({{
                        type: 'oauth_callback',
                        code: '{code}',
                        state: '{state or ""}'
                    }}, 'http://localhost:4000');
                    window.close();
                }} else {{
                    // If not a popup, redirect to main app
                    window.location.href = '{redirect_url}';
                }}
            </script>
        </head>
        <body>
            <h2>✅ Authorization Successful</h2>
            <p>Authorization code received. Redirecting...</p>
            <p>If you are not redirected automatically, <a href="{redirect_url}">click here</a>.</p>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    
    elif error:
        # Error - redirect to client with error
        redirect_url = f"{client_url}?error={error}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authorization Failed</title>
            <script>
                // If this is a popup, send the error to parent and close
                if (window.opener) {{
                    window.opener.postMessage({{
                        type: 'oauth_callback',
                        error: '{error}'
                    }}, 'http://localhost:4000');
                    window.close();
                }} else {{
                    // If not a popup, redirect to main app
                    window.location.href = '{redirect_url}';
                }}
            </script>
        </head>
        <body>
            <h2>❌ Authorization Failed</h2>
            <p>Error: {error}</p>
            <p><a href="{client_url}">Return to application</a></p>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    
    else:
        # No code or error - unexpected
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Invalid Callback</title>
        </head>
        <body>
            <h2>❌ Invalid OAuth Callback</h2>
            <p>No authorization code or error received.</p>
            <p><a href="http://localhost:4000">Return to application</a></p>
        </body>
        </html>
        """)


@app.get("/auth/url")
async def get_auth_url(scope: str = "read"):
    try:
        auth_url = oauth_client.get_authorization_url(scope)
        return {"auth_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/token")
async def exchange_token(auth_request: AuthRequest):
    try:
        token = await oauth_client.exchange_code_for_token(auth_request.authorization_code)
        return {"message": "Authentication successful", "token_type": token.get("token_type")}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")


@app.post("/auth/refresh")
async def refresh_token():
    try:
        token = await oauth_client.refresh_token()
        return {"message": "Token refreshed successfully", "token_type": token.get("token_type")}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token refresh failed: {str(e)}")


@app.post("/auth/register-client")
async def register_client(registration_request: ClientRegistrationRequest):
    try:
        registration = await oauth_client.register_client(
            client_name=registration_request.client_name,
            redirect_uris=registration_request.redirect_uris,
            grant_types=registration_request.grant_types,
            scope=registration_request.scope
        )
        return {
            "message": "Client registered successfully",
            "client_id": registration.client_id,
            "client_secret_expires_at": registration.client_secret_expires_at
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Client registration failed: {str(e)}")


@app.get("/auth/client-info")
async def get_client_info():
    try:
        client_info = oauth_client.get_client_info()
        if not client_info:
            raise HTTPException(status_code=404, detail="No client registration found")
        return client_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/delegate")
async def create_delegation_token(delegation_request: DelegationRequest):
    try:
        delegation_token = await oauth_client.exchange_token_for_delegation(
            subject_token=delegation_request.subject_token,
            target_user=delegation_request.target_user,
            scope=delegation_request.scope,
            audience=delegation_request.audience
        )
        return {
            "message": "Delegation token created successfully",
            "delegated_user": delegation_token.delegated_user,
            "scope": delegation_token.scope,
            "expires_in": delegation_token.expires_in
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Delegation failed: {str(e)}")


@app.get("/auth/delegation-consent/{target_user}")
async def get_delegation_consent_url(target_user: str, scope: str = "read"):
    try:
        consent_url = await oauth_client.get_user_consent_for_delegation(target_user, scope)
        return {"consent_url": consent_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/initialize")
async def initialize_mcp():
    try:
        response = await mcp_client.initialize()
        if response.error:
            raise HTTPException(status_code=400, detail=response.error)
        return response.result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/mcp/tools")
async def list_tools():
    try:
        response = await mcp_client.list_tools()
        if response.error:
            raise HTTPException(status_code=400, detail=response.error)
        return response.result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/tools/call")
async def call_tool(tool_request: ToolCallRequest, delegated_user: Optional[str] = Query(None)):
    try:
        response = await mcp_client.call_tool(tool_request.name, tool_request.arguments, delegated_user)
        if response.error:
            raise HTTPException(status_code=400, detail=response.error)
        return response.result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/tools/call/stream")
async def call_tool_stream(tool_request: ToolCallRequest, delegated_user: Optional[str] = Query(None)):
    async def generate_stream():
        try:
            async for chunk in mcp_client.call_tool_stream(tool_request.name, tool_request.arguments, delegated_user):
                yield json.dumps(chunk) + "\n"
        except ValueError as e:
            yield json.dumps({"type": "error", "error": str(e)}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "error": f"Tool streaming failed: {str(e)}"}) + "\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/mcp/resources")
async def list_resources():
    try:
        response = await mcp_client.list_resources()
        if response.error:
            raise HTTPException(status_code=400, detail=response.error)
        return response.result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/resources/read")
async def read_resource(resource_request: ResourceRequest):
    try:
        response = await mcp_client.read_resource(resource_request.uri)
        if response.error:
            raise HTTPException(status_code=400, detail=response.error)
        return response.result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/mcp/prompts")
async def list_prompts():
    try:
        response = await mcp_client.list_prompts()
        if response.error:
            raise HTTPException(status_code=400, detail=response.error)
        return response.result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/prompts/get")
async def get_prompt(prompt_request: PromptRequest):
    try:
        response = await mcp_client.get_prompt(prompt_request.name, prompt_request.arguments)
        if response.error:
            raise HTTPException(status_code=400, detail=response.error)
        return response.result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "authenticated": oauth_client.token is not None,
        "llm_available": llm_service.api_key is not None
    }


@app.post("/ai/query")
async def process_natural_language_query(query_request: NaturalLanguageQueryRequest):
    """Process a natural language query using LLM inference and MCP tools"""
    try:
        result = await intelligent_mcp_client.process_natural_language_query(
            user_query=query_request.query,
            delegated_user=query_request.delegated_user,
            context=query_request.context
        )
        
        return {
            "success": result.success,
            "query": result.query,
            "response": result.synthesized_response,
            "execution_time": result.total_execution_time,
            "tools_used": [step.tool_call.name for step in result.steps if step.status.value == "completed"],
            "execution_details": [
                {
                    "tool": step.tool_call.name,
                    "status": step.status.value,
                    "reasoning": step.tool_call.reasoning,
                    "error": step.error
                } for step in result.steps
            ]
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")


@app.post("/ai/query/stream")
async def process_natural_language_query_stream(query_request: NaturalLanguageQueryRequest):
    """Process a natural language query with real-time streaming updates"""
    async def generate_stream():
        try:
            async for update in intelligent_mcp_client.process_natural_language_query_stream(
                user_query=query_request.query,
                delegated_user=query_request.delegated_user,
                context=query_request.context
            ):
                yield json.dumps(update) + "\n"
        except ValueError as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": f"Query processing failed: {str(e)}"}) + "\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.post("/ai/suggestions")
async def get_tool_suggestions(suggestion_request: ToolSuggestionRequest):
    """Get tool suggestions for a natural language query"""
    try:
        suggestions = await intelligent_mcp_client.get_tool_suggestions(suggestion_request.query)
        return {
            "query": suggestion_request.query,
            "suggestions": suggestions
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get suggestions: {str(e)}")


@app.post("/ai/clear-context")
async def clear_conversation_context():
    """Clear the conversation context in the LLM service"""
    try:
        intelligent_mcp_client.clear_conversation_context()
        return {"message": "Conversation context cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear context: {str(e)}")


@app.get("/ai/status")
async def get_ai_status():
    """Get AI service status and capabilities"""
    return {
        "llm_provider": llm_service.provider.value,
        "model": getattr(llm_service, 'model', 'unknown'),
        "api_key_configured": llm_service.api_key is not None,
        "conversation_history_length": len(llm_service.conversation_history)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)