# 🤖 Azure AI Foundry Agent Chatbot

A Streamlit application demonstrating how to build a chatbot using Azure AI Foundry Agent with full Model Context Protocol (MCP) support.

## Features

- Powered by Azure AI Foundry Agent
- Azure AD authentication (MSAL)
- Model Context Protocol (MCP) integration with **tool approval workflow**
- **Configurable tool approval** - enable/disable approval requirements
- Real-time event processing (messages, tool calls, approvals)
- Polling-based architecture for reliability
- Clean event-driven design with proper sequencing
- Configurable via Streamlit secrets

## Design Decisions

### Polling-based Architecture

This application uses a **polling mechanism** instead of real-time streaming for the following reasons:

1. **Stream Limitations**: Azure AI Foundry's streaming API has a critical limitation - when the stream stops (e.g., for tool approval), it cannot be resumed. This makes it unsuitable for interactive tool approval workflows.

2. **MCP Tool Approval**: The application demonstrates the full **MCP tool approval workflow**, which requires:
   - Agent requests permission to execute a tool
   - User approves/denies the request
   - Execution continues after approval
   
   Real-time streaming cannot handle this pause-and-resume pattern.

3. **Platform Issues**: At the time of development, issues with Azure Search integration and MCP streaming were reported, making polling a more reliable approach.

4. **Reliability**: Polling provides a robust, predictable event flow that works consistently across all scenarios including tool approvals, multiple tool calls, and error handling.

The polling implementation still provides real-time user experience while maintaining reliability and supporting the full tool approval workflow.

## Prerequisites

- Azure AI Foundry account and agent
- Python 3.8 or higher

## Setup

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Configure your Azure AI Foundry settings

   Copy the example secrets file and update it with your configuration:
   ```
   $ cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```

   Edit `.streamlit/secrets.toml` and add your configuration:
   ```toml
   # Azure AI Foundry Configuration
   [azure_ai_foundry]
   proj_endpoint = "https://your-ai-foundry-endpoint.cognitiveservices.azure.com/"
   agent_id = "your-agent-id"

   # Environment Variables (for authentication)
   [env]
   AZURE_CLIENT_ID = "your-client-id"
   AZURE_CLIENT_SECRET = "your-client-secret"
   AZURE_TENANT_ID = "your-tenant-id"

   # MCP Configuration (optional)
   [mcp]
   mcp_client_id = "your-mcp-client-id"
   mcp_client_secret = "your-mcp-client-secret"
   ```

3. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```

## Authentication

The app supports Azure AD authentication via MSAL. You need to provide your Azure credentials in the secrets configuration.

## MCP Integration

The app includes support for Model Context Protocol (MCP) integration:

### Features
- Automatic MCP token acquisition using client credentials flow
- Integration with Azure AI Foundry Agent using McpTool class
- Real-time token status display
- Automatic token injection into agent runs

### Setup
1. Configure MCP settings in your `secrets.toml` file (see configuration section above)
2. The app will automatically attempt to obtain an MCP access token on startup
3. If successful, the token will be automatically used in all agent runs

### How it works
When you have a valid MCP token, the app will:
1. Automatically inject the token into every agent run using the `McpTool` class
2. Display the token status and configuration in the UI
3. Enable the agent to use MCP tools with proper authentication

## Tool Approval Settings

The application includes a **configurable tool approval system** that allows you to control whether tool calls require manual approval:

### Approval Modes

- **🔒 Approval Required (Default)**: Each tool call requires explicit user approval before execution
- **🔓 No Approval**: Tool calls are executed automatically without user intervention

### Configuration

You can toggle the approval mode using the sidebar checkbox:
- **"Require tool approval"** - Check this to require approval for each tool call
- **Uncheck** to allow automatic tool execution

This setting is applied when the MCP tool is initialized and affects all subsequent tool calls in the session.

## Configuration

The app requires the following configuration in `.streamlit/secrets.toml`:

### Required Configuration
```toml
[azure_ai_foundry]
proj_endpoint = "https://your-ai-foundry-endpoint.cognitiveservices.azure.com/"
agent_id = "your-agent-id"

[env]
AZURE_CLIENT_ID = "your-client-id"
AZURE_CLIENT_SECRET = "your-client-secret"
AZURE_TENANT_ID = "your-tenant-id"
```

### Optional MCP Configuration
```toml
[mcp]
mcp_client_id = "your-mcp-client-id"
mcp_client_secret = "your-mcp-client-secret"
```

**Note**: MCP uses the same `AZURE_TENANT_ID` from the `[env]` section. The token endpoint is automatically generated as `https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/token`.

**Note**: If MCP configuration is not provided, the app will work normally but without MCP functionality.

## Learn More

- [Azure AI Foundry Documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/)
- [Model Context Protocol Support](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/model-context-protocol)
