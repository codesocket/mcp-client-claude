import React, { useState, useEffect } from 'react';
import { authAPI, mcpAPI, healthAPI, oauthFlowAPI } from './api';
import AIChat from './AIChat';
import OAuthSetup from './OAuthSetup';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authUrl, setAuthUrl] = useState('');
  const [authCode, setAuthCode] = useState('');
  const [status, setStatus] = useState({ type: '', message: '' });
  const [tools, setTools] = useState([]);
  const [resources, setResources] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [selectedTool, setSelectedTool] = useState('');
  const [toolArguments, setToolArguments] = useState('{}');
  const [toolOutput, setToolOutput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [serverConfig, setServerConfig] = useState(null);
  const [showSetup, setShowSetup] = useState(true);

  useEffect(() => {
    checkHealth();
    checkOAuthStatus();
  }, []);

  const checkHealth = async () => {
    try {
      const health = await healthAPI.check();
      // Don't auto-set authenticated from health check anymore
      // Authentication state is now managed by OAuth flow
    } catch (error) {
      setStatus({ type: 'error', message: 'Failed to connect to server' });
    }
  };

  const checkOAuthStatus = async () => {
    try {
      const oauthStatus = await oauthFlowAPI.getStatus();
      if (oauthStatus.is_authenticated && oauthStatus.has_configuration) {
        setIsAuthenticated(true);
        setServerConfig(oauthStatus.configuration);
        setShowSetup(false);
        setStatus({ type: 'success', message: 'Connected and authenticated' });
        await initializeMCP();
      }
    } catch (error) {
      // OAuth flow not started or failed
      setShowSetup(true);
    }
  };

  const getAuthorizationUrl = async () => {
    try {
      const response = await authAPI.getAuthUrl();
      setAuthUrl(response.auth_url);
      setStatus({ type: 'info', message: 'Please visit the authorization URL and copy the code' });
    } catch (error) {
      setStatus({ type: 'error', message: 'Failed to get authorization URL' });
    }
  };

  const exchangeAuthCode = async () => {
    try {
      await authAPI.exchangeToken(authCode);
      setIsAuthenticated(true);
      setStatus({ type: 'success', message: 'Authentication successful!' });
      await initializeMCP();
    } catch (error) {
      setStatus({ type: 'error', message: 'Authentication failed' });
    }
  };

  const initializeMCP = async () => {
    try {
      await mcpAPI.initialize();
      await loadTools();
      await loadResources();
      await loadPrompts();
      setStatus({ type: 'success', message: 'MCP initialized successfully' });
    } catch (error) {
      setStatus({ type: 'error', message: `MCP initialization failed: ${error.message}` });
    }
  };

  const loadTools = async () => {
    try {
      console.log('Loading tools...');
      const response = await mcpAPI.listTools();
      console.log('Tools response:', response);
      console.log('Tools array:', response.tools);
      setTools(response.tools || []);
      console.log('Tools state updated');
    } catch (error) {
      console.error('Failed to load tools:', error);
      setStatus({ type: 'error', message: `Failed to load tools: ${error.message}` });
    }
  };

  const loadResources = async () => {
    try {
      const response = await mcpAPI.listResources();
      setResources(response.resources || []);
    } catch (error) {
      setStatus({ type: 'error', message: `Failed to load resources: ${error.message}` });
    }
  };

  const loadPrompts = async () => {
    try {
      const response = await mcpAPI.listPrompts();
      setPrompts(response.prompts || []);
    } catch (error) {
      setStatus({ type: 'error', message: `Failed to load prompts: ${error.message}` });
    }
  };

  const callTool = async () => {
    if (!selectedTool) return;
    
    try {
      const args = JSON.parse(toolArguments);
      const response = await mcpAPI.callTool(selectedTool, args);
      setToolOutput(JSON.stringify(response, null, 2));
      setStatus({ type: 'success', message: 'Tool executed successfully' });
    } catch (error) {
      setStatus({ type: 'error', message: `Tool execution failed: ${error.message}` });
    }
  };

  const callToolStream = async () => {
    if (!selectedTool || isStreaming) return;
    
    setIsStreaming(true);
    setToolOutput('');
    
    try {
      const args = JSON.parse(toolArguments);
      await mcpAPI.callToolStream(selectedTool, args, (chunk) => {
        setToolOutput(prev => prev + JSON.stringify(chunk) + '\n');
      });
      setStatus({ type: 'success', message: 'Streaming completed' });
    } catch (error) {
      setStatus({ type: 'error', message: `Streaming failed: ${error.message}` });
    } finally {
      setIsStreaming(false);
    }
  };

  const handleAuthComplete = async (authData) => {
    setIsAuthenticated(true);
    setServerConfig(authData.config);
    setShowSetup(false);
    setStatus({ type: 'success', message: 'OAuth authentication completed successfully!' });
    
    // Initialize MCP operations
    await initializeMCP();
  };

  const handleResetSetup = async () => {
    try {
      await oauthFlowAPI.resetFlow();
      setIsAuthenticated(false);
      setServerConfig(null);
      setShowSetup(true);
      setStatus({ type: 'info', message: 'Setup reset - please configure your MCP server' });
    } catch (error) {
      setStatus({ type: 'error', message: 'Failed to reset setup' });
    }
  };

  return (
    <div className="container">
      <h1>MCP Client UI</h1>
      
      {status.message && (
        <div className={`status ${status.type}`}>
          {status.message}
        </div>
      )}

      {showSetup ? (
        <OAuthSetup onAuthComplete={handleAuthComplete} />
      ) : (
        <>
          <div className="card">
            <div className="connection-status">
              <h2>✅ Connected to MCP Server</h2>
              {serverConfig && (
                <div className="server-details">
                  <div><strong>Server:</strong> {serverConfig.mcp_metadata.name}</div>
                  <div><strong>URL:</strong> {serverConfig.mcp_metadata.server_url}</div>
                  <div><strong>Features:</strong> {serverConfig.mcp_metadata.supported_features.join(', ')}</div>
                </div>
              )}
              <button className="button button-secondary" onClick={handleResetSetup}>
                🔄 Change Server
              </button>
            </div>
          </div>

          <AIChat isAuthenticated={isAuthenticated} />
          
          <div className="card">
            <h2>MCP Operations</h2>
            <button className="button" onClick={initializeMCP}>
              Re-initialize MCP
            </button>
            <button className="button" onClick={loadTools}>
              Refresh Tools
            </button>
            <button className="button" onClick={loadResources}>
              Refresh Resources
            </button>
            <button className="button" onClick={loadPrompts}>
              Refresh Prompts
            </button>
          </div>

          <div className="card">
            <h2>Tools ({tools.length})</h2>
            <div className="tool-list">
              {tools.map((tool, index) => (
                <div key={index} className="tool-item">
                  <h4>{tool.name}</h4>
                  <p>{tool.description}</p>
                  <button 
                    className="button"
                    onClick={() => setSelectedTool(tool.name)}
                  >
                    Select
                  </button>
                </div>
              ))}
            </div>
          </div>

          {selectedTool && (
            <div className="card">
              <h2>Execute Tool: {selectedTool}</h2>
              <textarea
                className="textarea"
                placeholder="Tool arguments (JSON)"
                value={toolArguments}
                onChange={(e) => setToolArguments(e.target.value)}
              />
              <button className="button" onClick={callTool}>
                Execute
              </button>
              <button 
                className="button" 
                onClick={callToolStream}
                disabled={isStreaming}
              >
                {isStreaming ? 'Streaming...' : 'Execute (Stream)'}
              </button>
              
              {toolOutput && (
                <div className="output">
                  {toolOutput}
                </div>
              )}
            </div>
          )}

          <div className="card">
            <h2>Resources ({resources.length})</h2>
            <div className="tool-list">
              {resources.map((resource, index) => (
                <div key={index} className="tool-item">
                  <h4>{resource.name}</h4>
                  <p>{resource.uri}</p>
                  <p>{resource.description}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <h2>Prompts ({prompts.length})</h2>
            <div className="tool-list">
              {prompts.map((prompt, index) => (
                <div key={index} className="tool-item">
                  <h4>{prompt.name}</h4>
                  <p>{prompt.description}</p>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default App;