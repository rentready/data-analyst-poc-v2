"""Azure AI Foundry client and event handling."""

import asyncio
import logging
from typing import Optional, Tuple, List, Dict, Any

from azure.ai.projects.aio import AIProjectClient
from azure.ai.agents.models import (
    AsyncAgentEventHandler,
    MessageDeltaChunk,
    ThreadMessage,
    ThreadRun,
    RunStep
)
from azure.core.credentials import TokenCredential
from .constants import (
    MAX_POLL_ATTEMPTS, POLL_INTERVAL_SECONDS, RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED, RUN_STATUS_CANCELLED, RUN_STATUS_EXPIRED,
    FILE_CITATION_TYPE, URL_CITATION_TYPE, ASSISTANT_ROLE
)

logger = logging.getLogger(__name__)


class StreamlitEventHandler(AsyncAgentEventHandler[str]):
    """Custom Event Handler for Streamlit chatbot."""
    
    def __init__(self):
        super().__init__()
        self.response_content = ""
        self.annotations = []
        
    async def on_message_delta(self, delta: MessageDeltaChunk) -> Optional[str]:
        """Handle streaming message deltas."""
        if hasattr(delta, 'text') and delta.text:
            self.response_content += delta.text
            return delta.text
        return None

    async def on_thread_message(self, message: ThreadMessage) -> Optional[str]:
        """Handle completed thread messages with annotations."""
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
                        "type": FILE_CITATION_TYPE,
                        "file_name": annotation_dict.get("file_citation", {}).get("file_id", "Unknown"),
                        "content": annotation_dict
                    })
                
                # URL citation annotations  
                for url_annotation in message.url_citation_annotations:
                    annotation_dict = url_annotation.as_dict()
                    annotations.append({
                        "type": URL_CITATION_TYPE, 
                        "file_name": annotation_dict.get("url_citation", {}).get("title", "Unknown"),
                        "content": annotation_dict
                    })
                
                self.annotations = annotations
                return content
                
        except Exception as e:
            logger.error(f"Error in event handler: {e}")
            return None

    async def on_thread_run(self, run: ThreadRun) -> Optional[str]:
        """Handle thread run status updates."""
        logger.info(f"Thread run status: {run.status}")
        if run.status == RUN_STATUS_FAILED:
            return f"Error: {run.last_error}"
        return None

    async def on_error(self, data: str) -> Optional[str]:
        """Handle errors."""
        logger.error(f"Event handler error: {data}")
        return None

    async def on_done(self) -> Optional[str]:
        """Handle completion."""
        logger.info("Event handler done")
        return None

    async def on_run_step(self, step: RunStep) -> Optional[str]:
        """Handle run steps."""
        logger.info(f"Step {step.get('id', 'unknown')} status: {step.get('status', 'unknown')}")
        return None


class AzureAIClient:
    """Azure AI Foundry client wrapper."""
    
    def __init__(self, endpoint: str, credential: TokenCredential):
        self.endpoint = endpoint
        self.credential = credential
    
    async def __aenter__(self):
        self.client = AIProjectClient(
            self.endpoint,
            self.credential,
            connection_verify=False  # Disable SSL verification for development
        )
        return self.client
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.__aexit__(exc_type, exc_val, exc_tb)


async def handle_chat(
    ai_project: AIProjectClient, 
    agent_id: str, 
    thread_id: str, 
    user_message: str
) -> Tuple[str, List[Dict[str, Any]]]:
    """Handle chat interaction.
    
    Args:
        ai_project: Azure AI Project client
        agent_id: Agent ID
        thread_id: Thread ID
        user_message: User's message
        
    Returns:
        Tuple of (response_content, annotations)
    """
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
        
        # Stream the response
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
            response_content, annotations = await _poll_for_completion(
                agent_client, agent_id, thread_id
            )
        
        return response_content, annotations
        
    except Exception as e:
        logger.error(f"Error in handle_chat: {e}")
        raise


async def _poll_for_completion(
    agent_client, 
    agent_id: str, 
    thread_id: str
) -> Tuple[str, List[Dict[str, Any]]]:
    """Poll for run completion when streaming doesn't work.
    
    Args:
        agent_client: Agent client
        agent_id: Agent ID
        thread_id: Thread ID
        
    Returns:
        Tuple of (response_content, annotations)
    """
    max_attempts = MAX_POLL_ATTEMPTS
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
            
            if latest_run.status == RUN_STATUS_COMPLETED:
                # Get the latest messages to find the assistant's response
                messages = await agent_client.messages.list(thread_id=thread_id)
                
                # Find the assistant's message (should be the latest one with role "assistant")
                for message in reversed(messages):
                    if message.role == ASSISTANT_ROLE and message.text_messages:
                        response_content = message.text_messages[0].text.value
                        
                        # Extract annotations if present
                        annotations = []
                        if hasattr(message, 'file_citation_annotations'):
                            for annotation in message.file_citation_annotations:
                                annotation_dict = annotation.as_dict()
                                annotations.append({
                                    "type": FILE_CITATION_TYPE,
                                    "file_name": annotation_dict.get("file_citation", {}).get("file_id", "Unknown"),
                                    "content": annotation_dict
                                })
                        
                        if hasattr(message, 'url_citation_annotations'):
                            for url_annotation in message.url_citation_annotations:
                                annotation_dict = url_annotation.as_dict()
                                annotations.append({
                                    "type": URL_CITATION_TYPE, 
                                    "file_name": annotation_dict.get("url_citation", {}).get("title", "Unknown"),
                                    "content": annotation_dict
                                })
                        return response_content, annotations
                break
            elif latest_run.status == RUN_STATUS_FAILED:
                error_msg = getattr(latest_run, 'last_error', 'Unknown error')
                raise Exception(f"Run failed: {error_msg}")
            elif latest_run.status in [RUN_STATUS_CANCELLED, RUN_STATUS_EXPIRED]:
                raise Exception(f"Run {latest_run.status}")
        
        # Wait before next poll
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        attempt += 1
    
    if attempt >= max_attempts:
        raise Exception("Run timed out")
    
    return "", []


async def get_or_create_thread(agent_client, thread_id: Optional[str], agent_id: str) -> str:
    """Get existing thread or create a new one.
    
    Args:
        agent_client: Agent client
        thread_id: Existing thread ID (if any)
        agent_id: Agent ID
        
    Returns:
        Thread ID
    """
    if not thread_id:
        logger.info("Creating a new thread")
        thread = await agent_client.threads.create()
        return thread.id
    else:
        logger.info(f"Retrieving thread with ID {thread_id}")
        thread = await agent_client.threads.get(thread_id)
        return thread.id
