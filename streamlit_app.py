import streamlit as st
import asyncio
from streamlit_msal import Msal
import logging
from typing import Optional

from azure.ai.projects.aio import AIProjectClient
from azure.ai.agents.models import (
    AsyncAgentEventHandler,
    MessageDeltaChunk,
    ThreadMessage,
    ThreadRun,
    RunStep
)
from azure.core.credentials import AccessToken, TokenCredential

from azure.identity import DefaultAzureCredential
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Show title and description.
st.title("🤖 Azure AI Foundry Agent Chatbot")
st.write(
    "This is a chatbot powered by Azure AI Foundry Agent. "
    "The configuration is set up via Streamlit secrets. "
    "Learn more about Azure AI Foundry at [Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-foundry/)."
)

# Get configuration from Streamlit secrets
def get_config():
    """Get configuration from Streamlit secrets"""
    try:
        foundry_config = st.secrets["azure_ai_foundry"]
        config = {
            "proj_endpoint": foundry_config.get("proj_endpoint"),
            "agent_id": foundry_config.get("agent_id")
        }
        
        missing = [k for k, v in config.items() if not v]
        if missing:
            st.error(f"❌ Missing required configuration in secrets: {', '.join(missing)}")
            st.info("💡 Please check your `.streamlit/secrets.toml` file and add the required Azure AI Foundry configuration.")
            return None
        
        return config
    except KeyError as e:
        st.error(f"❌ Azure AI Foundry configuration not found in secrets: {e}")
        st.info("💡 Please copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and add your configuration.")
        return None

config = get_config()
if not config:
    st.stop()

# Set environment variables for DefaultAzureCredential
try:
    env_config = st.secrets["env"]
    os.environ["AZURE_CLIENT_ID"] = env_config.get("AZURE_CLIENT_ID", "")
    os.environ["AZURE_CLIENT_SECRET"] = env_config.get("AZURE_CLIENT_SECRET", "")
    os.environ["AZURE_TENANT_ID"] = env_config.get("AZURE_TENANT_ID", "")
    pass  # Environment variables set
except KeyError:
    pass  # No environment variables found

# Initialize MSAL authentication using environment variables
client_id = os.environ.get("AZURE_CLIENT_ID")
tenant_id = os.environ.get("AZURE_TENANT_ID")

if not client_id or not tenant_id:
    st.error("❌ Missing required environment variables: AZURE_CLIENT_ID and AZURE_TENANT_ID")
    st.info("💡 Please set these variables in your secrets.toml file or environment.")
    st.stop()

authority = f"https://login.microsoftonline.com/{tenant_id}"

with st.sidebar:
    auth_data = Msal.initialize_ui(
        client_id=client_id,
        authority=authority,
        scopes=[], # Required scope for Azure AI Foundry
        # Customize (Default values):
        connecting_label="Connecting",
        disconnected_label="Disconnected",
        sign_in_label="Sign in",
        sign_out_label="Sign out"
    )

# Custom Token Credential for Azure AI Projects using MSAL token
class MSALTokenCredential(TokenCredential):
    def __init__(self, access_token: str, expires_at: int = None):
        self._access_token = access_token
        self._expires_at = expires_at
    
    async def get_token(self, *scopes, **kwargs) -> AccessToken:
        # Use the access token from MSAL authentication with real expiration
        return AccessToken(self._access_token, self._expires_at or 0)

# Custom Event Handler (based on MyEventHandler from main project)
class StreamlitEventHandler(AsyncAgentEventHandler[str]):
    def __init__(self):
        super().__init__()
        self.response_content = ""
        self.annotations = []
        
    async def on_message_delta(self, delta: MessageDeltaChunk) -> Optional[str]:
        """Handle streaming message deltas"""
        if hasattr(delta, 'text') and delta.text:
            self.response_content += delta.text
            return delta.text
        return None

    async def on_thread_message(self, message: ThreadMessage) -> Optional[str]:
        """Handle completed thread messages with annotations"""
        try:
            if message.status != "completed":
                return None
                
            if message.text_messages:
                content = message.text_messages[0].text.value
                
                # Handle annotations (same logic as main project)
                annotations = []
                
                # File citation annotations
                for annotation in message.file_citation_annotations:
                    annotation_dict = annotation.as_dict()
                    annotations.append({
                        "type": "file_citation",
                        "file_name": annotation_dict.get("file_citation", {}).get("file_id", "Unknown"),
                        "content": annotation_dict
                    })
                
                # URL citation annotations  
                for url_annotation in message.url_citation_annotations:
                    annotation_dict = url_annotation.as_dict()
                    annotations.append({
                        "type": "url_citation", 
                        "file_name": annotation_dict.get("url_citation", {}).get("title", "Unknown"),
                        "content": annotation_dict
                    })
                
                self.annotations = annotations
                return content
                
        except Exception as e:
            logger.error(f"Error in event handler: {e}")
            return None

    async def on_thread_run(self, run: ThreadRun) -> Optional[str]:
        """Handle thread run status updates"""
        logger.info(f"Thread run status: {run.status}")
        if run.status == "failed":
            return f"Error: {run.last_error}"
        return None

    async def on_error(self, data: str) -> Optional[str]:
        """Handle errors"""
        logger.error(f"Event handler error: {data}")
        return None

    async def on_done(self) -> Optional[str]:
        """Handle completion"""
        logger.info("Event handler done")
        return None

    async def on_run_step(self, step: RunStep) -> Optional[str]:
        """Handle run steps"""
        logger.info(f"Step {step.get('id', 'unknown')} status: {step.get('status', 'unknown')}")
        return None

# Async function to handle chat (based on main project's chat endpoint)
async def handle_chat(ai_project: AIProjectClient, agent_id: str, thread_id: str, user_message: str):
    """Handle chat interaction (same pattern as main project)"""
    try:
        agent_client = ai_project.agents
        
        # Create user message in thread
        message = await agent_client.messages.create(
            thread_id=thread_id,
            role="user", 
            content=user_message
        )
        logger.info(f"Created message, message ID: {message.id}")
        
        # Create event handler
        event_handler = StreamlitEventHandler()
        
        # Stream the response (same as main project's get_result function)
        response_content = ""
        annotations = []
        
        async with await agent_client.runs.stream(
            thread_id=thread_id,
            agent_id=agent_id,
            event_handler=event_handler,
        ) as stream:
            logger.info("Successfully created stream; starting to process events")
            async for event in stream:
                _, _, event_func_return_val = event
                if event_func_return_val:
                    logger.debug(f"Received event: {event_func_return_val}")
                    response_content += event_func_return_val
                    
            # Get final annotations from event handler
            annotations = event_handler.annotations
            
        # If no response content from streaming, poll for completion
        if not response_content:
            logger.info("No streaming response, polling for completion...")
            max_attempts = 60  # 60 seconds timeout
            attempt = 0
            
            while attempt < max_attempts:
                # Get the latest run status
                runs = await agent_client.runs.list(thread_id=thread_id)
                latest_run = None
                for run in runs:
                    if run.agent_id == agent_id:
                        latest_run = run
                        break
                
                if latest_run:
                    logger.info(f"Run status: {latest_run.status}")
                    
                    if latest_run.status == "completed":
                        # Get the latest messages to find the assistant's response
                        messages = await agent_client.messages.list(thread_id=thread_id)
                        
                        # Find the assistant's message (should be the latest one with role "assistant")
                        for message in reversed(messages):
                            if message.role == "assistant" and message.text_messages:
                                response_content = message.text_messages[0].text.value
                                
                                # Extract annotations if present
                                if hasattr(message, 'file_citation_annotations'):
                                    for annotation in message.file_citation_annotations:
                                        annotation_dict = annotation.as_dict()
                                        annotations.append({
                                            "type": "file_citation",
                                            "file_name": annotation_dict.get("file_citation", {}).get("file_id", "Unknown"),
                                            "content": annotation_dict
                                        })
                                
                                if hasattr(message, 'url_citation_annotations'):
                                    for url_annotation in message.url_citation_annotations:
                                        annotation_dict = url_annotation.as_dict()
                                        annotations.append({
                                            "type": "url_citation", 
                                            "file_name": annotation_dict.get("url_citation", {}).get("title", "Unknown"),
                                            "content": annotation_dict
                                        })
                                break
                        break
                    elif latest_run.status == "failed":
                        error_msg = getattr(latest_run, 'last_error', 'Unknown error')
                        raise Exception(f"Run failed: {error_msg}")
                    elif latest_run.status in ["cancelled", "expired"]:
                        raise Exception(f"Run {latest_run.status}")
                
                # Wait 1 second before next poll
                await asyncio.sleep(1)
                attempt += 1
            
            if attempt >= max_attempts:
                raise Exception("Run timed out")
        
        return response_content, annotations
        
    except Exception as e:
        logger.error(f"Error in handle_chat: {e}")
        raise

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
    
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
    
if "agent_id" not in st.session_state:
    st.session_state.agent_id = config["agent_id"]

# Display existing messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        
        # Display annotations if they exist
        if "annotations" in message and message["annotations"]:
            with st.expander("📎 Sources"):
                for annotation in message["annotations"]:
                    st.write(f"**{annotation['file_name']}** ({annotation['type']})")

# Chat input
if prompt := st.chat_input("What is up?"):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                # Check if user is authenticated
                if not auth_data or "accessToken" not in auth_data:
                    st.error("❌ Please sign in to use the chatbot.")
                    pass
                
                # Initialize AI Project Client with MSAL token
                async def process_chat():
                    # Get expiration time from token claims
                    account = auth_data.get('account', {})
                    id_token_claims = account.get('idTokenClaims', {})
                    expires_at = id_token_claims.get('exp', 0)
                    
                    # Try DefaultAzureCredential first (uses environment variables)
                    try:
                        credential = DefaultAzureCredential()
                    except Exception as e:
                        # Fallback to MSAL token
                        credential = MSALTokenCredential(auth_data["accessToken"], expires_at)
                    
                    async with AIProjectClient(
                        config["proj_endpoint"],
                        credential,
                        connection_verify=False  # Disable SSL verification for development
                    ) as ai_project:
                        agent_client = ai_project.agents
                        
                        # Get or create thread (same logic as main project)
                        thread_id = st.session_state.thread_id
                        if not thread_id or st.session_state.agent_id != config["agent_id"]:
                            logger.info("Creating a new thread")
                            thread = await agent_client.threads.create()
                            thread_id = thread.id
                            st.session_state.thread_id = thread_id
                            st.session_state.agent_id = config["agent_id"]
                        else:
                            logger.info(f"Retrieving thread with ID {thread_id}")
                            thread = await agent_client.threads.get(thread_id)
                        
                        # Handle chat
                        response_content, annotations = await handle_chat(
                            ai_project, config["agent_id"], thread_id, prompt
                        )
                        
                        return response_content, annotations
                
                # Run the async function
                response_content, annotations = asyncio.run(process_chat())
                
                # Display response
                st.markdown(response_content)
                
                # Display annotations
                if annotations:
                    with st.expander("📎 Sources"):
                        for annotation in annotations:
                            st.write(f"**{annotation['file_name']}** ({annotation['type']})")
                
                # Store response
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response_content,
                    "annotations": annotations
                })
                
            except Exception as e:
                st.error(f"❌ Error generating response: {e}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": "Sorry, I encountered an error. Please try again."
                })

# Configuration display in sidebar
with st.sidebar:
    st.markdown("---")
    st.markdown("### 🔧 Configuration")
    
    with st.expander("Azure AI Foundry"):
        st.write(f"**Endpoint:** {config['proj_endpoint']}")
        st.write(f"**Agent ID:** {config['agent_id']}")
        st.write(f"**Thread ID:** {st.session_state.thread_id}")