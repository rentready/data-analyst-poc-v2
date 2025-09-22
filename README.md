# 🤖 Azure AI Foundry Agent Chatbot

A Streamlit app that demonstrates how to build a chatbot using Azure AI Foundry Agent with support for Model Context Protocol (MCP).

## Features

- Powered by Azure AI Foundry Agent
- Support for both API key and Azure AD authentication
- Configurable via Streamlit secrets
- Ready for MCP integration

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

   Edit `.streamlit/secrets.toml` and add your Azure AI Foundry configuration:
   ```toml
   [azure_ai_foundry]
   proj_endpoint = "your-azure-ai-foundry-endpoint"
   api_key = "your-azure-ai-foundry-api-key"
   agent_id = "your-agent-id"
   ```

3. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```

## Authentication

The app uses API key authentication via `AzureKeyCredential`. You need to provide your Azure AI Foundry API key in the secrets configuration.

## Configuration

The app requires the following configuration in `.streamlit/secrets.toml`:

```toml
[azure_ai_foundry]
proj_endpoint = "https://your-project.services.ai.azure.com/api/projects/your-project"
api_key = "your-api-key-here"
agent_id = "asst_your_agent_id"
```

## Learn More

- [Azure AI Foundry Documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/)
- [Model Context Protocol Support](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/model-context-protocol)
