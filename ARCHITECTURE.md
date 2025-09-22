# Architecture Overview

This document describes the modular architecture of the Azure AI Foundry Chatbot application.

## Project Structure

```
streamlit-chatbot-sample/
├── src/                          # Source code modules
│   ├── __init__.py              # Package initialization
│   ├── config.py                # Configuration management
│   ├── auth.py                  # Authentication handling
│   ├── ai_client.py             # Azure AI client and event handling
│   ├── ui.py                    # UI components
│   ├── utils.py                 # Utility functions
│   └── constants.py             # Application constants
├── streamlit_app.py             # Main Streamlit application
├── requirements.txt             # Python dependencies
├── .streamlit/
│   ├── secrets.toml.example     # Configuration template
│   └── secrets.toml             # Actual configuration (not in git)
└── README.md                    # Project documentation
```

## Module Responsibilities

### `src/config.py`
- **Purpose**: Configuration management and validation
- **Key Functions**:
  - `get_config()`: Load and validate Azure AI Foundry configuration
  - `setup_environment_variables()`: Set up environment variables for authentication
  - `get_auth_config()`: Get authentication configuration from environment

### `src/auth.py`
- **Purpose**: Authentication and credential management
- **Key Classes**:
  - `MSALTokenCredential`: Custom token credential for MSAL tokens
- **Key Functions**:
  - `initialize_msal_auth()`: Initialize MSAL authentication UI
  - `get_credential()`: Get appropriate credential (DefaultAzureCredential or MSAL)
  - `is_authenticated()`: Check authentication status

### `src/ai_client.py`
- **Purpose**: Azure AI Foundry client interaction and event handling
- **Key Classes**:
  - `StreamlitEventHandler`: Custom event handler for streaming responses
  - `AzureAIClient`: Context manager for AI client
- **Key Functions**:
  - `handle_chat()`: Main chat interaction logic
  - `get_or_create_thread()`: Thread management
  - `_poll_for_completion()`: Polling for completion when streaming fails

### `src/ui.py`
- **Purpose**: UI components and rendering functions
- **Key Functions**:
  - `render_header()`: Render main header and description
  - `render_messages()`: Render chat messages
  - `render_annotations()`: Render source annotations

### `src/constants.py`
- **Purpose**: Application constants and configuration keys
- **Contains**: All string constants, configuration keys, and magic numbers

### `src/utils.py`
- **Purpose**: Utility functions
- **Key Functions**:
  - `setup_logging()`: Configure logging
  - `get_logger()`: Get logger instance
  - `safe_get()`: Safe dictionary access

### `streamlit_app.py`
- **Purpose**: Main application entry point
- **Key Functions**:
  - `main()`: Main application logic
  - `initialize_session_state()`: Initialize Streamlit session state
  - `process_chat_message()`: Process individual chat messages

## Design Principles

### 1. Separation of Concerns
Each module has a single, well-defined responsibility:
- Configuration management is separate from authentication
- UI rendering is separate from business logic
- Azure AI client logic is isolated from Streamlit-specific code

### 2. Dependency Injection
- Configuration is injected into functions rather than accessed globally
- Credentials are passed as parameters rather than created within functions

### 3. Error Handling
- Each module handles its own errors appropriately
- Errors are logged and propagated up the call stack
- User-friendly error messages are displayed in the UI

### 4. Type Hints
- All functions include proper type hints for better code maintainability
- Return types are clearly specified

### 5. Constants Management
- All magic strings and numbers are defined in `constants.py`
- This makes the code more maintainable and reduces typos

## Benefits of This Architecture

1. **Maintainability**: Each module can be modified independently
2. **Testability**: Individual modules can be unit tested in isolation
3. **Reusability**: Modules can be reused in other applications
4. **Readability**: Code is organized logically and easy to understand
5. **Scalability**: New features can be added without affecting existing code

## Adding New Features

When adding new features:

1. **Identify the appropriate module** based on the feature's responsibility
2. **Add constants** to `constants.py` if needed
3. **Update type hints** for any new functions or classes
4. **Add error handling** and logging as appropriate
5. **Update documentation** in this file if the architecture changes

## Configuration

The application uses a layered configuration approach:

1. **Streamlit Secrets**: Primary configuration source
2. **Environment Variables**: For authentication credentials
3. **Constants**: For application-wide settings

This allows for flexible deployment across different environments while maintaining security.
