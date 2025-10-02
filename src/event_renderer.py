"""Event renderer - handles UI display for run events."""

import streamlit as st
import json
import logging
import time
from typing import Optional, Callable
from .run_events import (
    RunEvent, MessageEvent, ToolCallEvent, ToolCallsStepEvent,
    RequiresApprovalEvent, RunCompletedEvent, ErrorEvent
)

logger = logging.getLogger(__name__)


def parse_tool_output(output: Optional[str]) -> tuple[bool, any]:
    """
    Parse tool output - try JSON first, fallback to text.
    Returns: (is_json, parsed_data)
    """
    if not output:
        return False, None
    
    try:
        # Try to extract JSON after "TOOL RESULT:" marker
        if 'TOOL RESULT:' in output:
            json_part = output.split('TOOL RESULT:')[1].strip()
            result = json.loads(json_part)
            return True, result
        else:
            # Try direct JSON parse
            result = json.loads(output)
            return True, result
    except:
        # Return as text
        return False, output


class EventRenderer:
    """Renders run events to Streamlit UI."""
    
    @staticmethod
    def render(event: RunEvent):
        """Render event to UI."""
        if isinstance(event, MessageEvent):
            EventRenderer.render_message(event)
        
        elif isinstance(event, ToolCallsStepEvent):
            EventRenderer.render_tool_calls_step(event)
        
        elif isinstance(event, RequiresApprovalEvent):
            EventRenderer.render_approval_request(event)
        
        elif isinstance(event, RunCompletedEvent):
            EventRenderer.render_completion(event)
        
        elif isinstance(event, ErrorEvent):
            EventRenderer.render_error(event)
        
        else:
            logger.warning(f"Unknown event type: {type(event)}")
    
    @staticmethod
    def render_message(event: MessageEvent):
        """Render assistant message (plain, for history)."""
        st.markdown(event.content)
    
    @staticmethod
    def render_message_with_typing(event: MessageEvent):
        """Render assistant message with typewriter effect (for new messages)."""

        if not isinstance(event, MessageEvent):
            return
        
        placeholder = st.empty()
        displayed_text = ""
        
        for char in event.content:
            displayed_text += char
            placeholder.markdown(displayed_text + "▌")  # Add cursor
            time.sleep(0.005)
        
        # Clear placeholder and render final text normally
        placeholder.empty()
        st.markdown(event.content)
    
    @staticmethod
    def render_tool_calls_step(event: ToolCallsStepEvent):
        """Render tool calls step with all tool calls."""
        for tool_call in event.tool_calls:
            EventRenderer._render_single_tool_call(tool_call)
    
    @staticmethod
    def _render_single_tool_call(tool_call: ToolCallEvent):
        """Render a single tool call."""
        # Tool header with status
        status_emoji = {
            "in_progress": "🔄",
            "completed": "✅",
            "failed": "❌"
        }
        emoji = status_emoji.get(tool_call.status, "❓")
        
        tool_label = tool_call.tool_name
        if tool_call.server_label:
            tool_label = f"{tool_call.tool_name} ({tool_call.server_label})"
        
        with st.status(f"{emoji} {tool_label}"):
            # Arguments
            if tool_call.arguments:
                with st.expander("📝 Arguments", expanded=False):
                    st.json(tool_call.arguments)
            
            # Output/Result
            if tool_call.output:
                is_json, parsed = parse_tool_output(tool_call.output)
                
                if is_json:
                    EventRenderer._render_structured_output(parsed)
                else:
                    with st.expander("📤 Output", expanded=True):
                        st.text(parsed)
            else:
                st.info("⏳ No output yet...")
    
    @staticmethod
    def _render_structured_output(result):
        """Render structured JSON output."""
        # Show success/error status
        if isinstance(result, dict):
            if result.get('success') is True:
                st.success("✅ Tool executed successfully")
                if 'count' in result:
                    st.info(f"📊 Found {result['count']} results")
            elif result.get('success') is False:
                st.error("❌ Tool execution failed")
                if 'error' in result:
                    st.error(f"**Error:** {result['error']}")
        
        # Always show raw data
        with st.expander("📊 Result Data", expanded=True):
            if isinstance(result, dict):
                st.json(result)
            else:
                st.markdown(str(result))
    
    @staticmethod
    def render_approval_request(event: RequiresApprovalEvent, 
                               on_approve: callable = None, 
                               on_deny: callable = None):
        """Render tool approval UI with buttons."""
        st.warning("🔧 MCP Tool requires approval")
        
        for i, tool_call in enumerate(event.tool_calls):
            with st.expander(f"Tool: {tool_call.name} ({tool_call.server_label})", expanded=True):
                st.write(f"**Tool ID:** {tool_call.id}")
                st.write(f"**Type:** {tool_call.type}")
                st.write(f"**Server:** {tool_call.server_label}")
                
                if tool_call.arguments:
                    st.write("**Arguments:**")
                    st.json(tool_call.arguments)
        
        # Render approval buttons if callbacks provided
        if on_approve and on_deny:
            render_approval_buttons(event, on_approve, on_deny)
    
    @staticmethod
    def render_completion(event: RunCompletedEvent):
        """Render run completion - just logging."""
        logger.info(f"✅ Run {event.run_id} completed")
    
    @staticmethod
    def render_error(event: ErrorEvent):
        """Render error event."""
        st.error(f"❌ Error: {event.error_message}")
        if event.error_code:
            st.caption(f"Error code: {event.error_code}")


def render_approval_buttons(event: RequiresApprovalEvent, 
                           on_approve: Callable, 
                           on_deny: Callable):
    """Render approval buttons separately (for callback handling)."""
    col1, col2 = st.columns(2)
    
    with col1:
        st.button(
            "✅ Approve All",
            key=f"approve_{event.run_id}",
            on_click=on_approve,
            args=(event,)
        )
    
    with col2:
        st.button(
            "❌ Deny All", 
            key=f"deny_{event.run_id}",
            on_click=on_deny,
            args=(event,)
        )


def render_error_buttons(on_retry: Callable, on_cancel: Callable):
    """Render error retry/cancel buttons."""
    col1, col2 = st.columns(2)
    
    with col1:
        st.button(
            "🔄 Retry",
            key="retry_button",
            on_click=on_retry
        )
    
    with col2:
        st.button(
            "❌ Cancel",
            key="cancel_button", 
            on_click=on_cancel
        )

