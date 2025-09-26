"""Ultra simple chat - following Microsoft documentation."""

from pickle import NONE
import streamlit as st
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
import logging
import time
from src.config import get_config, get_mcp_config, setup_environment_variables
from src.constants import PROJ_ENDPOINT_KEY, AGENT_ID_KEY
from src.event_parser import EventParser, MessageDeltaEvent, ThreadRunStepFailedEvent, ThreadRunStepCompletedEvent, ThreadRunStepDeltaEvent, DoneEvent, IncompleteEvent
from src.mcp_client import get_mcp_token_sync
from azure.ai.agents.models import McpTool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_tool_result(output: str) -> str:
    """Extract TOOL RESULT section from tool output."""
    try:
        # Look for "TOOL RESULT:" pattern
        if "TOOL RESULT:" in output:
            # Find the start of TOOL RESULT section
            start_idx = output.find("TOOL RESULT:")
            if start_idx != -1:
                # Extract everything after "TOOL RESULT:"
                result = output[start_idx + len("TOOL RESULT:"):].strip()
                return result
        return None
    except Exception as e:
        logger.error(f"Error extracting tool result: {e}")
        return None


def get_response(thread_id: str, message: str, project_endpoint: str, agent_id: str):
    """Get AI response using sync client."""
    client = AIProjectClient(project_endpoint, DefaultAzureCredential())
    agents_client = client.agents
    
    # Create user message
    agents_client.messages.create(thread_id=thread_id, role="user", content=message)

    # Get MCP configuration
    setup_environment_variables()
    mcp_config = get_mcp_config()

    mcp_token = get_mcp_token_sync(mcp_config)


    # Initialize MCP tool if config and token available
    tool_resources = []
    if mcp_config and mcp_token:
        try:
            # Get server label from config
            server_label = mcp_config.get("mcp_server_label", "mcp_server")
            
            # Create MCP tool with authorization header
            mcp_tool = McpTool(
                server_label=server_label,
                server_url="",  # URL will be set by the agent configuration
                allowed_tools=[]  # Allow all tools
            )
            
            # Update headers with authorization token
            mcp_tool.update_headers("authorization", f"bearer {mcp_token}")
            mcp_tool.set_approval_mode("never")
            
            # Get tool resources
            tool_resources = mcp_tool.resources
            logger.info(f"MCP tool initialized with {len(tool_resources)} resources")
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP tool: {e}")

    # Stream the response with MCP token in headers if available
    headers = {}
    if mcp_token:
        headers["Authorization"] = f"Bearer {mcp_token}"
    
    stream = agents_client.runs.stream(
        thread_id=thread_id,
        agent_id=agent_id,
        response_format="auto",
        headers=headers,
        tool_resources=tool_resources
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
            with st.spinner("Thinking...", show_time=True):
                stream = get_response(st.session_state.thread_id, prompt, project_endpoint, agent_id)
                
            # Create generator for st.write_stream using EventParser
            def stream_generator():
                status_container = st.empty()
                event_bytes = b''
                for raw_event_bytes in stream.response_iterator:

                    event_bytes += raw_event_bytes
                    parsed_event = EventParser.parse_event(event_bytes)

                    if isinstance(parsed_event, IncompleteEvent):
                        continue

                    # Reset event_bytes only after successful parsing
                    event_bytes = b''

                    if isinstance(parsed_event, MessageDeltaEvent):
                        status_container.empty()
                        time.sleep(0.02)
                        yield parsed_event.text_value
                    elif hasattr(parsed_event, 'status') and parsed_event.status == 'completed':
                        logger.info(f"✅ {parsed_event.__class__.__name__} completed")
                    elif hasattr(parsed_event, 'status') and parsed_event.status != 'completed':
                        logger.info(f"Processing: {parsed_event.status}")
                        status_container.status("Processing...")
                    elif isinstance(parsed_event, ThreadRunStepCompletedEvent):
                        logger.info(f"Step completed: {parsed_event.step_type}")
                    elif isinstance(parsed_event, ThreadRunStepDeltaEvent):
                        if parsed_event.has_output:
                            logger.info(f"🔧 MCP Tool: {parsed_event.tool_name} ({parsed_event.server_label})")
                            if parsed_event.output:
                                tool_result = extract_tool_result(parsed_event.output)
                                yield tool_result

                    elif isinstance(parsed_event, ThreadRunStepFailedEvent):
                        logger.info(f"❌ Tool failed: {parsed_event.error_code} - {parsed_event.error_message}")
                    elif isinstance(parsed_event, DoneEvent):
                        logger.info("Response completed")
                    elif isinstance(parsed_event, dict):
                        logger.info(f"Event: {parsed_event.get('type', 'unknown')}")
                    else:
                        logger.info(f"Unknown event: {event_bytes}")
            
            content_response = st.write_stream(stream_generator)
        st.session_state.messages.append({"role": "assistant", "content": content_response})

if __name__ == "__main__":
    main()
