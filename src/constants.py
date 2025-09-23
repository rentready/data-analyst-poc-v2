"""Constants for Azure AI Foundry Chatbot."""

# Azure AI Foundry configuration keys
PROJ_ENDPOINT_KEY = "proj_endpoint"
AGENT_ID_KEY = "agent_id"

# Environment variable keys
AZURE_CLIENT_ID_KEY = "AZURE_CLIENT_ID"
AZURE_CLIENT_SECRET_KEY = "AZURE_CLIENT_SECRET"
AZURE_TENANT_ID_KEY = "AZURE_TENANT_ID"

# Streamlit secrets keys
AZURE_AI_FOUNDRY_SECRETS_KEY = "azure_ai_foundry"
ENV_SECRETS_KEY = "env"

# Authentication
AUTHORITY_BASE_URL = "https://login.microsoftonline.com"

# Polling configuration
MAX_POLL_ATTEMPTS = 60
POLL_INTERVAL_SECONDS = 1

# Message roles
USER_ROLE = "user"
ASSISTANT_ROLE = "assistant"

# Annotation types
FILE_CITATION_TYPE = "file_citation"
URL_CITATION_TYPE = "url_citation"

# Run statuses
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_CANCELLED = "cancelled"
RUN_STATUS_EXPIRED = "expired"

# UI settings
DEFAULT_TYPING_DELAY = 0.02  # Delay between characters in seconds

# MCP Configuration
MCP_SERVER_LABEL_KEY = "mcp_server_label"
MCP_CLIENT_ID_KEY = "mcp_client_id"
MCP_CLIENT_SECRET_KEY = "mcp_client_secret"
MCP_SECRETS_KEY = "mcp"
