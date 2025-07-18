import React, { useState, useEffect } from 'react';
import { discoveryAPI, oauthFlowAPI } from './api';

const FlowStep = {
  SERVER_INPUT: 'server_input',
  DISCOVER_METADATA: 'discover_metadata',
  REGISTER_CLIENT: 'register_client',
  GET_AUTHORIZATION_URL: 'get_authorization_url',
  WAIT_FOR_CODE: 'wait_for_code',
  EXCHANGE_CODE: 'exchange_code',
  COMPLETE: 'complete',
  ERROR: 'error'
};

function OAuthSetup({ onAuthComplete }) {
  const [currentStep, setCurrentStep] = useState(FlowStep.SERVER_INPUT);
  const [mcpServerUrl, setMcpServerUrl] = useState('https://your-mcp-server.example.com');
  const [clientName, setClientName] = useState('MCP Client Application');
  const [discoveredConfig, setDiscoveredConfig] = useState(null);
  const [flowStatus, setFlowStatus] = useState(null);
  const [authorizationUrl, setAuthorizationUrl] = useState('');
  const [authCode, setAuthCode] = useState('');
  const [error, setError] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [isMonitoringAuth, setIsMonitoringAuth] = useState(false);

  // Monitor for authorization code in URL on component mount
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get('code');
    const error = urlParams.get('error');
    
    if (code && currentStep === FlowStep.WAIT_FOR_CODE) {
      console.log('Auto-detected authorization code:', code);
      setAuthCode(code);
      // Clear URL parameters to avoid confusion
      const cleanUrl = window.location.pathname;
      window.history.replaceState({}, document.title, cleanUrl);
    } else if (error) {
      console.error('OAuth error in URL:', error);
      setError(`OAuth error: ${error}`);
      setCurrentStep(FlowStep.ERROR);
    }
  }, [currentStep]);

  // Listen for postMessage from OAuth popup
  useEffect(() => {
    const handleMessage = (event) => {
      // Verify origin for security
      if (event.origin !== 'http://localhost:8001') {
        return;
      }

      const { type, code, error, state } = event.data;
      
      if (type === 'oauth_callback') {
        if (code) {
          console.log('Received authorization code from popup:', code);
          setAuthCode(code);
          setIsMonitoringAuth(false);
          // Clear URL parameters to avoid confusion
          const cleanUrl = window.location.pathname;
          window.history.replaceState({}, document.title, cleanUrl);
        } else if (error) {
          console.error('OAuth error from popup:', error);
          setError(`OAuth error: ${error}`);
          setCurrentStep(FlowStep.ERROR);
          setIsMonitoringAuth(false);
        }
      }
    };

    window.addEventListener('message', handleMessage);
    
    return () => {
      window.removeEventListener('message', handleMessage);
    };
  }, []);

  // Monitor popup window for authorization code
  useEffect(() => {
    let checkInterval = null;

    if (isMonitoringAuth && currentStep === FlowStep.WAIT_FOR_CODE) {
      checkInterval = setInterval(() => {
        const popupWindow = window.mcpPopupWindow;
        
        if (popupWindow && popupWindow.closed) {
          // Popup was closed, stop monitoring
          setIsMonitoringAuth(false);
          clearInterval(checkInterval);
          console.log('Popup closed, stopped monitoring');
        } else if (popupWindow) {
          try {
            // Try to access popup URL to detect redirect
            const popupUrl = popupWindow.location.href;
            if (popupUrl && popupUrl.includes('code=')) {
              const urlParams = new URLSearchParams(new URL(popupUrl).search);
              const code = urlParams.get('code');
              if (code) {
                console.log('Auto-detected code from popup:', code);
                setAuthCode(code);
                popupWindow.close();
                setIsMonitoringAuth(false);
                clearInterval(checkInterval);
              }
            }
          } catch (e) {
            // Cross-origin error is expected, continue monitoring
            // This is normal when the popup is on a different domain
          }
        }
      }, 1000);
    }

    return () => {
      if (checkInterval) {
        clearInterval(checkInterval);
      }
    };
  }, [isMonitoringAuth, currentStep]);

  const resetFlow = async () => {
    try {
      await oauthFlowAPI.resetFlow();
      setCurrentStep(FlowStep.SERVER_INPUT);
      setMcpServerUrl('');
      setDiscoveredConfig(null);
      setFlowStatus(null);
      setAuthorizationUrl('');
      setAuthCode('');
      setError('');
      setProgress(0);
    } catch (error) {
      console.error('Failed to reset flow:', error);
    }
  };

  const handleServerDiscovery = async () => {
    if (!mcpServerUrl.trim()) return;

    setIsProcessing(true);
    setError('');

    try {
      const result = await discoveryAPI.discoverServer(mcpServerUrl);
      setDiscoveredConfig(result.configuration);
      setCurrentStep(FlowStep.DISCOVER_METADATA);
      setProgress(25);
    } catch (error) {
      setError(`Server discovery failed: ${error.message}`);
      setCurrentStep(FlowStep.ERROR);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleStartOAuthFlow = async () => {
    setIsProcessing(true);
    setError('');
    setCurrentStep(FlowStep.REGISTER_CLIENT);

    try {
      await oauthFlowAPI.startFlow(mcpServerUrl, clientName, "http://localhost:8001/auth/callback", (update) => {
        setFlowStatus(update);
        setProgress(update.progress || 0);

        if (update.step === 'get_authorization_url' && update.data?.authorization_url) {
          console.log('Received authorization URL:', update.data.authorization_url);
          setAuthorizationUrl(update.data.authorization_url);
          setCurrentStep(FlowStep.WAIT_FOR_CODE);
        } else if (update.step === 'error') {
          setError(update.error || update.message);
          setCurrentStep(FlowStep.ERROR);
        } else {
          setCurrentStep(update.step);
        }
      });
    } catch (error) {
      setError(`OAuth flow failed: ${error.message}`);
      setCurrentStep(FlowStep.ERROR);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCompleteAuth = async () => {
    if (!authCode.trim()) return;

    setIsProcessing(true);
    setError('');

    try {
      const result = await oauthFlowAPI.completeFlow(authCode);
      setCurrentStep(FlowStep.COMPLETE);
      setProgress(100);
      
      // Notify parent component
      if (onAuthComplete) {
        onAuthComplete({
          serverUrl: mcpServerUrl,
          config: discoveredConfig,
          authResult: result
        });
      }
    } catch (error) {
      setError(`Authentication completion failed: ${error.message}`);
      setCurrentStep(FlowStep.ERROR);
    } finally {
      setIsProcessing(false);
    }
  };

  const openAuthorizationUrl = () => {
    if (authorizationUrl) {
      console.log('Opening authorization URL:', authorizationUrl);
      const popupWindow = window.open(authorizationUrl, '_blank', 'width=600,height=700,scrollbars=yes,resizable=yes');
      window.mcpPopupWindow = popupWindow;
      
      if (popupWindow) {
        setIsMonitoringAuth(true);
        console.log('Started monitoring popup for authorization code...');
      } else {
        alert('Pop-up blocked! Please copy the URL manually and open it in a new tab.');
      }
    } else {
      console.error('No authorization URL available');
      alert('No authorization URL available. Please try restarting the flow.');
    }
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case FlowStep.SERVER_INPUT:
        return (
          <div className="setup-step">
            <h3>🌐 MCP Server Configuration</h3>
            <p>Enter the URL of your remote MCP server to begin the setup process.</p>
            
            <div className="input-group">
              <input
                type="text"
                className="input"
                placeholder="https://mcp-server.example.com"
                value={mcpServerUrl}
                onChange={(e) => setMcpServerUrl(e.target.value)}
                disabled={isProcessing}
              />
              <button 
                className="button" 
                onClick={handleServerDiscovery}
                disabled={!mcpServerUrl.trim() || isProcessing}
              >
                {isProcessing ? 'Discovering...' : 'Discover Server'}
              </button>
            </div>

            <div className="input-group">
              <label>Client Name (optional):</label>
              <input
                type="text"
                className="input"
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
                disabled={isProcessing}
              />
            </div>

            <div className="examples">
              <h4>💡 Example URLs:</h4>
              <div className="example-urls">
                <button 
                  className="example-url" 
                  onClick={() => setMcpServerUrl('https://api.anthropic.com')}
                >
                  https://api.anthropic.com (Demo)
                </button>
                <button 
                  className="example-url" 
                  onClick={() => setMcpServerUrl('https://accounts.google.com')}
                >
                  https://accounts.google.com (Real OAuth - for testing)
                </button>
                <button 
                  className="example-url" 
                  onClick={() => setMcpServerUrl('https://github.com')}
                >
                  https://github.com (Real OAuth - for testing)
                </button>
                <button 
                  className="example-url" 
                  onClick={() => setMcpServerUrl('https://httpbin.org')}
                >
                  https://httpbin.org (Test endpoints)
                </button>
              </div>
              
              <div className="note">
                <p><strong>Note:</strong> Demo URLs will generate authorization URLs but won't work for actual authentication. 
                Real OAuth providers like Google/GitHub will have working authorization endpoints but won't accept our demo client.</p>
              </div>
            </div>
          </div>
        );

      case FlowStep.DISCOVER_METADATA:
        return (
          <div className="setup-step">
            <h3>✅ Server Discovered Successfully</h3>
            {discoveredConfig && (
              <div className="config-summary">
                <div className="server-info">
                  <h4>📊 Server Information:</h4>
                  <div className="info-grid">
                    <div><strong>Name:</strong> {discoveredConfig.mcp_metadata.name}</div>
                    <div><strong>Version:</strong> {discoveredConfig.mcp_metadata.version}</div>
                    <div><strong>Features:</strong> {discoveredConfig.mcp_metadata.supported_features.join(', ')}</div>
                  </div>
                </div>

                <div className="oauth-info">
                  <h4>🔐 OAuth Configuration:</h4>
                  <div className="endpoint-list">
                    <div>✅ Authorization: {discoveredConfig.oauth_metadata.authorization_endpoint}</div>
                    <div>✅ Token: {discoveredConfig.oauth_metadata.token_endpoint}</div>
                    {discoveredConfig.oauth_metadata.registration_endpoint && (
                      <div>✅ Registration: {discoveredConfig.oauth_metadata.registration_endpoint}</div>
                    )}
                  </div>
                </div>
              </div>
            )}

            <button 
              className="button button-primary" 
              onClick={handleStartOAuthFlow}
              disabled={isProcessing}
            >
              {isProcessing ? 'Starting OAuth Flow...' : 'Start OAuth 2.1 Flow'}
            </button>
          </div>
        );

      case FlowStep.REGISTER_CLIENT:
        return (
          <div className="setup-step">
            <h3>🔧 Registering OAuth Client</h3>
            <div className="flow-status">
              {flowStatus && (
                <div className="status-message">
                  <div className="progress-bar">
                    <div className="progress-fill" style={{width: `${progress}%`}}></div>
                  </div>
                  <p>{flowStatus.message}</p>
                  {flowStatus.data && (
                    <pre className="status-data">{JSON.stringify(flowStatus.data, null, 2)}</pre>
                  )}
                </div>
              )}
            </div>
          </div>
        );

      case FlowStep.GET_AUTHORIZATION_URL:
        return (
          <div className="setup-step">
            <h3>🔗 Generating Authorization URL</h3>
            <div className="flow-status">
              {flowStatus && (
                <div className="status-message">
                  <div className="progress-bar">
                    <div className="progress-fill" style={{width: `${progress}%`}}></div>
                  </div>
                  <p>{flowStatus.message}</p>
                </div>
              )}
            </div>
          </div>
        );

      case FlowStep.WAIT_FOR_CODE:
        return (
          <div className="setup-step">
            <h3>🎫 User Consent Required</h3>
            <p>Click the button below to open the OAuth consent screen in a new tab.</p>
            
            <div className="auth-url-section">
              <div className="action-buttons">
                <button 
                  className="button button-primary" 
                  onClick={openAuthorizationUrl}
                >
                  🚀 Open Authorization Page
                </button>
                <a 
                  href={authorizationUrl} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="button button-secondary"
                >
                  🔗 Open in New Tab
                </a>
              </div>
              
              <div className="auth-url-display">
                <label>Authorization URL:</label>
                <div className="url-box">
                  <code>{authorizationUrl}</code>
                  <button 
                    className="copy-button"
                    onClick={() => {
                      navigator.clipboard.writeText(authorizationUrl);
                      alert('URL copied to clipboard!');
                    }}
                  >
                    📋 Copy
                  </button>
                </div>
              </div>
              
              <div className="instructions">
                <h5>📋 Instructions:</h5>
                <ol>
                  <li>Click "Open Authorization Page" or "Open in New Tab"</li>
                  <li>If pop-ups are blocked, manually copy and paste the URL</li>
                  <li>Complete the authorization on the OAuth provider</li>
                  <li>Copy the authorization code from the URL or page</li>
                  <li>Paste the code in the field below</li>
                </ol>
              </div>
            </div>

            <div className="auth-code-section">
              <h4>📝 Enter Authorization Code:</h4>
              {isMonitoringAuth ? (
                <div className="monitoring-status">
                  <p>🔍 <strong>Auto-monitoring active:</strong> The authorization code will be automatically detected when you complete the OAuth flow in the popup window.</p>
                  <p>If auto-detection fails, you can manually paste the code below.</p>
                </div>
              ) : (
                <p>After granting consent, copy the authorization code and paste it below:</p>
              )}
              
              <div className="input-group">
                <input
                  type="text"
                  className="input"
                  placeholder={isMonitoringAuth ? "Code will be auto-populated..." : "Paste authorization code here..."}
                  value={authCode}
                  onChange={(e) => setAuthCode(e.target.value)}
                  disabled={isProcessing}
                />
                <button 
                  className="button" 
                  onClick={handleCompleteAuth}
                  disabled={!authCode.trim() || isProcessing}
                >
                  {isProcessing ? 'Completing...' : 'Complete Authentication'}
                </button>
              </div>
            </div>
          </div>
        );

      case FlowStep.COMPLETE:
        return (
          <div className="setup-step">
            <h3>🎉 Authentication Complete!</h3>
            <div className="success-message">
              <p>✅ OAuth 2.1 flow completed successfully</p>
              <p>✅ Access token obtained</p>
              <p>✅ Ready to use MCP operations</p>
              
              <div className="progress-bar">
                <div className="progress-fill" style={{width: '100%'}}></div>
              </div>
            </div>
          </div>
        );

      case FlowStep.ERROR:
        return (
          <div className="setup-step">
            <h3>❌ Setup Failed</h3>
            <div className="error-message">
              <p>{error}</p>
              <button className="button" onClick={resetFlow}>
                🔄 Start Over
              </button>
            </div>
          </div>
        );

      default:
        return (
          <div className="setup-step">
            <h3>🔄 Processing...</h3>
            <p>Please wait while we set up your MCP connection.</p>
          </div>
        );
    }
  };

  return (
    <div className="oauth-setup">
      <div className="setup-header">
        <h2>🚀 MCP Client Setup</h2>
        <p>Follow these steps to connect to your MCP server with OAuth 2.1 authentication</p>
      </div>

      <div className="setup-progress">
        <div className="step-indicators">
          <div className={`step-indicator ${currentStep === FlowStep.SERVER_INPUT ? 'active' : currentStep !== FlowStep.SERVER_INPUT && progress > 0 ? 'completed' : ''}`}>
            1. Server Discovery
          </div>
          <div className={`step-indicator ${currentStep === FlowStep.REGISTER_CLIENT || currentStep === FlowStep.GET_AUTHORIZATION_URL ? 'active' : progress > 50 ? 'completed' : ''}`}>
            2. Client Registration
          </div>
          <div className={`step-indicator ${currentStep === FlowStep.WAIT_FOR_CODE ? 'active' : progress > 85 ? 'completed' : ''}`}>
            3. User Consent
          </div>
          <div className={`step-indicator ${currentStep === FlowStep.COMPLETE ? 'active completed' : ''}`}>
            4. Complete
          </div>
        </div>
      </div>

      <div className="setup-content">
        {renderStepContent()}
      </div>

      {currentStep !== FlowStep.SERVER_INPUT && currentStep !== FlowStep.COMPLETE && currentStep !== FlowStep.ERROR && (
        <div className="setup-actions">
          <button className="button button-secondary" onClick={resetFlow}>
            🔄 Reset & Start Over
          </button>
        </div>
      )}
    </div>
  );
}

export default OAuthSetup;