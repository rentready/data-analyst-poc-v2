"""Authentication management for Azure AI Foundry Chatbot."""

from streamlit_msal import Msal
from azure.core.credentials import AccessToken, TokenCredential
from azure.identity import DefaultAzureCredential
from .constants import (
    AUTHORITY_BASE_URL
)

class MSALTokenCredential(TokenCredential):
    """Custom Token Credential for Azure AI Projects using MSAL token."""
    
    def __init__(self, access_token: str, expires_at: int = None):
        self._access_token = access_token
        self._expires_at = expires_at
    
    async def get_token(self, *scopes, **kwargs) -> AccessToken:
        """Get access token with expiration time."""
        return AccessToken(self._access_token, self._expires_at or 0)


def initialize_msal_auth(client_id: str, tenant_id: str) -> TokenCredential:
    """Initialize MSAL authentication UI.
    
    Args:
        client_id: Azure AD client ID
        tenant_id: Azure AD tenant ID
        
    Returns:
        TokenCredential instance or None if not authenticated
    """
    # Form authority URL from tenant_id
    authority = f"{AUTHORITY_BASE_URL}/{tenant_id}"
    
    auth_data = Msal.initialize_ui(
        client_id=client_id,
        authority=authority,
        scopes=[],  # Required scope for Azure AI Foundry
        # Customize (Default values):
        connecting_label="Connecting",
        disconnected_label="Disconnected",
        sign_in_label="Sign in",
        sign_out_label="Sign out"
    )
    
    # Check if authentication was successful
    if not _is_authenticated(auth_data):
        return None
        
    return DefaultAzureCredential()

def _is_authenticated(auth_data: dict) -> bool:
    """Check if user is authenticated.
    
    Args:
        auth_data: Authentication data from MSAL
        
    Returns:
        True if authenticated, False otherwise
    """
    return auth_data and "accessToken" in auth_data
