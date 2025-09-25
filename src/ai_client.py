"""Azure AI Foundry client and event handling with MCP support."""

import asyncio
import json
import logging
from typing import Optional, Tuple, List, Dict, Any
import streamlit as st

from azure.ai.projects.aio import AIProjectClient
from azure.ai.agents.models import (
    AsyncAgentEventHandler,
    MessageDeltaChunk,
    ThreadMessage,
    ThreadRun,
    RunStep,
    McpTool
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
    
    def __init__(self, on_tool_status=None):
        super().__init__()
        self.response_content = ""
        self.annotations = []
        self.has_streamed_content = False
        self.on_tool_status = on_tool_status
        self.tool_status_container = None
        
    async def on_message_delta(self, delta: MessageDeltaChunk) -> Optional[str]:
        """Handle streaming message deltas."""
        if hasattr(delta, 'text') and delta.text:
            self.response_content += delta.text
            self.has_streamed_content = True
            return delta.text
        return None

    async def on_thread_message(self, message: ThreadMessage) -> Optional[str]:
        """Handle completed thread messages with annotations."""
        try:
            if message.status != "completed":
                return None
                
            if message.text_messages:
                # Only handle annotations, don't return content to avoid duplication
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
                # Don't return content here to avoid duplication with streaming
                return None
                
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
        step_id = step.get('id', 'unknown')
        step_status = step.get('status', 'unknown')
        step_type = step.get('type', 'unknown')
        
        logger.info(f"Step {step_id} ({step_type}) status: {step_status}")
        
        # Handle tool execution
        if step_type == "tool_calls":
            if step_status == "in_progress":
                self._show_tool_start()
            elif step_status == "completed":
                self._show_tool_completion(step)
            elif step_status == "failed":
                self._show_tool_failure()
        
        return None
    
    def _show_tool_start(self):
        """Show tool execution start."""
        logger.info("🔧 TOOL EXECUTION STARTED")
        if not hasattr(self, 'status_container'):
            self.status_container = st.status("🔧 Executing tool...", expanded=False)
        else:
            self.status_container.update(label="🔧 Executing tool...", state="running")
    
    def _show_tool_completion(self, step):
        """Show tool completion with name and result."""
        logger.info("🔧 TOOL EXECUTION COMPLETED")
        
        try:
            # Extract tool name and result
            step_details = step.step_details
            tool_call = step_details['tool_calls'][0]
            tool_name = tool_call['name']
            output = tool_call.get('output', '')
            
            # Parse result if available
            result = self._parse_tool_result(output)
            count = result.get('count', 0) if result else 0
            
            # Update status
            if hasattr(self, 'status_container'):
                self.status_container.update(
                    label=f"✅ Tool {tool_name} completed: {count} results",
                    state="complete"
                )
                # Show result
                if result:
                    self.status_container.write(result)
                elif output:
                    self.status_container.write(output)
                else:
                    self.status_container.write("Tool completed")
                    
        except Exception as e:
            logger.info(f"🔧 TOOL COMPLETION ERROR: {e}")
            if hasattr(self, 'status_container'):
                self.status_container.update(
                    label="✅ Tool completed",
                    state="complete"
                )
                self.status_container.write("Tool completed")
    
    def _show_tool_failure(self):
        """Show tool execution failure."""
        logger.info("🔧 TOOL EXECUTION FAILED")
        if hasattr(self, 'status_container'):
            self.status_container.update(
                label="❌ Tool execution failed",
                state="error"
            )
            self.status_container.write("Tool execution failed")
    
    def _parse_tool_result(self, output):
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


class AzureAIClient:
    """Azure AI Foundry client wrapper."""
    
    def __init__(self, endpoint: str, credential: TokenCredential):
        self.endpoint = endpoint
        self.credential = credential
    
    async def __aenter__(self):
        self.client = AIProjectClient(
            self.endpoint,
            self.credential
        )
        return self.client
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.__aexit__(exc_type, exc_val, exc_tb)


async def handle_chat(
    ai_project: AIProjectClient, 
    agent_id: str, 
    thread_id: str, 
    user_message: str,
    mcp_token: str = None,
    mcp_config: dict = None,
    on_stream_chunk: callable = None,
    on_tool_status: callable = None
) -> Tuple[str, List[Dict[str, Any]]]:
    """Handle chat interaction.
    
    Args:
        ai_project: Azure AI Project client
        agent_id: Agent ID
        thread_id: Thread ID
        user_message: User's message
        mcp_token: Optional MCP access token for tool resources
        on_stream_chunk: Optional callback function for streaming chunks
        
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
        event_handler = StreamlitEventHandler(on_tool_status=on_tool_status)
        
        # Prepare MCP tool resources if token is available
        tool_resources = None
        if mcp_token:
            # Get server label from config or use default
            server_label = "mcp_server"
            if mcp_config:
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
            logger.info(f"MCP token added to run parameters (token length: {len(mcp_token)})")
        
        # Stream the response
        async with await agent_client.runs.stream(
            thread_id=thread_id,
            agent_id=agent_id,
            event_handler=event_handler,
            tool_resources=tool_resources
        ) as stream:
            logger.info("Successfully created stream; starting to process events")

            async for event in stream:
                _, _, event_func_return_val = event
                if event_func_return_val:
                    logger.debug(f"Received event: {event_func_return_val}")
                    # Content is already accumulated in event_handler.response_content
                    # Call streaming callback if provided
                    if on_stream_chunk:
                        on_stream_chunk(event_func_return_val)
                    
        # Get response content and annotations from event handler
        response_content = event_handler.response_content
        annotations = event_handler.annotations
        
        # If no response content from streaming, poll for completion
        if not event_handler.has_streamed_content:
            logger.info("No streaming response, polling for completion...")
            response_content, annotations = await _poll_for_completion(
                agent_client, agent_id, thread_id, mcp_token
            )
        
        return response_content, annotations
        
    except Exception as e:
        logger.error(f"Error in handle_chat: {e}")
        raise


async def _poll_for_completion(
    agent_client, 
    agent_id: str, 
    thread_id: str,
    mcp_token: str = None
) -> Tuple[str, List[Dict[str, Any]]]:
    """Poll for run completion when streaming doesn't work.
    
    Args:
        agent_client: Agent client
        agent_id: Agent ID
        thread_id: Thread ID
        mcp_token: Optional MCP access token
        
    Returns:
        Tuple of (response_content, annotations)
    """
    max_attempts = MAX_POLL_ATTEMPTS
    attempt = 0
    
    while attempt < max_attempts:
        # Get the latest run status
        runs = agent_client.runs.list(thread_id=thread_id)
        latest_run = None
        async for run in runs:
            if run.agent_id == agent_id:
                latest_run = run
                break
        
        if latest_run:
            logger.info(f"Run status: {latest_run.status}")
            
            if latest_run.status == RUN_STATUS_COMPLETED:
                # Get the latest messages to find the assistant's response
                messages = agent_client.messages.list(thread_id=thread_id)
                
                # Find the assistant's message (should be the latest one with role "assistant")
                messages_list = []
                async for message in messages:
                    messages_list.append(message)
                
                for message in reversed(messages_list):
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
