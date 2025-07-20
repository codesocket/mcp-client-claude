import axios from 'axios';

const API_BASE_URL = 'http://localhost:8001';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const authAPI = {
  getAuthUrl: async (scope = 'read') => {
    const response = await api.get(`/auth/url?scope=${scope}`);
    return response.data;
  },

  exchangeToken: async (authorizationCode) => {
    const response = await api.post('/auth/token', {
      authorization_code: authorizationCode
    });
    return response.data;
  },

  refreshToken: async () => {
    const response = await api.post('/auth/refresh');
    return response.data;
  }
};

export const mcpAPI = {
  initialize: async () => {
    const response = await api.post('/mcp/initialize');
    return response.data;
  },

  listTools: async () => {
    const response = await api.get('/mcp/tools');
    return response.data;
  },

  callTool: async (name, args) => {
    const response = await api.post('/mcp/tools/call', {
      name,
      arguments: args
    });
    return response.data;
  },

  callToolStream: async (name, args, onChunk) => {
    const response = await fetch(`${API_BASE_URL}/mcp/tools/call/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name,
        arguments: args
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        
        if (done) break;
        
        const chunk = decoder.decode(value);
        buffer += chunk;
        
        // Process complete lines (NDJSON format)
        const lines = buffer.split('\n');
        // Keep the last potentially incomplete line in buffer
        buffer = lines.pop() || '';
        
        for (const line of lines) {
          if (line.trim()) {
            try {
              const parsed = JSON.parse(line);
              onChunk(parsed);
            } catch (e) {
              console.error('Failed to parse streaming JSON:', line, e);
              onChunk({ type: 'text', content: line });
            }
          }
        }
      }
      
      // Process any remaining buffer content
      if (buffer.trim()) {
        try {
          const parsed = JSON.parse(buffer);
          onChunk(parsed);
        } catch (e) {
          console.error('Failed to parse final streaming JSON:', buffer, e);
          onChunk({ type: 'text', content: buffer });
        }
      }
    } finally {
      reader.releaseLock();
    }
  },

  listResources: async () => {
    const response = await api.get('/mcp/resources');
    return response.data;
  },

  readResource: async (uri) => {
    const response = await api.post('/mcp/resources/read', { uri });
    return response.data;
  },

  listPrompts: async () => {
    const response = await api.get('/mcp/prompts');
    return response.data;
  },

  getPrompt: async (name, args) => {
    const response = await api.post('/mcp/prompts/get', {
      name,
      arguments: args
    });
    return response.data;
  }
};

export const healthAPI = {
  check: async () => {
    const response = await api.get('/health');
    return response.data;
  }
};

export const aiAPI = {
  processQuery: async (query, delegatedUser = null, context = null) => {
    const response = await api.post('/ai/query', {
      query,
      delegated_user: delegatedUser,
      context
    });
    return response.data;
  },

  processQueryStream: async (query, delegatedUser = null, context = null, onUpdate) => {
    const response = await fetch(`${API_BASE_URL}/ai/query/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query,
        delegated_user: delegatedUser,
        context
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        
        if (done) break;
        
        const chunk = decoder.decode(value);
        buffer += chunk;
        
        // Process complete lines (NDJSON format)
        const lines = buffer.split('\n');
        // Keep the last potentially incomplete line in buffer
        buffer = lines.pop() || '';
        
        for (const line of lines) {
          if (line.trim()) {
            try {
              const parsed = JSON.parse(line);
              onUpdate(parsed);
            } catch (e) {
              console.error('Failed to parse streaming JSON:', line, e);
              onUpdate({ type: 'error', message: 'Failed to parse response' });
            }
          }
        }
      }
      
      // Process any remaining buffer content
      if (buffer.trim()) {
        try {
          const parsed = JSON.parse(buffer);
          onUpdate(parsed);
        } catch (e) {
          console.error('Failed to parse final streaming JSON:', buffer, e);
          onUpdate({ type: 'error', message: 'Failed to parse final response' });
        }
      }
    } finally {
      reader.releaseLock();
    }
  },

  getToolSuggestions: async (query) => {
    const response = await api.post('/ai/suggestions', { query });
    return response.data;
  },

  clearContext: async () => {
    const response = await api.post('/ai/clear-context');
    return response.data;
  },

  getStatus: async () => {
    const response = await api.get('/ai/status');
    return response.data;
  }
};

export const discoveryAPI = {
  discoverServer: async (mcpServerUrl) => {
    const response = await api.post('/discover/server', {
      mcp_server_url: mcpServerUrl
    });
    return response.data;
  }
};

export const oauthFlowAPI = {
  startFlow: async (mcpServerUrl, clientName = "MCP Client Application", redirectUri = "http://localhost:8001/auth/callback", onUpdate) => {
    const response = await fetch(`${API_BASE_URL}/oauth/start-flow`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        mcp_server_url: mcpServerUrl,
        client_name: clientName,
        redirect_uri: redirectUri
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        
        if (done) break;
        
        const chunk = decoder.decode(value);
        buffer += chunk;
        
        // Process complete lines (NDJSON format)
        const lines = buffer.split('\n');
        // Keep the last potentially incomplete line in buffer
        buffer = lines.pop() || '';
        
        for (const line of lines) {
          if (line.trim()) {
            try {
              const parsed = JSON.parse(line);
              onUpdate(parsed);
            } catch (e) {
              console.error('Failed to parse OAuth flow JSON:', line, e);
              onUpdate({ type: 'error', error: 'Failed to parse response' });
            }
          }
        }
      }
      
      // Process any remaining buffer content
      if (buffer.trim()) {
        try {
          const parsed = JSON.parse(buffer);
          onUpdate(parsed);
        } catch (e) {
          console.error('Failed to parse final OAuth flow JSON:', buffer, e);
          onUpdate({ type: 'error', error: 'Failed to parse final response' });
        }
      }
    } finally {
      reader.releaseLock();
    }
  },

  completeFlow: async (authorizationCode) => {
    const response = await api.post('/oauth/complete', {
      authorization_code: authorizationCode
    });
    return response.data;
  },

  getStatus: async () => {
    const response = await api.get('/oauth/status');
    return response.data;
  },

  resetFlow: async () => {
    const response = await api.post('/oauth/reset');
    return response.data;
  }
};