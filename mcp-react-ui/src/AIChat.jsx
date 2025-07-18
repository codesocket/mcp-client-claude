import React, { useState, useEffect, useRef } from 'react';
import { aiAPI } from './api';

function AIChat({ isAuthenticated }) {
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [streamingData, setStreamingData] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [aiStatus, setAiStatus] = useState(null);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    checkAiStatus();
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingData]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const checkAiStatus = async () => {
    try {
      const status = await aiAPI.getStatus();
      setAiStatus(status);
    } catch (error) {
      console.error('Failed to check AI status:', error);
    }
  };

  const handleQuerySubmit = async (e) => {
    e.preventDefault();
    if (!query.trim() || isProcessing || !isAuthenticated) return;

    const userMessage = { type: 'user', content: query, timestamp: new Date() };
    setMessages(prev => [...prev, userMessage]);
    setIsProcessing(true);
    setStreamingData(null);
    setShowSuggestions(false);

    const currentQuery = query;
    setQuery('');

    try {
      // Use streaming for real-time updates
      await aiAPI.processQueryStream(currentQuery, null, null, (update) => {
        setStreamingData(update);
        
        if (update.type === 'final_response') {
          const assistantMessage = {
            type: 'assistant',
            content: update.response,
            timestamp: new Date(),
            metadata: {
              query: currentQuery,
              success: true
            }
          };
          setMessages(prev => [...prev, assistantMessage]);
          setStreamingData(null);
        }
      });
    } catch (error) {
      const errorMessage = {
        type: 'assistant',
        content: `I encountered an error processing your request: ${error.message}`,
        timestamp: new Date(),
        metadata: {
          query: currentQuery,
          success: false,
          error: error.message
        }
      };
      setMessages(prev => [...prev, errorMessage]);
      setStreamingData(null);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleGetSuggestions = async () => {
    if (!query.trim()) return;

    try {
      const response = await aiAPI.getToolSuggestions(query);
      setSuggestions(response.suggestions || []);
      setShowSuggestions(true);
    } catch (error) {
      console.error('Failed to get suggestions:', error);
    }
  };

  const handleClearContext = async () => {
    try {
      await aiAPI.clearContext();
      setMessages([]);
      setStreamingData(null);
    } catch (error) {
      console.error('Failed to clear context:', error);
    }
  };

  const formatTimestamp = (timestamp) => {
    return timestamp.toLocaleTimeString();
  };

  const renderStreamingUpdate = (data) => {
    switch (data.type) {
      case 'status':
        return <div className="streaming-status">🔄 {data.message}</div>;
      
      case 'plan':
        return (
          <div className="streaming-plan">
            <div className="plan-header">📋 Execution Plan:</div>
            {data.plan.tools.map((tool, index) => (
              <div key={index} className="plan-tool">
                <strong>{tool.name}</strong>: {tool.reasoning}
              </div>
            ))}
          </div>
        );
      
      case 'tool_start':
        return (
          <div className="streaming-tool-start">
            🔧 Executing {data.tool} (Step {data.step}/{data.total})
          </div>
        );
      
      case 'tool_result':
        return (
          <div className="streaming-tool-result">
            ✅ {data.tool} completed
          </div>
        );
      
      case 'tool_error':
        return (
          <div className="streaming-tool-error">
            ❌ {data.tool} failed: {data.error}
          </div>
        );
      
      default:
        return <div className="streaming-other">{JSON.stringify(data)}</div>;
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="card">
        <h2>🤖 AI Assistant</h2>
        <p>Please authenticate first to use the AI-powered natural language interface.</p>
      </div>
    );
  }

  if (!aiStatus?.api_key_configured) {
    return (
      <div className="card">
        <h2>🤖 AI Assistant</h2>
        <div className="status error">
          AI service not configured. Please set OPENAI_API_KEY environment variable.
        </div>
      </div>
    );
  }

  return (
    <div className="card ai-chat">
      <div className="ai-chat-header">
        <h2>🤖 AI Assistant</h2>
        <div className="ai-status">
          <span>Model: {aiStatus?.model}</span>
          <button className="button" onClick={handleClearContext}>
            Clear Context
          </button>
        </div>
      </div>

      <div className="chat-messages">
        {messages.map((message, index) => (
          <div key={index} className={`message ${message.type}`}>
            <div className="message-header">
              <strong>{message.type === 'user' ? 'You' : 'AI Assistant'}</strong>
              <span className="timestamp">{formatTimestamp(message.timestamp)}</span>
            </div>
            <div className="message-content">
              {message.content}
            </div>
            {message.metadata && (
              <div className="message-metadata">
                {!message.metadata.success && (
                  <span className="error-badge">Error</span>
                )}
              </div>
            )}
          </div>
        ))}

        {streamingData && (
          <div className="message assistant streaming">
            <div className="message-header">
              <strong>AI Assistant</strong>
              <span className="streaming-indicator">●</span>
            </div>
            <div className="message-content">
              {renderStreamingUpdate(streamingData)}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleQuerySubmit} className="chat-input-form">
        <div className="input-row">
          <input
            type="text"
            className="input chat-input"
            placeholder="Ask me anything about the available tools..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={isProcessing}
          />
          <button 
            type="submit" 
            className="button" 
            disabled={isProcessing || !query.trim()}
          >
            {isProcessing ? 'Processing...' : 'Send'}
          </button>
        </div>
        
        <div className="input-actions">
          <button 
            type="button" 
            className="button" 
            onClick={handleGetSuggestions}
            disabled={!query.trim()}
          >
            Get Tool Suggestions
          </button>
        </div>
      </form>

      {showSuggestions && suggestions.length > 0 && (
        <div className="suggestions-panel">
          <h4>🔧 Tool Suggestions</h4>
          {suggestions.map((suggestion, index) => (
            <div key={index} className="suggestion-item">
              <div className="suggestion-header">
                <strong>{suggestion.name}</strong>
                <span className={`confidence ${suggestion.confidence}`}>
                  {suggestion.confidence}
                </span>
              </div>
              <div className="suggestion-description">
                {suggestion.description}
              </div>
              <div className="suggestion-reasoning">
                <em>{suggestion.reasoning}</em>
              </div>
              {Object.keys(suggestion.suggested_arguments || {}).length > 0 && (
                <div className="suggestion-args">
                  <strong>Suggested arguments:</strong>
                  <pre>{JSON.stringify(suggestion.suggested_arguments, null, 2)}</pre>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="chat-examples">
        <h4>💡 Try asking:</h4>
        <div className="example-queries">
          <button 
            className="example-query" 
            onClick={() => setQuery("What tools are available?")}
          >
            "What tools are available?"
          </button>
          <button 
            className="example-query" 
            onClick={() => setQuery("Help me analyze the latest data")}
          >
            "Help me analyze the latest data"
          </button>
          <button 
            className="example-query" 
            onClick={() => setQuery("Show me the system status")}
          >
            "Show me the system status"
          </button>
        </div>
      </div>
    </div>
  );
}

export default AIChat;