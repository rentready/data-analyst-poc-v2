"""MCP Token Client for Azure AI Foundry Agent integration."""

import asyncio
import logging
import aiohttp
from typing import Optional, Dict, Any
import streamlit as st

from .constants import (
    MCP_CLIENT_ID_KEY, MCP_CLIENT_SECRET_KEY,
    AZURE_TENANT_ID_KEY, AUTHORITY_BASE_URL
)

logger = logging.getLogger(__name__)


class MCPTokenClient:
    """Client for obtaining MCP access tokens for Azure AI Foundry Agent."""
    
    def __init__(self, config: Dict[str, str]):
        """Initialize MCP token client.
        
        Args:
            config: MCP configuration dictionary
        """
        self.config = config
        self.client_id = config[MCP_CLIENT_ID_KEY]
        self.client_secret = config[MCP_CLIENT_SECRET_KEY]
        self.tenant_id = config[AZURE_TENANT_ID_KEY]
        
        # Always construct OAuth endpoint from tenant_id
        self.token_endpoint = f"{AUTHORITY_BASE_URL}/{self.tenant_id}/oauth2/token"
    
    async def get_access_token(self) -> Optional[str]:
        """Get access token using client credentials flow for MCP.
        
        Returns:
            Access token string or None if failed
        """
        try:
            # Prepare form data for client credentials flow
            data = {
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'scope': 'https://graph.microsoft.com/.default'  # Default scope for MCP
            }
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.token_endpoint,
                    data=data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        access_token = token_data.get('access_token')
                        
                        if access_token:
                            logger.info("Successfully obtained MCP access token")
                            return access_token
                        else:
                            logger.error("No access token in response")
                            return None
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get access token. Status: {response.status}, Error: {error_text}")
                        return None
                        
        except asyncio.TimeoutError:
            logger.error("Timeout while getting MCP access token")
            return None
        except Exception as e:
            logger.error(f"Error getting MCP access token: {e}")
            return None
    
    def get_token_sync(self) -> Optional[str]:
        """Synchronous wrapper for getting access token.
        
        Returns:
            Access token string or None if failed
        """
        try:
            return asyncio.run(self.get_access_token())
        except Exception as e:
            logger.error(f"Error in synchronous token retrieval: {e}")
            return None


async def get_mcp_token_async(config: Dict[str, str]) -> Optional[str]:
    """Get MCP token asynchronously.
    
    Args:
        config: MCP configuration dictionary
        
    Returns:
        Access token string or None if failed
    """
    if not config:
        return None
    
    client = MCPTokenClient(config)
    return await client.get_access_token()


def get_mcp_token_sync(config: Dict[str, str]) -> Optional[str]:
    """Get MCP token synchronously.
    
    Args:
        config: MCP configuration dictionary
        
    Returns:
        Access token string or None if failed
    """
    if not config:
        return None
    
    client = MCPTokenClient(config)
    return client.get_token_sync()


def display_mcp_status(config: Optional[Dict[str, str]], token: Optional[str]) -> None:
    """Display MCP status in Streamlit UI.
    
    Args:
        config: MCP configuration dictionary
        token: Current MCP token (if any)
    """
    if config is None:
        st.warning("⚠️ MCP not configured")
        st.info("💡 Add MCP configuration to secrets.toml to enable functionality")
        return
    
    if token:
        st.success("✅ MCP token obtained and will be passed to run")
        with st.expander("MCP Configuration"):
            # Generate endpoint from tenant_id
            tenant_id = config.get(AZURE_TENANT_ID_KEY, "unknown")
            endpoint = f"{AUTHORITY_BASE_URL}/{tenant_id}/oauth2/token"
            
            # Get server label from config
            server_label = config.get("mcp_server_label", "mcp_server")
            
            st.json({
                "server_label": server_label,
                "token_acquired": True,
                "token_length": len(token),
                "endpoint": endpoint,
                "tenant_id": tenant_id,
                "status": "Ready for run"
            })
        
        # Display run configuration
        from .ui import render_mcp_run_config
        render_mcp_run_config(token)
    else:
        st.error("❌ Failed to obtain MCP token")
        st.info("💡 Check MCP settings in secrets.toml")
