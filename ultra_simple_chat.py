"""Ultra simple chat - refactored with event stream architecture."""

import streamlit as st
import logging
from src.config import get_config, get_mcp_config, setup_environment_variables, get_auth_config
from src.constants import PROJ_ENDPOINT_KEY, AGENT_ID_KEY
from src.mcp_client import get_mcp_token_sync, display_mcp_status
from src.auth import initialize_msal_auth
from src.agent_manager import AgentManager
from src.run_processor import RunProcessor
from src.event_renderer import EventRenderer, render_approval_buttons
from src.run_events import RequiresApprovalEvent

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
        st.rerun()


def on_tool_deny(event: RequiresApprovalEvent, agent_manager: AgentManager):
    """Handle tool denial."""
    if agent_manager.submit_approvals(event, approved=False):
        # Denied - stop processing
        st.session_state.pending_approval = None
        st.session_state.processor = None
        st.session_state.stage = 'user_input'
        st.rerun()

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
    if mcp_config:
        with st.sidebar:
            display_mcp_status(mcp_config, mcp_token)
    
    # Initialize agent manager
    agent_manager = AgentManager(
        project_endpoint=config[PROJ_ENDPOINT_KEY],
        agent_id=config[AGENT_ID_KEY],
        mcp_config=mcp_config,
        mcp_token=mcp_token
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
    
    # Create thread if needed
    if not st.session_state.thread_id:
        st.session_state.thread_id = agent_manager.create_thread()
    
    # Display message history
    render_message_history()
    
    # Handle pending approval (blocking state)
    if st.session_state.pending_approval:
        event = st.session_state.pending_approval
        with st.chat_message("assistant"):
            EventRenderer.render_approval_request(event)
            render_approval_buttons(event, 
                                   lambda e: on_tool_approve(e, agent_manager),
                                   lambda e: on_tool_deny(e, agent_manager))
        return
    
    # Handle user input
    if st.session_state.stage == 'user_input':
        if prompt := st.chat_input("Say something:"):
            # User message - simple dict (not an event)
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # Create run and new processor
            run_id = agent_manager.create_run(st.session_state.thread_id, prompt)
            st.session_state.run_id = run_id
            st.session_state.processor = RunProcessor(agent_manager.agents_client)
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
