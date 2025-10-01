"""Run events - abstraction for agent execution events."""

from typing import Optional, Any, Literal
import logging

logger = logging.getLogger(__name__)


class RunEvent:
    """Base class for all run events."""
    
    def __init__(self, event_id: str, event_type: str, is_blocking: bool = False):
        self.event_id = event_id
        self.event_type = event_type
        self.is_blocking = is_blocking
    
    def __hash__(self):
        return hash(self.event_id)
    
    def __eq__(self, other):
        if isinstance(other, RunEvent):
            return self.event_id == other.event_id
        return False


class MessageEvent(RunEvent):
    """Message from assistant - ready to display."""
    
    def __init__(self, message_id: str, content: str):
        super().__init__(
            event_id=f"message_{message_id}",
            event_type="message",
            is_blocking=False
        )
        self.message_id = message_id
        self.content = content


class ToolCallEvent(RunEvent):
    """Tool call - complete with arguments and output."""
    
    def __init__(self, tool_id: str, tool_name: str, tool_type: str, 
                 server_label: Optional[str], arguments: dict, 
                 output: Optional[str], status: str):
        super().__init__(
            event_id=f"tool_{tool_id}",
            event_type="tool_call",
            is_blocking=False
        )
        self.tool_id = tool_id
        self.tool_name = tool_name
        self.tool_type = tool_type
        self.server_label = server_label
        self.arguments = arguments
        self.output = output
        self.status = status


class ToolCallsStepEvent(RunEvent):
    """Step containing multiple tool calls."""
    
    def __init__(self, step_id: str, tool_calls: list[ToolCallEvent], status: str):
        super().__init__(
            event_id=f"step_{step_id}",
            event_type="tool_calls_step",
            is_blocking=False
        )
        self.step_id = step_id
        self.tool_calls = tool_calls
        self.status = status


class RequiresApprovalEvent(RunEvent):
    """Tool approval request - blocks execution until approved/denied."""
    
    def __init__(self, run_id: str, thread_id: str, tool_calls: list[Any]):
        # Include tool call IDs in event_id to handle multiple approval requests per run
        tool_ids = '_'.join(sorted([tc.id for tc in tool_calls]))
        super().__init__(
            event_id=f"approval_{run_id}_{tool_ids}",
            event_type="requires_approval", 
            is_blocking=True
        )
        self.run_id = run_id
        self.thread_id = thread_id
        self.tool_calls = tool_calls


class RunStatusEvent(RunEvent):
    """Run status change event."""
    
    def __init__(self, run_id: str, status: str):
        super().__init__(
            event_id=f"status_{run_id}_{status}",
            event_type="status",
            is_blocking=False
        )
        self.run_id = run_id
        self.status = status


class RunCompletedEvent(RunEvent):
    """Run completed - final event in the stream."""
    
    def __init__(self, run_id: str):
        super().__init__(
            event_id=f"completed_{run_id}",
            event_type="completed",
            is_blocking=False
        )
        self.run_id = run_id


class ErrorEvent(RunEvent):
    """Error occurred during run."""
    
    def __init__(self, error_message: str, error_code: Optional[str] = None):
        super().__init__(
            event_id=f"error_{hash(error_message)}",
            event_type="error",
            is_blocking=False
        )
        self.error_message = error_message
        self.error_code = error_code

