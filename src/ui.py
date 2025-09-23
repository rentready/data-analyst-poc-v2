"""UI components for Azure AI Foundry Chatbot."""

import streamlit as st
from typing import List, Dict, Any, Optional
from .constants import DEFAULT_TYPING_DELAY


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


def render_typing_effect(text: str, delay: float = 0.03) -> None:
    """Render text with typing effect.
    
    Args:
        text: Text to display with typing effect
        delay: Delay between characters in seconds
    """
    import time
    
    placeholder = st.empty()
    displayed_text = ""
    
    for char in text:
        displayed_text += char
        placeholder.markdown(displayed_text + "▌")  # Cursor effect
        time.sleep(delay)
    
    # Remove cursor at the end
    placeholder.markdown(displayed_text)


class StreamingDisplay:
    """Class to handle streaming text display with typing effect."""
    
    def __init__(self, placeholder=None, typing_delay: float = DEFAULT_TYPING_DELAY):
        self.placeholder = placeholder or st.empty()
        self.displayed_text = ""
        self.cursor = "▌"
        self.typing_delay = typing_delay
    
    def add_chunk(self, chunk: str) -> None:
        """Add a chunk of text to the display with typing effect.
        
        Args:
            chunk: Text chunk to add
        """
        import time
        
        # Add each character with a small delay for typing effect
        for char in chunk:
            self.displayed_text += char
            self.placeholder.markdown(self.displayed_text + self.cursor)
            time.sleep(self.typing_delay)
    
    def finalize(self) -> None:
        """Finalize the display by removing the cursor."""
        self.placeholder.markdown(self.displayed_text)
    
    def get_text(self) -> str:
        """Get the current displayed text.
        
        Returns:
            Current displayed text
        """
        return self.displayed_text


