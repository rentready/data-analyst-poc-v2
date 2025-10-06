"""Ultra simple chat - refactored with event stream architecture."""

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
from agent_framework import WorkflowBuilder, WorkflowOutputEvent, RequestInfoEvent, WorkflowFailedEvent, RequestInfoExecutor, WorkflowStatusEvent, WorkflowRunState
import asyncio

logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)

def on_tool_approve(event: RequiresApprovalEvent, agent_manager: AgentManager):
    """Handle tool approval."""
    if agent_manager.submit_approvals(event, approved=True):
        # Unblock processor and continue
        if 'processor' in st.session_state and st.session_state.processor:
            st.session_state.processor.unblock()
        st.session_state.pending_approval = None
        st.session_state.stage = 'processing'
        # Mark that we should skip the initial stream setup
        st.session_state.skip_run_stream = True


def on_tool_deny(event: RequiresApprovalEvent, agent_manager: AgentManager):
    """Handle tool denial."""
    if agent_manager.submit_approvals(event, approved=False):
        # Denied - stop processing
        st.session_state.pending_approval = None
        st.session_state.processor = None
        st.session_state.stage = 'user_input'
        # Mark that we should skip the initial stream setup
        st.session_state.skip_run_stream = True


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
    if 'skip_run_stream' not in st.session_state:
        st.session_state.skip_run_stream = False
    if 'current_prompt' not in st.session_state:
        st.session_state.current_prompt = None
    
    # Create thread if needed
    if not st.session_state.thread_id:
        st.session_state.thread_id = agent_manager.create_thread()
    
    return agent_manager


def run_async_task(async_func, *args):
    """
    Run an asynchronous function in a new event loop.

    Args:
    async_func (coroutine): The asynchronous function to execute.
    *args: Arguments to pass to the asynchronous function.

    Returns:
    None
    """
    
    loop = None

    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(async_func(*args))
    finally:
        # Close the existing loop if open
        if loop is not None:
            loop.close()

def main():
    st.title("🤖 Ultra Simple Chat")
    
    # Initialize app (config, auth, MCP, agent manager, session state, thread)
    agent_manager = initialize_app()
    
    # Display message history
    render_message_history()
    
    # Handle pending approval (blocking state)
    if st.session_state.pending_approval:
        event = st.session_state.pending_approval.data.event
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
    
    # Handle user input
    if st.session_state.stage == 'user_input':
        if prompt := st.chat_input("Say something:"):
            # User message - simple dict (not an event)
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            with st.chat_message("user"):
                st.markdown(prompt)
            
            with st.spinner("Thinking...", show_time=True):
                agent_executor = CustomAzureAgentExecutor(agent_manager, st.session_state.thread_id)
                tool_approval_executor = RequestInfoExecutor(id="request_tool_approval")
                workflow = (
                    WorkflowBuilder()
                    .set_start_executor(agent_executor)
                    .add_edge(agent_executor, tool_approval_executor)
                    .add_edge(tool_approval_executor, agent_executor)
                    .build()
                )
                st.session_state.stage = 'processing'
                st.session_state.workflow = workflow
                st.session_state.current_prompt = prompt
                st.session_state.skip_run_stream = False

    # Process run events
    if st.session_state.stage == 'processing' and st.session_state.workflow:
        async def run_workflow_stream():
            with st.chat_message("assistant"):
                # Check if we should skip the initial stream setup (e.g., after approval)
                if not st.session_state.get('skip_run_stream', False):
                    with st.spinner("Thinking...", show_time=True):
                        events = st.session_state.workflow.run_stream(st.session_state.current_prompt)
                else:
                    responses: dict[str, str] = {}
                    responses[st.session_state.pending_approval_id] = "result"
                    events =st.session_state.workflow.send_responses_streaming(responses)
                
                # Reset the skip flag
                st.session_state.skip_run_stream = False

                st.session_state.last_event = None

                events_exhausted = False
            
                while not events_exhausted:
                    event = None
                    with st.spinner("Processing...", show_time=True):
                        try:
                            event = await anext(events)
                        except StopAsyncIteration as e:
                            events_exhausted = True
                            continue;

                    logger.info(f"Event: {event}")
                    st.session_state.last_event = event
                    if isinstance(event, WorkflowOutputEvent):
                        if isinstance(event.data, MessageEvent):
                            EventRenderer.render_message_with_typing(event.data)
                            st.session_state.messages.append(event.data)
                    if (isinstance(event, RequestInfoEvent)):
                        st.session_state.pending_approval = event
                        st.session_state.pending_approval_id = event.request_id
                        st.session_state.events = events
                        #st.rerun()
                        break;

                    if (isinstance(event, WorkflowFailedEvent)):
                        st.session_state.error_event = event
                        st.session_state.stage = 'error'
                        #st.rerun()
                        break;

                async for event in events:
                    st.session_state.last_event = event
                logger.info("✅ 1. Run completed, resetting state")
                #st.rerun()
                #return;
    
        # Создать loop один раз и сохранить
        if 'event_loop' not in st.session_state or st.session_state.event_loop is None:
            st.session_state.event_loop = asyncio.new_event_loop()

        loop = st.session_state.event_loop
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_workflow_stream())

        logger.info("✅ Exited run_workflow_stream")

        if st.session_state.last_event is not None and \
            st.session_state.last_event.state!=WorkflowRunState.IDLE and st.session_state.last_event.state!=WorkflowRunState.CANCELLED \
            and st.session_state.last_event.state!=WorkflowRunState.FAILED:
            st.rerun()
            return
        # st.rerun()
        # return

        # Run completed - reset state
        logger.info("✅ 2. Run completed, resetting state")
        st.session_state.stage = 'user_input'
        st.session_state.run_id = None
        st.session_state.processor = None
        st.session_state.workflow = None
        st.session_state.current_prompt = None
        st.session_state.event_loop = None
        st.rerun()

if __name__ == "__main__":
    main()
