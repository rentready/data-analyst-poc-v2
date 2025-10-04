"""Ultra simple chat - refactored with event stream architecture."""

from tracemalloc import stop
from src.workflows import agent_executor
import streamlit as st
import logging
from src.config import get_config, get_mcp_config, setup_environment_variables, get_auth_config
from src.constants import PROJ_ENDPOINT_KEY, AGENT_ID_KEY
from src.mcp_client import get_mcp_token_sync, display_mcp_status
from src.auth import initialize_msal_auth
from src.agent_manager import AgentManager
from src.run_processor import RunProcessor
from src.event_renderer import EventRenderer, render_error_buttons
from src.run_events import RequiresApprovalEvent, MessageEvent, ErrorEvent, ToolCallEvent
from src.workflows.agent_executor import CustomAzureAgentExecutor
from agent_framework import WorkflowBuilder, WorkflowOutputEvent
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def on_tool_approve(event: RequiresApprovalEvent, agent_manager: AgentManager):
    """Handle tool approval."""
    if agent_manager.submit_approvals(event, approved=True):
        # Unblock processor and continue
        if 'processor' in st.session_state and st.session_state.processor:
            st.session_state.processor.unblock()
        st.session_state.pending_approval = None
        st.session_state.stage = 'processing'


def on_tool_deny(event: RequiresApprovalEvent, agent_manager: AgentManager):
    """Handle tool denial."""
    if agent_manager.submit_approvals(event, approved=False):
        # Denied - stop processing
        st.session_state.pending_approval = None
        st.session_state.processor = None
        st.session_state.stage = 'user_input'


def on_error_retry(agent_manager: AgentManager):
    """Handle error retry - create new run with retry instruction."""
    # Create retry instruction message - don't repeat user's message
    retry_message = "Please continue from where the previous attempt failed. Retry the last operation that encountered an error."
    
    # Add retry message to chat
    st.session_state.messages.append({
        "role": "user", 
        "content": f"🔄 **Retrying previous request**"
    })
    
    # Create new run with retry instruction
    with st.spinner("Creating new run for retry...", show_time=True):
        run_id = agent_manager.create_run(st.session_state.thread_id, retry_message)
        st.session_state.run_id = run_id
        st.session_state.processor = RunProcessor(agent_manager.agents_client)
        st.session_state.stage = 'processing'
        st.session_state.error_event = None


def on_error_cancel():
    """Handle error cancel."""
    st.session_state.stage = 'user_input'
    st.session_state.run_id = None
    st.session_state.processor = None
    st.session_state.error_event = None

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


def initialize_app() -> AgentManager:
    """
    Initialize application: config, auth, MCP, agent manager, session state.
    Returns AgentManager instance.
    """
    # Get configuration
    config = get_config()
    if not config:
        st.error("❌ Please configure your Azure AI Foundry settings in Streamlit secrets.")
        st.stop()
    
    # Setup environment
    setup_environment_variables()
    
    # Get authentication configuration
    client_id, tenant_id, _ = get_auth_config()
    if not client_id or not tenant_id:
        st.stop()
    
    # Initialize MSAL authentication in sidebar
    with st.sidebar:
        token_credential = initialize_msal_auth(client_id, tenant_id)
    
    # Check if user is authenticated
    if not token_credential:
        st.error("❌ Please sign in to use the chatbot.")
        st.stop()
    
    # Get MCP configuration and token
    mcp_config = get_mcp_config()
    mcp_token = get_mcp_token_sync(mcp_config)
    
    # Display MCP status in sidebar
    # Get approval setting (default to True)
    require_approval = True
    
    if mcp_config:
        with st.sidebar:
            display_mcp_status(mcp_config, mcp_token)
            # Add approval setting inside MCP section
            st.divider()
            require_approval = st.checkbox(
                "Require tool approval", 
                value=True,
                help="When enabled, you'll need to approve each tool call before execution"
            )
    
    # Initialize agent manager
    agent_manager = AgentManager(
        project_endpoint=config[PROJ_ENDPOINT_KEY],
        agent_id=config[AGENT_ID_KEY],
        mcp_config=mcp_config,
        mcp_token=mcp_token,
        require_approval=require_approval
    )
    
    # Initialize session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = None
    if "processor" not in st.session_state:
        st.session_state.processor = None
    if 'stage' not in st.session_state:
        st.session_state.stage = 'user_input'
    if 'run_id' not in st.session_state:
        st.session_state.run_id = None
    if 'pending_approval' not in st.session_state:
        st.session_state.pending_approval = None
    if 'error_event' not in st.session_state:
        st.session_state.error_event = None
    
    # Create thread if needed
    if not st.session_state.thread_id:
        st.session_state.thread_id = agent_manager.create_thread()
    
    return agent_manager


def main():
    st.title("🤖 Ultra Simple Chat")
    
    # Initialize app (config, auth, MCP, agent manager, session state, thread)
    agent_manager = initialize_app()
    
    # Display message history
    render_message_history()
    
    # Handle pending approval (blocking state)
    if st.session_state.pending_approval:
        event = st.session_state.pending_approval
        with st.chat_message("assistant"):
            EventRenderer.render_approval_request(event,
                                                lambda e: on_tool_approve(e, agent_manager),
                                                lambda e: on_tool_deny(e, agent_manager))
        return
    
    # Handle error state
    if st.session_state.stage == 'error' and 'error_event' in st.session_state:
        error_event = st.session_state.error_event
        with st.chat_message("assistant"):
            EventRenderer.render_error(error_event)
            render_error_buttons(
                lambda: on_error_retry(agent_manager), 
                on_error_cancel
            )
        return
    
    workflow = None
    events = None
    # Handle user input
    if st.session_state.stage == 'user_input':
        if prompt := st.chat_input("Say something:"):
            # User message - simple dict (not an event)
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            with st.chat_message("user"):
                st.markdown(prompt)
            
            with st.spinner("Thinking...", show_time=True):
                st.session_state.stage = 'processing'
                logger.info(f"Processing prompt: {prompt}")
                agent_executor = CustomAzureAgentExecutor(agent_manager, st.session_state.thread_id)
                workflow = WorkflowBuilder().set_start_executor(agent_executor).build()
                events = workflow.run_stream(prompt)
                

    # Process run events
    if st.session_state.stage == 'processing':
        
        with st.chat_message("assistant"):
            async def run_workflow_stream(events):
                events_exhausted = False
            
                while not events_exhausted:
                    event = None
                    with st.spinner("Processing...", show_time=True):
                        try:
                            event = await anext(events)
                        except StopAsyncIteration as e:
                            events_exhausted = True
                            continue;

                        st.write(event)
                        if isinstance(event, WorkflowOutputEvent):
                            if isinstance(event.data, MessageEvent):
                                EventRenderer.render_message_with_typing(event.data)

            asyncio.run(run_workflow_stream(events))


if __name__ == "__main__":
    main()
