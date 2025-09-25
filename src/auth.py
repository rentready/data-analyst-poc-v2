"""Authentication management for Azure AI Foundry Chatbot."""

from streamlit_msal import Msal
from azure.core.credentials import AccessToken, TokenCredential
from azure.identity import DefaultAzureCredential


class MSALTokenCredential(TokenCredential):
    """Custom Token Credential for Azure AI Projects using MSAL token."""
    
    def __init__(self, access_token: str, expires_at: int = None):
        self._access_token = access_token
        self._expires_at = expires_at
    
    async def get_token(self, *scopes, **kwargs) -> AccessToken:
        """Get access token with expiration time."""
        return AccessToken(self._access_token, self._expires_at or 0)


def initialize_msal_auth(client_id: str, authority: str) -> dict:
    """Initialize MSAL authentication UI.
    
    Args:
        client_id: Azure AD client ID
        authority: Azure AD authority URL
        
    Returns:
        Authentication data from MSAL
    """
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
    return auth_data


def get_credential(auth_data: dict) -> TokenCredential:
    """Get appropriate credential for Azure AI client.
    
    Args:
        auth_data: Authentication data from MSAL
        
    Returns:
        TokenCredential instance
    """
    # Get expiration time from token claims
    account = auth_data.get('account', {})
    id_token_claims = account.get('idTokenClaims', {})
    expires_at = id_token_claims.get('exp', 0)
    
    # Try DefaultAzureCredential first (uses environment variables)
    try:
        return DefaultAzureCredential()
    except Exception:
        # Fallback to MSAL token
        return MSALTokenCredential(auth_data["accessToken"], expires_at)


def is_authenticated(auth_data: dict) -> bool:
    """Check if user is authenticated.
    
    Args:
        auth_data: Authentication data from MSAL
        
    Returns:
        True if authenticated, False otherwise
    """
    return auth_data and "accessToken" in auth_data
