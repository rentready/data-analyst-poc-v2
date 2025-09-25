"""UI components for Azure AI Foundry Chatbot."""

import streamlit as st
from typing import List, Dict, Any, Optional


def render_header() -> None:
    """Render the main header and description."""
    st.title("🤖 Azure AI Foundry Agent Chatbot")
    st.write(
        "This is a chatbot powered by Azure AI Foundry Agent. "
        "The configuration is set up via Streamlit secrets. "
        "Learn more about Azure AI Foundry at [Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-foundry/)."
    )


def render_messages(messages: List[Dict[str, Any]]) -> None:
    """Render chat messages.
    
    Args:
        messages: List of message dictionaries
    """
    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            # Display annotations if they exist
            if "annotations" in message and message["annotations"]:
                with st.expander("📎 Sources"):
                    for annotation in message["annotations"]:
                        st.write(f"**{annotation['file_name']}** ({annotation['type']})")


def render_annotations(annotations: List[Dict[str, Any]]) -> None:
    """Render annotations in an expander.
    
    Args:
        annotations: List of annotation dictionaries
    """
    if annotations:
        with st.expander("📎 Sources"):
            for annotation in annotations:
                st.write(f"**{annotation['file_name']}** ({annotation['type']})")


def render_config_sidebar(config: Dict[str, str], thread_id: Optional[str]) -> None:
    """Render configuration information in sidebar.
    
    Args:
        config: Configuration dictionary
        thread_id: Current thread ID
    """
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 🔧 Configuration")
        
        with st.expander("Azure AI Foundry"):
            st.write(f"**Endpoint:** {config['proj_endpoint']}")
            st.write(f"**Agent ID:** {config['agent_id']}")
            st.write(f"**Thread ID:** {thread_id}")


def render_error_message(error: str) -> None:
    """Render error message.
    
    Args:
        error: Error message to display
    """
    st.error(f"❌ Error generating response: {error}")


def render_spinner_with_message(message: str = "Thinking..."):
    """Context manager for rendering spinner with message.
    
    Args:
        message: Message to display in spinner
        
    Returns:
        Streamlit spinner context manager
    """
    return st.spinner(message)