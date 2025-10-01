"""Run processor - converts polling into event stream."""

import logging
import time
import json
from typing import Generator, Optional
from azure.ai.agents.models import SubmitToolApprovalAction
from .run_events import (
    RunEvent, MessageEvent, ToolCallEvent, ToolCallsStepEvent,
    RequiresApprovalEvent, RunStatusEvent, RunCompletedEvent, ErrorEvent
)

logger = logging.getLogger(__name__)


class RunProcessor:
    """Processes agent run and yields events."""
    
    def __init__(self, agents_client):
        self.agents_client = agents_client
        self.seen_events = set()  # For deduplication
        self.is_blocked = False  # Track if we're waiting for approval
        self.blocked_event = None  # Store blocking event
    
    def unblock(self):
        """Unblock processor after approval is submitted."""
        logger.info(f"🔓 Unblocking processor")
        self.is_blocked = False
        self.blocked_event = None
    
    def poll_run_events(self, thread_id: str, run_id: str, 
                       poll_interval: float = 1.0) -> Generator[RunEvent, None, None]:
        """
        Poll run and yield events as they become ready.
        
        Events are yielded with ALL data loaded (messages fetched, tools complete, etc).
        Blocking events (requires_approval) will stop the stream until handled externally.
        """
        while True:
            try:
                run = self.agents_client.runs.get(thread_id=thread_id, run_id=run_id)
                logger.info(f"Run status: {run.status}")
                
                # Check for approval requirement FIRST (blocks everything)
                if run.status == "requires_action" and isinstance(run.required_action, SubmitToolApprovalAction):
                    event = RequiresApprovalEvent(
                        run_id=run.id,
                        thread_id=thread_id,
                        tool_calls=run.required_action.submit_tool_approval.tool_calls
                    )
                    
                    # Only yield once, then exit
                    if event.event_id not in self.seen_events:
                        self.seen_events.add(event.event_id)
                        self.is_blocked = True
                        self.blocked_event = event
                        logger.info(f"🔒 Yielding blocking event: approval required")
                        yield event
                        # Exit generator - will resume after unblock()
                        return
                    else:
                        # Already seen this approval event, just continue polling
                        # Run will change from requires_action to in_progress after approval is processed
                        logger.info(f"⏭️ Skipping already-seen approval event, continuing polling...")
                        # Don't return - continue to next iteration
                
                # Process steps for in-progress runs
                if run.status in ["in_progress", "queued"]:
                    yield from self._process_steps(thread_id, run_id)
                
                # Terminal states
                if run.status not in ["queued", "in_progress", "requires_action"]:
                    # Final sweep - process any remaining completed steps
                    # This handles race conditions where steps complete after we last polled
                    logger.info(f"🏁 Run finished with status {run.status}, doing final sweep")
                    yield from self._process_steps(thread_id, run_id)
                    
                    # Yield completion event
                    if run.status == "completed":
                        event = RunCompletedEvent(run_id=run.id)
                        if event.event_id not in self.seen_events:
                            self.seen_events.add(event.event_id)
                            logger.info(f"✅ Run completed successfully")
                            yield event
                    elif run.status == "failed":
                        error_msg = getattr(run, 'last_error', {}).get('message', 'Run failed')
                        error_code = getattr(run, 'last_error', {}).get('code', None)
                        logger.error(f"❌ Run failed: {error_msg}")
                        yield ErrorEvent(error_message=error_msg, error_code=error_code)
                    
                    # Exit the polling loop
                    return
                
                time.sleep(poll_interval)
                
            except Exception as e:
                logger.error(f"Error polling run: {e}")
                yield ErrorEvent(error_message=str(e))
                return
    
    def _process_steps(self, thread_id: str, run_id: str) -> Generator[RunEvent, None, None]:
        """Process run steps and yield events."""
        try:
            steps = self.agents_client.run_steps.list(thread_id=thread_id, run_id=run_id, order="asc")
            
            for step in steps:
                step_type = getattr(step, 'type', 'unknown')
                step_status = getattr(step, 'status', 'unknown')
                step_id = getattr(step, 'id', 'unknown')
                
                logger.info(f"🔍 Processing step: {step_id}, type={step_type}, status={step_status}")
                
                # Only process completed steps
                if step_status != "completed":
                    logger.info(f"⏭️ Skipping step {step_id} - not completed (status: {step_status})")
                    continue
                
                if step_type == "tool_calls":
                    event = self._create_tool_calls_event(step)
                    if event:
                        if event.event_id in self.seen_events:
                            logger.info(f"⏭️ Skipping tool calls step {step_id} - already seen")
                        else:
                            # Check if all tool calls have output before yielding
                            all_have_output = all(tc.output for tc in event.tool_calls)
                            if all_have_output:
                                self.seen_events.add(event.event_id)
                                logger.info(f"✅ Yielding tool calls step: {step_id} with {len(event.tool_calls)} tool(s)")
                                yield event
                            else:
                                # Output not ready - STOP processing steps to preserve order
                                # Will retry in next poll iteration
                                logger.info(f"⏳ Tool calls step {step_id} completed but output not ready yet")
                                logger.info(f"🛑 Stopping step processing to preserve order, will retry in next poll")
                                return  # Exit _process_steps, will retry in next while loop iteration
                
                elif step_type == "message_creation":
                    event = self._create_message_event(thread_id, step)
                    if event:
                        if event.event_id in self.seen_events:
                            logger.info(f"⏭️ Skipping message {event.message_id} - already seen")
                        else:
                            self.seen_events.add(event.event_id)
                            logger.info(f"✅ Yielding message: {event.message_id}")
                            yield event
                        
        except Exception as e:
            logger.error(f"Error processing steps: {e}")
    
    def _create_tool_calls_event(self, step) -> Optional[ToolCallsStepEvent]:
        """Create tool calls step event with all data loaded."""
        try:
            step_details = getattr(step, 'step_details', {})
            if 'tool_calls' not in step_details:
                logger.warning(f"Step {step.id} has no tool_calls in step_details")
                return None
            
            tool_calls_raw = step_details['tool_calls']
            logger.info(f"🔧 Creating tool calls event for step {step.id} with {len(tool_calls_raw)} tool call(s)")
            
            tool_call_events = []
            for idx, tool_call in enumerate(tool_calls_raw):
                tool_id = tool_call.get('id', 'unknown')
                tool_name = tool_call.get('name', 'Unknown Tool')
                tool_type = tool_call.get('type', 'unknown')
                server_label = tool_call.get('server_label')
                
                logger.info(f"  Tool {idx+1}: {tool_name} (type={tool_type}, server={server_label})")
                
                # Parse arguments
                arguments = {}
                if 'arguments' in tool_call:
                    try:
                        arguments = json.loads(tool_call['arguments']) if isinstance(tool_call['arguments'], str) else tool_call['arguments']
                    except:
                        arguments = {'raw': tool_call['arguments']}
                
                output = tool_call.get('output')
                has_output = output is not None and output != ""
                logger.info(f"    Has output: {has_output}")
                
                tool_event = ToolCallEvent(
                    tool_id=tool_id,
                    tool_name=tool_name,
                    tool_type=tool_type,
                    server_label=server_label,
                    arguments=arguments,
                    output=output,
                    status="completed"
                )
                tool_call_events.append(tool_event)
            
            return ToolCallsStepEvent(
                step_id=step.id,
                tool_calls=tool_call_events,
                status="completed"
            )
            
        except Exception as e:
            logger.error(f"Error creating tool calls event: {e}")
            return None
    
    def _create_message_event(self, thread_id: str, step) -> Optional[MessageEvent]:
        """Create message event - FETCH the actual message content."""
        try:
            step_details = getattr(step, 'step_details', {})
            if 'message_creation' not in step_details:
                return None
            
            message_id = step_details['message_creation'].get('message_id')
            if not message_id:
                return None
            
            # FETCH the actual message content
            message = self.agents_client.messages.get(thread_id=thread_id, message_id=message_id)
            
            if message.text_messages:
                content = message.text_messages[-1].text.value
                return MessageEvent(message_id=message_id, content=content)
            
            return None
            
        except Exception as e:
            logger.error(f"Error creating message event: {e}")
            return None

