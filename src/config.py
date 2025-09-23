"""Configuration management for Azure AI Foundry Chatbot."""

import streamlit as st
from typing import Dict, Optional
from .constants import (
    PROJ_ENDPOINT_KEY, AGENT_ID_KEY, AZURE_AI_FOUNDRY_SECRETS_KEY,
    ENV_SECRETS_KEY, AZURE_CLIENT_ID_KEY, AZURE_CLIENT_SECRET_KEY,
    AZURE_TENANT_ID_KEY, AUTHORITY_BASE_URL, MCP_SECRETS_KEY,
    MCP_CLIENT_ID_KEY, MCP_CLIENT_SECRET_KEY, MCP_SERVER_LABEL_KEY
)


def get_config() -> Optional[Dict[str, str]]:
    """Get configuration from Streamlit secrets.
    
    Returns:
        Dict containing configuration or None if configuration is invalid.
    """
    try:
        foundry_config = st.secrets[AZURE_AI_FOUNDRY_SECRETS_KEY]
        config = {
            PROJ_ENDPOINT_KEY: foundry_config.get(PROJ_ENDPOINT_KEY),
            AGENT_ID_KEY: foundry_config.get(AGENT_ID_KEY)
        }
        
        missing = [k for k, v in config.items() if not v]
        if missing:
            st.error(f"❌ Missing required configuration in secrets: {', '.join(missing)}")
            st.info("💡 Please check your `.streamlit/secrets.toml` file and add the required Azure AI Foundry configuration.")
            return None
        
        return config
    except KeyError as e:
        st.error(f"❌ Azure AI Foundry configuration not found in secrets: {e}")
        st.info("💡 Please copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and add your configuration.")
        return None


def setup_environment_variables() -> None:
    """Set up environment variables for DefaultAzureCredential."""
    try:
        env_config = st.secrets[ENV_SECRETS_KEY]
        import os
        os.environ[AZURE_CLIENT_ID_KEY] = env_config.get(AZURE_CLIENT_ID_KEY, "")
        os.environ[AZURE_CLIENT_SECRET_KEY] = env_config.get(AZURE_CLIENT_SECRET_KEY, "")
        os.environ[AZURE_TENANT_ID_KEY] = env_config.get(AZURE_TENANT_ID_KEY, "")
    except KeyError:
        pass  # No environment variables found


def get_auth_config() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Get authentication configuration from environment variables.
    
    Returns:
        Tuple of (client_id, tenant_id, authority) or (None, None, None) if missing.
    """
    import os
    
    client_id = os.environ.get(AZURE_CLIENT_ID_KEY)
    tenant_id = os.environ.get(AZURE_TENANT_ID_KEY)
    
    if not client_id or not tenant_id:
        st.error(f"❌ Missing required environment variables: {AZURE_CLIENT_ID_KEY} and {AZURE_TENANT_ID_KEY}")
        st.info("💡 Please set these variables in your secrets.toml file or environment.")
        return None, None, None
    
    authority = f"{AUTHORITY_BASE_URL}/{tenant_id}"
    return client_id, tenant_id, authority


def get_mcp_config() -> Optional[Dict[str, str]]:
    """Get MCP configuration from Streamlit secrets.
    
    Returns:
        Dict containing MCP configuration or None if configuration is invalid.
    """
    try:
        mcp_config = st.secrets[MCP_SECRETS_KEY]
        
        # Get tenant_id from env section (shared with main auth)
        import os
        tenant_id = os.environ.get(AZURE_TENANT_ID_KEY)
        
        config = {
            MCP_CLIENT_ID_KEY: mcp_config.get(MCP_CLIENT_ID_KEY),
            MCP_CLIENT_SECRET_KEY: mcp_config.get(MCP_CLIENT_SECRET_KEY),
            MCP_SERVER_LABEL_KEY: mcp_config.get(MCP_SERVER_LABEL_KEY, "mcp_server"),
            AZURE_TENANT_ID_KEY: tenant_id
        }
        
        missing = [k for k, v in config.items() if not v]
        if missing:
            st.warning(f"⚠️ Missing MCP configuration in secrets: {', '.join(missing)}")
            st.info("💡 MCP functionality will be disabled. Add MCP configuration to enable it.")
            return None
        
        return config
    except KeyError:
        st.warning("⚠️ MCP configuration not found in secrets. MCP functionality will be disabled.")
        return None


def get_mcp_run_config(access_token: str, server_label: str = "mcp_server") -> Dict[str, any]:
    """Get MCP run configuration details.
    
    Args:
        access_token: Access token for MCP authentication
        server_label: MCP server label
        
    Returns:
        Dict containing MCP run configuration
    """
    return {
        "mcp": [
            {
                "server_label": server_label,
                "headers": {
                    "authorization": f"bearer {access_token}"
                },
                "require_approval": "never"
            }
        ]
    }
