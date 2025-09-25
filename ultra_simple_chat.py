"""Ultra simple chat - following Microsoft documentation."""

import streamlit as st
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
import time
from src.config import get_config
from src.constants import PROJ_ENDPOINT_KEY, AGENT_ID_KEY
from src.event_parser import EventParser, MessageDeltaEvent

def get_response(thread_id: str, message: str, project_endpoint: str, agent_id: str):
    """Get AI response using sync client."""
    client = AIProjectClient(project_endpoint, DefaultAzureCredential())
    agents_client = client.agents
    
    # Create user message
    agents_client.messages.create(thread_id=thread_id, role="user", content=message)

    # Stream the response
    stream = agents_client.runs.stream(
        thread_id=thread_id,
        agent_id=agent_id,
        response_format="auto"
    )

    return stream

def main():
    st.title("🤖 Ultra Simple Chat")
    
    # Get configuration
    config = get_config()
    if not config:
        st.error("❌ Please configure your Azure AI Foundry settings in Streamlit secrets.")
        st.stop()
    
    project_endpoint = config[PROJ_ENDPOINT_KEY]
    agent_id = config[AGENT_ID_KEY]
    
    # Initialize
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = None
    
    # Create thread
    if not st.session_state.thread_id:
        client = AIProjectClient(project_endpoint, DefaultAzureCredential())
        thread = client.agents.threads.create()
        st.session_state.thread_id = thread.id
    
    # Display messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
    
    # Chat input
    if prompt := st.chat_input("Say something:"):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        
        # Get AI response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                stream = get_response(st.session_state.thread_id, prompt, project_endpoint, agent_id)
                
                # Create generator for st.write_stream using EventParser
                def stream_generator():
                    for event_bytes in stream.response_iterator:
                        parsed_event = EventParser.parse_event(event_bytes)
                        if isinstance(parsed_event, MessageDeltaEvent):
                            yield parsed_event.text_value
                
                content_response = st.write_stream(stream_generator)
        st.session_state.messages.append({"role": "assistant", "content": content_response})

if __name__ == "__main__":
    main()
