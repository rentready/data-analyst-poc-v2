"""Azure AI Foundry Chatbot - Main Streamlit Application."""

import asyncio
import logging
import streamlit as st

# Import our custom modules
from src.config import get_config, setup_environment_variables, get_auth_config
from src.auth import initialize_msal_auth, get_credential, is_authenticated
from src.ai_client import AzureAIClient, handle_chat, get_or_create_thread
from src.ui import (
    render_header, render_messages, render_annotations, 
    render_error_message, render_spinner_with_message, StreamingDisplay
)
from src.constants import PROJ_ENDPOINT_KEY, AGENT_ID_KEY, USER_ROLE, ASSISTANT_ROLE

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def initialize_session_state(config: dict) -> None:
    """Initialize Streamlit session state.
    
    Args:
        config: Configuration dictionary
    """
    if "messages" not in st.session_state:
        st.session_state.messages = []
        
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = None
        
    if "agent_id" not in st.session_state:
        st.session_state.agent_id = config[AGENT_ID_KEY]


async def process_chat_message(
    config: dict, 
    auth_data: dict, 
    prompt: str,
    on_stream_chunk: callable = None
) -> tuple[str, list]:
    """Process a chat message and return response.
    
    Args:
        config: Configuration dictionary
        auth_data: Authentication data
        prompt: User's message
        on_stream_chunk: Optional callback for streaming chunks
        
    Returns:
        Tuple of (response_content, annotations)
    """
    # Get credential
    credential = get_credential(auth_data)
    
    # Initialize AI client
    async with AzureAIClient(config[PROJ_ENDPOINT_KEY], credential) as ai_project:
        agent_client = ai_project.agents
        
        # Get or create thread
        thread_id = await get_or_create_thread(
            agent_client, 
            st.session_state.thread_id, 
            config[AGENT_ID_KEY]
        )
        
        # Update session state
        if st.session_state.thread_id != thread_id:
            st.session_state.thread_id = thread_id
            st.session_state.agent_id = config[AGENT_ID_KEY]
        
        # Handle chat
        response_content, annotations = await handle_chat(
            ai_project, config[AGENT_ID_KEY], thread_id, prompt, on_stream_chunk
        )
        
        return response_content, annotations


def main() -> None:
    """Main application function."""
    # Render header
    render_header()
    
    # Get configuration
    config = get_config()
    if not config:
        st.stop()
    
    # Setup environment variables
    setup_environment_variables()
    
    # Get authentication configuration
    client_id, tenant_id, authority = get_auth_config()
    if not client_id or not tenant_id:
        st.stop()
    
    # Initialize MSAL authentication
    auth_data = initialize_msal_auth(client_id, authority)
    
    # Initialize session state
    initialize_session_state(config)
    
    # Display existing messages
    render_messages(st.session_state.messages)
    
    # Chat input
    if prompt := st.chat_input("What is up?"):
        # Add user message
        st.session_state.messages.append({"role": USER_ROLE, "content": prompt})
        with st.chat_message(USER_ROLE):
            st.markdown(prompt)

        # Generate response
        with st.chat_message(ASSISTANT_ROLE):
            try:
                # Check if user is authenticated
                if not is_authenticated(auth_data):
                    st.error("❌ Please sign in to use the chatbot.")
                    return
                
                # Create streaming display
                streaming_display = StreamingDisplay()
                
                # Define streaming callback
                def on_chunk(chunk: str):
                    streaming_display.add_chunk(chunk)
                
                # Process chat message with streaming
                response_content, annotations = asyncio.run(
                    process_chat_message(config, auth_data, prompt, on_chunk)
                )
                
                # Finalize the streaming display
                streaming_display.finalize()
                
                # Display annotations
                render_annotations(annotations)
                
                # Store response
                st.session_state.messages.append({
                    "role": ASSISTANT_ROLE,
                    "content": response_content,
                    "annotations": annotations
                })
                
            except Exception as e:
                render_error_message(str(e))
                st.session_state.messages.append({
                    "role": ASSISTANT_ROLE,
                    "content": "Sorry, I encountered an error. Please try again."
                })


if __name__ == "__main__":
    main()
