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


class EventParser:
    """Parser for Azure AI Agents streaming events."""
    
    @staticmethod
    def parse_event(event_bytes: bytes) -> Optional[Any]:
        """Parse a single event from bytes."""
        try:
            event_str = event_bytes.decode('utf-8')
            lines = event_str.split('\n')
            
            event_type = None
            data = None
            
            for line in lines:
                if line.startswith('event: '):
                    event_type = line[7:]  # Remove 'event: ' prefix
                elif line.startswith('data: '):
                    data = json.loads(line[6:])  # Remove 'data: ' prefix
            
            if not event_type or not data:
                return None
                
            # Parse specific event types
            if event_type == 'thread.message.delta':
                return EventParser._parse_message_delta(data)
            elif event_type == 'thread.run.created':
                return EventParser._parse_thread_run(data)
            elif event_type == 'thread.run.queued':
                return EventParser._parse_thread_run(data)
            elif event_type == 'thread.run.in_progress':
                return EventParser._parse_thread_run(data)
            elif event_type == 'thread.run.completed':
                return EventParser._parse_thread_run(data)
            elif event_type == 'thread.message.created':
                return EventParser._parse_thread_message(data)
            elif event_type == 'thread.message.in_progress':
                return EventParser._parse_thread_message(data)
            elif event_type == 'thread.message.completed':
                return EventParser._parse_thread_message(data)
            elif event_type == 'done':
                return {'type': 'done', 'data': data}
                
            return None
            
        except Exception as e:
            print(f"Error parsing event: {e}")
            return None
    
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
    def extract_text_from_events(events: Generator[bytes, None, None]) -> Generator[str, None, None]:
        """Extract text from message delta events."""
        for event_bytes in events:
            parsed_event = EventParser.parse_event(event_bytes)
            if isinstance(parsed_event, MessageDeltaEvent):
                yield parsed_event.text_value
