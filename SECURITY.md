# Security Guidelines

## 🔒 Protected Files & Information

This repository is configured to protect sensitive information from being committed to Git:

### ✅ **Files Protected by .gitignore:**

- **Environment Variables**: `.env`, `.env.local`, `.env.development`, etc.
- **API Keys**: OpenAI API keys, OAuth client secrets
- **OAuth Credentials**: Client IDs, client secrets, tokens
- **Build Artifacts**: `node_modules/`, `dist/`, `__pycache__/`, etc.
- **IDE Files**: `.vscode/`, `.idea/`, temporary files
- **System Files**: `.DS_Store`, `Thumbs.db`, swap files
- **Logs**: `*.log`, `logs/`
- **Certificates**: `*.pem`, `*.key`, `*.crt`

### 📝 **Safe to Commit:**

- **Example Files**: `.env.example` with placeholder values
- **Documentation**: README files, code comments
- **Configuration Templates**: Configuration files with default/example values
- **Source Code**: Application logic without embedded secrets

## 🛡️ **Security Best Practices**

### 1. Environment Variables
```bash
# ✅ Good - Use environment variables
OPENAI_API_KEY=your_api_key_here

# ❌ Bad - Never hardcode in source
api_key = "sk-actual-api-key-here"
```

### 2. OAuth Configuration
- Use the provided `.env.example` as a template
- Never commit actual client secrets or API keys
- OAuth endpoints are auto-discovered when possible

### 3. Development Setup
```bash
# Create your local .env from the example
cp mcp-fastapi-server/.env.example mcp-fastapi-server/.env

# Edit with your actual values
nano mcp-fastapi-server/.env
```

### 4. Production Deployment
- Use environment variables or secure secret management
- Never deploy with `.env` files containing real secrets
- Use proper authentication and HTTPS in production

## 🔍 **Verification Commands**

Check that sensitive files are properly ignored:

```bash
# Check git status (should not show .env files)
git status

# Check ignored files (should show .env in ignored section)
git status --ignored

# Verify no secrets in staged changes
git diff --cached
```

## 🚨 **If You Accidentally Commit Secrets**

1. **Immediately revoke/rotate** the exposed credentials
2. Remove from Git history:
   ```bash
   git filter-branch --force --index-filter \
   'git rm --cached --ignore-unmatch path/to/secret/file' \
   --prune-empty --tag-name-filter cat -- --all
   ```
3. Force push to update remote repository
4. Inform team members to re-clone

## 📞 **Report Security Issues**

If you discover a security vulnerability, please:
1. Do not open a public issue
2. Contact the maintainers directly
3. Provide detailed information about the vulnerability
4. Allow time for the issue to be addressed before public disclosure