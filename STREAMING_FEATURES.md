# Streaming Features

This document describes the streaming and typing effect features implemented in the Azure AI Foundry Chatbot.

## Features Implemented

### 1. Real-time Streaming
- **StreamingDisplay Class**: Handles real-time text display with typing effect
- **Callback System**: AI client calls back to UI for each text chunk
- **Live Updates**: Text appears character by character as it's generated

### 2. Typing Effect
- **Character-by-character display**: Each character appears with a small delay
- **Cursor indicator**: Shows a blinking cursor (▌) while typing
- **Configurable delay**: Typing speed can be adjusted via `DEFAULT_TYPING_DELAY` constant

### 3. Architecture Changes

#### AI Client (`src/ai_client.py`)
- Added `on_stream_chunk` callback parameter to `handle_chat()`
- Modified streaming logic to call callback for each chunk
- Maintains backward compatibility with non-streaming usage

#### UI Components (`src/ui.py`)
- **StreamingDisplay Class**: New class for handling streaming text display
- **render_typing_effect()**: Function for static typing effect
- **Configurable typing delay**: Uses constants for consistent behavior

#### Main Application (`streamlit_app.py`)
- Integrated streaming display into chat flow
- Removed spinner in favor of live typing effect
- Maintains error handling and annotation display

## Usage

### Basic Streaming
```python
# Create streaming display
streaming_display = StreamingDisplay()

# Define callback
def on_chunk(chunk: str):
    streaming_display.add_chunk(chunk)

# Process with streaming
response_content, annotations = await process_chat_message(
    config, auth_data, prompt, on_chunk
)

# Finalize display
streaming_display.finalize()
```

### Custom Typing Speed
```python
# Faster typing (0.01 seconds per character)
streaming_display = StreamingDisplay(typing_delay=0.01)

# Slower typing (0.05 seconds per character)
streaming_display = StreamingDisplay(typing_delay=0.05)
```

## Configuration

### Constants (`src/constants.py`)
- `DEFAULT_TYPING_DELAY = 0.02`: Default delay between characters (20ms)

### Customization
You can adjust the typing speed by:
1. Modifying `DEFAULT_TYPING_DELAY` in constants
2. Passing custom `typing_delay` to `StreamingDisplay`
3. Setting different delays for different use cases

## Benefits

1. **Better UX**: Users see text appearing in real-time, like a real conversation
2. **Engaging**: Typing effect makes the interaction feel more natural
3. **Responsive**: No waiting for complete response before seeing anything
4. **Configurable**: Typing speed can be adjusted based on preferences
5. **Backward Compatible**: Works with existing polling fallback system

## Technical Details

### Streaming Flow
1. User sends message
2. AI client starts streaming response
3. Each chunk triggers `on_stream_chunk` callback
4. UI displays chunk with typing effect
5. Process continues until complete
6. Final display removes cursor

### Fallback Handling
- If streaming fails, falls back to polling system
- Maintains same user experience
- No breaking changes to existing functionality

### Performance
- Minimal overhead for typing effect
- Efficient chunk processing
- Responsive UI updates
