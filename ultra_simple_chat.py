"""Ultra simple chat - refactored with event stream architecture."""

import streamlit as st
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
import logging
from src.config import get_config, get_mcp_config, setup_environment_variables
from src.constants import PROJ_ENDPOINT_KEY, AGENT_ID_KEY
from src.mcp_client import get_mcp_token_sync
from azure.ai.agents.models import McpTool, ToolApproval, RequiredMcpToolCall
from src.run_processor import RunProcessor
from src.event_renderer import EventRenderer, render_approval_buttons
from src.run_events import RequiresApprovalEvent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration and MCP setup

# Get configuration
config = get_config()
if not config:
    st.error("❌ Please configure your Azure AI Foundry settings in Streamlit secrets.")
    st.stop()

project_endpoint = config[PROJ_ENDPOINT_KEY]
agent_id = config[AGENT_ID_KEY]

# Get MCP configuration
setup_environment_variables()
mcp_config = get_mcp_config()
# Get server label from config
server_label = mcp_config.get("mcp_server_label", "mcp_server")

mcp_token = get_mcp_token_sync(mcp_config)

# Create MCP tool with authorization header
mcp_tool = McpTool(
    server_label=server_label,
    server_url="",  # URL will be set by the agent configuration
    allowed_tools=[]  # Allow all tools
)

# Update headers with authorization token
mcp_tool.update_headers("authorization", f"bearer {mcp_token}")
#mcp_tool.set_approval_mode("never")

client = AIProjectClient(project_endpoint, DefaultAzureCredential())
agents_client = client.agents

# Session state management
if 'stage' not in st.session_state:
    st.session_state.stage = 'user_input'
if 'run_id' not in st.session_state:
    st.session_state.run_id = None
if 'pending_approval' not in st.session_state:
    st.session_state.pending_approval = None


def submit_tool_approvals(event: RequiresApprovalEvent, approved: bool):
    """Submit tool approvals to Azure AI Foundry."""
    try:
        client = AIProjectClient(project_endpoint, DefaultAzureCredential())
        agents_client = client.agents
        
        tool_approvals = []
        for tool_call in event.tool_calls:
            if isinstance(tool_call, RequiredMcpToolCall):
                try:
                    tool_approvals.append(
                        ToolApproval(
                            tool_call_id=tool_call.id,
                            approve=approved,
                            headers=mcp_tool.headers,
                        )
                    )
                except Exception as e:
                    logger.error(f"Error creating approval for {tool_call.id}: {e}")
        
        if tool_approvals:
            logger.info(f"Submitting {len(tool_approvals)} tool approvals (approved={approved})")
            agents_client.runs.submit_tool_outputs(
                thread_id=event.thread_id,
                run_id=event.run_id,
                tool_approvals=tool_approvals
            )
            logger.info(f"✅ Submitted tool approvals")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Failed to submit tool approvals: {e}")
        return False


def on_tool_approve(event: RequiresApprovalEvent):
    """Handle tool approval."""
    if submit_tool_approvals(event, approved=True):
        # Unblock processor and continue
        if 'processor' in st.session_state and st.session_state.processor:
            st.session_state.processor.unblock()
        st.session_state.pending_approval = None
        st.session_state.stage = 'processing'
        st.rerun()


def on_tool_deny(event: RequiresApprovalEvent):
    """Handle tool denial."""
    if submit_tool_approvals(event, approved=False):
        # Denied - stop processing
        st.session_state.pending_approval = None
        st.session_state.processor = None
        st.session_state.stage = 'user_input'
        st.rerun()

def create_run(thread_id: str, message: str) -> str:
    """Create a run and return run_id."""
    client = AIProjectClient(project_endpoint, DefaultAzureCredential())
    agents_client = client.agents
    
    # Create user message
    agents_client.messages.create(thread_id=thread_id, role="user", content=message)
    
    # Get tool resources if MCP is available
    tool_resources = []
    if mcp_config and mcp_token:
        try:
            tool_resources = mcp_tool.resources
            logger.info(f"MCP tool initialized with {len(tool_resources)} resources")
        except Exception as e:
            logger.error(f"Failed to initialize MCP tool: {e}")
    
    # Create run with MCP headers
    headers = {}
    if mcp_token:
        headers["Authorization"] = f"Bearer {mcp_token}"
    
    run = agents_client.runs.create(
        thread_id=thread_id,
        agent_id=agent_id,
        instructions="You are a helpful assistant, you will respond to the user's message and you will use the tools provided to you to help the user. You will justify what tools you are going to use before requesting them.",
        headers=headers,
        tool_resources=tool_resources
    )
    
    logger.info(f"✅ Created run: {run.id}")
    return run.id

def render_message_history():
    """Render message history from session state."""
    for item in st.session_state.messages:
        if isinstance(item, dict):
            # User message - simple dict
            with st.chat_message(item["role"]):
                st.markdown(item["content"])
        else:
            # Assistant event - RunEvent object
            with st.chat_message("assistant"):
                EventRenderer.render(item)


def main():
    st.title("🤖 Ultra Simple Chat")
    
    # Initialize session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = None
    if "processor" not in st.session_state:
        st.session_state.processor = None
    
    # Create thread if needed
    if not st.session_state.thread_id:
        client = AIProjectClient(project_endpoint, DefaultAzureCredential())
        thread = client.agents.threads.create()
        st.session_state.thread_id = thread.id
        logger.info(f"✅ Created thread: {thread.id}")
    
    # Display message history
    render_message_history()
    
    # Handle pending approval (blocking state)
    if st.session_state.pending_approval:
        event = st.session_state.pending_approval
        with st.chat_message("assistant"):
            EventRenderer.render_approval_request(event)
            render_approval_buttons(event, on_tool_approve, on_tool_deny)
        return
    
    # Handle user input
    if st.session_state.stage == 'user_input':
        if prompt := st.chat_input("Say something:"):
            # User message - simple dict (not an event)
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # Create run and new processor
            run_id = create_run(st.session_state.thread_id, prompt)
            st.session_state.run_id = run_id
            st.session_state.processor = RunProcessor(agents_client)
            st.session_state.stage = 'processing'
            st.rerun()
    
    # Process run events
    if st.session_state.stage == 'processing' and st.session_state.run_id:
        processor = st.session_state.processor
        
        if not processor:
            logger.error("No processor in session state!")
            st.error("Error: No processor found")
            st.session_state.stage = 'user_input'
            return
        
        with st.chat_message("assistant"):
            # Stream events using existing processor (maintains state across reruns)
            for event in processor.poll_run_events(
                thread_id=st.session_state.thread_id,
                run_id=st.session_state.run_id
            ):
                logger.info(f"📦 Received event: {event.event_type} (id: {event.event_id})")
                
                # Handle blocking event
                if event.is_blocking:
                    st.session_state.pending_approval = event
                    st.rerun()
                    return
                
                # Render event and store it (not dict) in history
                EventRenderer.render(event)
                
                # Store event in history (skip completion/error events)
                if event.event_type not in ['completed', 'error']:
                    st.session_state.messages.append(event)
        
        # Run completed - reset state
        logger.info("✅ Run completed, resetting state")
        st.session_state.stage = 'user_input'
        st.session_state.run_id = None
        st.session_state.processor = None
        st.rerun()


if __name__ == "__main__":
    main()
