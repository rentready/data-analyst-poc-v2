"""Event parser for Azure AI Agents streaming events."""

import json
from typing import Optional, Generator, Any
from dataclasses import dataclass


@dataclass
class MessageDeltaEvent:
    """Parsed message delta event."""
    text_value: str
    message_id: str
    index: int
    type: str


@dataclass
class ThreadRunEvent:
    """Parsed thread run event."""
    run_id: str
    status: str
    thread_id: str
    assistant_id: str


@dataclass
class ThreadMessageEvent:
    """Parsed thread message event."""
    message_id: str
    status: str
    role: str
    content: list

@dataclass
class ThreadRunStepFailedEvent:
    """Parsed thread run step failed event."""
    id: str
    status: str
    step_type: str
    run_id: str
    assistant_id: str
    thread_id: str
    error_code: str
    error_message: str

@dataclass
class ThreadRunStepCompletedEvent:
    """Parsed thread run step completed event."""
    id: str
    status: str
    step_type: str
    run_id: str
    assistant_id: str
    thread_id: str

@dataclass
class ThreadRunStepDeltaEvent:
    """Parsed thread run step delta event."""
    id: str
    step_details_type: str
    tool_calls_count: int
    tool_name: str
    tool_type: str
    server_label: str
    has_output: bool
    output: str

@dataclass
class DoneEvent:
    """Parsed done event."""
    type: str
    data: dict


class EventParser:
    """Parser for Azure AI Agents streaming events."""
    
    @staticmethod
    def parse_event(event_bytes: bytes) -> Optional[Any]:
        """Parse a single event from bytes."""
        try:
            event_str = event_bytes.decode('utf-8')
            
            # Split by double newlines to handle multiple events in one chunk
            events = event_str.split('\n\n')
            
            for event in events:
                if not event.strip():
                    continue
                    
                lines = event.strip().split('\n')
                event_type = None
                data = None
                
                for line in lines:
                    if line.startswith('event: '):
                        event_type = line[7:]  # Remove 'event: ' prefix
                    elif line.startswith('data: '):
                        data_str = line[6:]  # Remove 'data: ' prefix
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                
                if event_type and data:
                    # Return the first valid event
                    return EventParser._parse_by_type(event_type, data)
            
            return None
                
        except Exception as e:
            print(f"Error parsing event: {e}")
            return None
    
    @staticmethod
    def _parse_by_type(event_type: str, data: dict) -> Optional[Any]:
        """Parse event by type."""
        if event_type == 'thread.message.delta':
            return EventParser._parse_message_delta(data)
        elif event_type in ['thread.run.created', 'thread.run.queued', 'thread.run.in_progress', 'thread.run.completed']:
            return EventParser._parse_thread_run(data)
        elif event_type in ['thread.message.created', 'thread.message.in_progress', 'thread.message.completed']:
            return EventParser._parse_thread_message(data)
        elif event_type == 'thread.run.step.completed':
            return EventParser._parse_thread_run_step(data)
        elif event_type == 'thread.run.step.delta':
            return EventParser._parse_thread_run_step_delta(data)
        elif event_type == 'thread.run.step.failed':
            return EventParser._parse_thread_run_step_failed(data)
        elif event_type == 'thread.message.delta':
            return EventParser._parse_message_delta(data)
        elif event_type == 'done':
            return DoneEvent(type='done', data=data)
        
        # Return generic event for unknown types
        return {'type': event_type, 'data': data}
    
    @staticmethod
    def _parse_message_delta(data: dict) -> Optional[MessageDeltaEvent]:
        """Parse message delta event."""
        try:
            if 'delta' in data and 'content' in data['delta']:
                for content in data['delta']['content']:
                    if 'text' in content and 'value' in content['text']:
                        return MessageDeltaEvent(
                            text_value=content['text']['value'],
                            message_id=data.get('id', ''),
                            index=content.get('index', 0),
                            type=content.get('type', 'text')
                        )
        except Exception as e:
            print(f"Error parsing message delta: {e}")
        return None
    
    @staticmethod
    def _parse_thread_run(data: dict) -> Optional[ThreadRunEvent]:
        """Parse thread run event."""
        try:
            return ThreadRunEvent(
                run_id=data.get('id', ''),
                status=data.get('status', ''),
                thread_id=data.get('thread_id', ''),
                assistant_id=data.get('assistant_id', '')
            )
        except Exception as e:
            print(f"Error parsing thread run: {e}")
        return None
    
    @staticmethod
    def _parse_thread_message(data: dict) -> Optional[ThreadMessageEvent]:
        """Parse thread message event."""
        try:
            return ThreadMessageEvent(
                message_id=data.get('id', ''),
                status=data.get('status', ''),
                role=data.get('role', ''),
                content=data.get('content', [])
            )
        except Exception as e:
            print(f"Error parsing thread message: {e}")
        return None

    @staticmethod
    def _parse_thread_run_step(data: dict) -> Optional[ThreadRunStepCompletedEvent]:
        """Parse thread run step event."""
        try:
            return ThreadRunStepCompletedEvent(
                id=data.get('id', ''),
                status=data.get('status', ''),
                step_type=data.get('type', ''),
                run_id=data.get('run_id', ''),
                assistant_id=data.get('assistant_id', ''),
                thread_id=data.get('thread_id', '')
            )
        except Exception as e:
            print(f"Error parsing thread run step event: {e}")
            return None

    @staticmethod
    def _parse_thread_run_step_delta(data: dict) -> Optional[ThreadRunStepDeltaEvent]:
        """Parse thread run step delta event (MCP tool execution)."""
        try:
            delta = data.get('delta', {})
            step_details = delta.get('step_details', {})
            tool_calls = step_details.get('tool_calls', []) if step_details else []
            
            # Debug: print the structure we're working with
            print(f"DEBUG: step_details = {step_details}")
            print(f"DEBUG: tool_calls = {tool_calls}")
            
            # Extract tool call information
            tool_name = 'unknown'
            tool_type = 'unknown'
            server_label = 'unknown'
            has_output = False
            output_preview = ''
            
            if tool_calls and len(tool_calls) > 0:
                tool_call = tool_calls[0]  # Usually one tool call
                tool_name = tool_call.get('name', 'unknown')
                tool_type = tool_call.get('type', 'unknown')
                server_label = tool_call.get('server_label', 'unknown')
                has_output = bool(tool_call.get('output'))
                output_preview = tool_call.get('output', '')
            
            return ThreadRunStepDeltaEvent(
                id=data.get('id', ''),
                step_details_type=step_details.get('type') if step_details else '',
                tool_calls_count=len(tool_calls) if tool_calls else 0,
                tool_name=tool_name,
                tool_type=tool_type,
                server_label=server_label,
                has_output=has_output,
                output=output_preview
            )
        except Exception as e:
            print(f"Error parsing thread run step delta event: {e}")
            return None

    @staticmethod
    def _parse_thread_run_step_failed(data: dict) -> Optional[ThreadRunStepFailedEvent]:
        """Parse thread run step failed event."""
        try:
            return ThreadRunStepFailedEvent(
                id=data.get('id', ''),
                status=data.get('status', ''),
                step_type=data.get('type', ''),
                run_id=data.get('run_id', ''),
                assistant_id=data.get('assistant_id', ''),
                thread_id=data.get('thread_id', ''),
                error_code=data.get('last_error', {}).get('code', ''),
                error_message=data.get('last_error', {}).get('message', '')
            )
        except Exception as e:
            print(f"Error parsing thread run step failed event: {e}")
            return None
    
    @staticmethod
    def extract_text_from_events(events: Generator[bytes, None, None]) -> Generator[str, None, None]:
        """Extract text from message delta events."""
        for event_bytes in events:
            parsed_event = EventParser.parse_event(event_bytes)
            if isinstance(parsed_event, MessageDeltaEvent):
                yield parsed_event.text_value
