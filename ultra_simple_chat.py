"""Ultra simple chat - following Microsoft documentation."""

from pickle import NONE
import streamlit as st
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
import logging
import time
import json
from src.config import get_config, get_mcp_config, setup_environment_variables
from src.constants import PROJ_ENDPOINT_KEY, AGENT_ID_KEY
from src.event_parser import EventParser, MessageDeltaEvent, ThreadRunStepFailedEvent, ThreadRunStepCompletedEvent, ThreadRunStepDeltaEvent, DoneEvent, IncompleteEvent, ThreadRunRequiresActionEvent, MCPToolCall
from src.mcp_client import get_mcp_token_sync
from src.utils import extract_tool_result
from azure.ai.agents.models import McpTool, ToolApproval, RequiredMcpToolCall, SubmitToolApprovalAction, ListSortOrder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_tool_result(output):
    """Parse tool result from output."""
    if not output:
        return None
        
    try:
        if 'TOOL RESULT:' in output:
            # Extract JSON part after TOOL RESULT:
            json_part = output.split('TOOL RESULT:')[1].strip()
            result = json.loads(json_part)
            logger.info(f"🔧 PARSED JSON RESULT: {result}")
            return result
        else:
            # Try to parse as JSON directly
            result = json.loads(output)
            logger.info(f"🔧 PARSED DIRECT JSON: {result}")
            return result
    except Exception as e:
        logger.info(f"🔧 JSON PARSE FAILED, RETURNING AS TEXT: {e}")
        # Return full output if JSON parsing fails
        return output

def show_structured_result(result):
    """Show structured result data in a simple format."""
    if isinstance(result, dict):
        if 'success' in result and result['success']:
            st.success("✅ Tool executed successfully")
            if 'count' in result:
                st.info(f"📊 Found {result['count']} results")
        elif 'success' in result and not result['success']:
            st.error("❌ Tool execution failed")
            if 'error' in result:
                st.error(f"**Error:** {result['error']}")
    
    # Always show the raw data
    st.json(result)

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

if 'stage' not in st.session_state:
    st.session_state.stage = 'user_input'
if 'run_id' not in st.session_state:
    st.session_state.run_id = None

def on_tool_approval(success: bool):
    st.session_state.stage = 'tool_approved'
    # Use the stored run_id from session state
    if st.session_state.run_id:
        # Get the current run status
        run = agents_client.runs.get(thread_id=st.session_state.thread_id, run_id=st.session_state.run_id)
        
        if run.status == "requires_action":
            submit_tool_approvals(st.session_state.thread_id, st.session_state.run_id, run.required_action.submit_tool_approval.tool_calls, success, project_endpoint)

def show_tool_approval_ui(tool_calls: list, thread_id: str, run_id: str, project_endpoint: str):
    """Show tool approval UI and return True if approved."""
    st.warning("🔧 MCP Tool requires approval")
    
    for i, tool_call in enumerate(tool_calls):
        with st.expander(f"Tool: {tool_call.name} ({tool_call.server_label})", expanded=True):
            st.write(f"**Tool ID:** {tool_call.id}")
            st.write(f"**Type:** {tool_call.type}")
            st.write(f"**Server:** {tool_call.server_label}")
            
            if tool_call.arguments:
                st.write("**Arguments:**")
                st.json(tool_call.arguments)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.button("✅ Approve All", key=f"approve_all_{run_id}", on_click=on_tool_approval, args=(True,))
    
    with col2:
        st.button("❌ Deny All", key=f"deny_all_{run_id}", on_click=on_tool_approval, args=(False,))

def get_latest_assistant_message(agents_client, thread_id: str):
    """Get the latest assistant message from the thread using the optimized API."""
    try:
        # Use the optimized API method
        message_text = agents_client.messages.get_last_message_text_by_role(thread_id=thread_id, role="assistant")
        if message_text:
            return message_text.text.value
        return None
    except Exception as e:
        logger.error(f"Error getting latest assistant message: {e}")
        return None

def get_message_by_id(agents_client, thread_id: str, message_id: str):
    """Get message content by message ID."""
    try:
        message = agents_client.messages.get(thread_id=thread_id, message_id=message_id)
        logger.info(f"Message: {message}")
        if message.text_messages:
            return message.text_messages[-1].text.value
        return "No content"
    except Exception as e:
        logger.error(f"Error getting message {message_id}: {e}")
        return None

def show_tool_result(tool_name, result):
    """Show tool result in a simple format."""
    with st.status(f"✅ {tool_name} completed", expanded=True):
        show_structured_result(result)

def poll_run_until_completion(agents_client, thread_id: str, run_id: str, status_container=None):
    """Poll run status until completion, handling tool approvals if needed."""
    while True:
        run = agents_client.runs.get(thread_id=thread_id, run_id=run_id)
        logger.info(f"Run status: {run.status}")
        
        if run.status == "requires_action" and isinstance(run.required_action, SubmitToolApprovalAction):
            if status_container:
                status_container.status("Tool approval...")
            logger.info(f"Tool approval required: {run.required_action.submit_tool_approval.tool_calls}")
            show_tool_approval_ui(run.required_action.submit_tool_approval.tool_calls, thread_id, run.id, project_endpoint)
            return "requires_approval"
        
        # Get run steps to see what's happening
        if run.status == "in_progress":
            try:
                steps = client.agents.run_steps.list(thread_id=thread_id, run_id=run_id)
                logger.info(f"Steps: {steps}")
                for step in steps:
                    step_type = getattr(step, 'type', 'unknown')
                    step_status = getattr(step, 'status', 'unknown')
                    step_id = getattr(step, 'id', 'unknown')
                    
                    logger.info(f"Step {step_id}: {step_type} - {step_status}")
                    
                    # Log step details based on type
                    if hasattr(step, 'step_details') and step.step_details:
                        step_details = step.step_details
                        logger.info(f"  Step details: {step_details}")
                        
                        if step_type == "message_creation" and 'message_creation' in step_details:
                            message_id = step_details['message_creation'].get('message_id', 'unknown')
                            logger.info(f"  Message creation: {message_id}")
                            logger.info(f"  Step details: {step_details}")
                            
                            # Get and display message content immediately if completed or in progress
                            if step_status in ["completed", "in_progress"]:
                                try:
                                    message_content = get_message_by_id(agents_client, thread_id, message_id)
                                    if message_content:
                                        st.write(message_content)
                                        st.session_state.messages.append({"role": "assistant", "content": message_content})
                                except Exception as e:
                                    logger.error(f"Error getting message content: {e}")
                        
                        elif step_type == "tool_calls":
                            # Show tool results immediately when completed
                            try:
                                tool_calls = step_details.get('tool_calls', [])
                                for tool_call in tool_calls:
                                    tool_name = tool_call.get('name', 'Unknown Tool')
                                    tool_output = tool_call.get('output', '')
                                    
                                    if tool_output:
                                        # Parse and show tool result
                                        parsed_result = parse_tool_result(tool_output)
                                        if parsed_result:
                                            show_tool_result(tool_name, parsed_result)
                                        else:
                                            # Show raw output if parsing failed
                                            with st.status(f"🔧 {tool_name} completed", expanded=True):
                                                st.text(tool_output)
                            except Exception as e:
                                logger.error(f"Error showing tool results: {e}")
                        
            except Exception as e:
                logger.error(f"Error getting run steps: {e}")
                # Try alternative approach - get run details
                try:
                    run_details = agents_client.runs.get(thread_id=thread_id, run_id=run_id)
                    logger.info(f"Run details: {run_details}")
                    if hasattr(run_details, 'required_action') and run_details.required_action:
                        logger.info(f"Required action: {run_details.required_action}")
                except Exception as e2:
                    logger.error(f"Error getting run details: {e2}")
        
        if run.status not in ["queued", "in_progress"]:
            # Check if there's a final message that wasn't shown yet
            try:
                latest_message = get_latest_assistant_message(agents_client, thread_id)
                if latest_message:
                    # Check if this message was already shown
                    if not any(msg.get("content") == latest_message for msg in st.session_state.messages):
                        st.write(latest_message)
                        st.session_state.messages.append({"role": "assistant", "content": latest_message})
            except Exception as e:
                logger.error(f"Error getting final message: {e}")
            
            return "completed"
        
        if status_container:
            status_container.status("Processing...")
        time.sleep(1)

def submit_tool_approvals(thread_id: str, run_id: str, tool_calls: list, approved: bool, project_endpoint: str):
    """Submit tool approvals to Azure AI Foundry."""
    try:
        run = agents_client.runs.get(thread_id=thread_id, run_id=run_id)

        logger.info(f"Run status: {run.status} required action: {run.required_action}")
        if run.status == "requires_action" and isinstance(run.required_action, SubmitToolApprovalAction):
            tool_calls = run.required_action.submit_tool_approval.tool_calls
            if not tool_calls:
                logger.warning("No tool calls provided - cancelling run")
                agents_client.runs.cancel(thread_id=thread_id, run_id=run_id)
                return

            tool_approvals = []
            for tool_call in tool_calls:
                if isinstance(tool_call, RequiredMcpToolCall):
                    try:
                        tool_approvals.append(
                            ToolApproval(
                                tool_call_id=tool_call.id,
                                approve=True,
                                headers=mcp_tool.headers,
                            )
                        )
                    except Exception as e:
                        logger.error(f"Error approving tool_call {tool_call.id}: {e}")

            logger.info(f"tool_approvals: {tool_approvals}")
            if tool_approvals:
                logger.info(f"Submitting {len(tool_approvals)} tool approvals")
                agents_client.runs.submit_tool_outputs(
                    thread_id=thread_id, run_id=run_id, tool_approvals=tool_approvals
                )
                logger.info(f"Submitted {len(tool_approvals)} tool approvals")
        return True
        
    except Exception as e:
        logger.error(f"Failed to submit tool approvals: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception details: {str(e)}")
        return False

def create_run(thread_id: str, message: str, project_endpoint: str, agent_id: str):
    """Get AI response using sync client."""
    # Create user message
    agents_client.messages.create(thread_id=thread_id, role="user", content=message)


    # Initialize MCP tool if config and token available
    tool_resources = []
    if mcp_config and mcp_token:
        try:
            # Get tool resources
            tool_resources = mcp_tool.resources
            logger.info(f"MCP tool initialized with {len(tool_resources)} resources")
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP tool: {e}")

    # Stream the response with MCP token in headers if available
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
    
    # Store run_id in session state
    st.session_state.run_id = run.id
    
    return run

def main():
    st.title("🤖 Ultra Simple Chat")
    
    # Initialize
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = None
    
    # Create thread
    if not st.session_state.thread_id:
        thread = client.agents.threads.create()
        st.session_state.thread_id = thread.id
    
    # Display messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    run = None
    prompt = None
    if st.session_state.stage == 'user_input' and (prompt := st.chat_input("Say something:")):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        # Get AI response
        with st.chat_message("assistant"):
            with st.spinner("Thinking...", show_time=True):
                run = create_run(st.session_state.thread_id, prompt, project_endpoint, agent_id)
            
            logger.info(f"Run created: {run}")
            # Store run_id for potential tool approval
            st.session_state.run_id = run.id

    if st.session_state.stage == 'tool_approved':
        logger.info(f"Tool approved stage")

    run = st.session_state.run_id

    result = None

    if run:
    # Process the run
        result = poll_run_until_completion(agents_client, st.session_state.thread_id, st.session_state.run_id, st.empty())
    
    if result == "requires_approval":
        st.session_state.stage = 'tool_approval'
        return
    elif result == "completed":
        # Get and display the latest assistant message
        latest_message = get_latest_assistant_message(agents_client, st.session_state.thread_id)
        if latest_message:
            st.write(latest_message)
            st.session_state.messages.append({"role": "assistant", "content": latest_message})
        
        # Reset stage to allow new user input
        st.session_state.stage = 'user_input'
        st.session_state.run_id = None

if __name__ == "__main__":
    main()
