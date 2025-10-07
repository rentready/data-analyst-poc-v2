"""Agent manager - handles Azure AI Agent operations."""

import logging
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import McpTool, ToolApproval, RequiredMcpToolCall
from .run_events import RequiresApprovalEvent

logger = logging.getLogger(__name__)


class AgentManager:
    """Manages Azure AI Agent operations including MCP setup and approvals."""
    
    def __init__(self, project_endpoint: str, agent_id: str, mcp_config: dict, mcp_token: str, thread_id: str = None):
        self.project_endpoint = project_endpoint
        self.agent_id = agent_id
        self.mcp_config = mcp_config
        self.mcp_token = mcp_token
        
        # Initialize clients
        self.client = AIProjectClient(project_endpoint, DefaultAzureCredential())
        self.agents_client = self.client.agents
        
        # Setup MCP tool
        self.mcp_tool = self._setup_mcp_tool()
        self.thread_id = self.create_thread() if thread_id is None else thread_id
    
    def _setup_mcp_tool(self) -> McpTool:
        """Setup MCP tool with authorization."""
        server_label = self.mcp_config.get("mcp_server_label", "mcp_server")
        
        mcp_tool = McpTool(
            server_label=server_label,
            server_url="",  # URL will be set by agent configuration
            allowed_tools=[]  # Allow all tools
        )
        
        # Update headers with authorization token
        mcp_tool.update_headers("authorization", f"bearer {self.mcp_token}")
        
        return mcp_tool
    
    def create_run(self, thread_id: str, message: str) -> str:
        """Create a run and return run_id."""
        # Create user message
        self.agents_client.messages.create(thread_id=thread_id, role="user", content=message)
        
        # Get tool resources if MCP is available
        tool_resources = []
        if self.mcp_config and self.mcp_token:
            try:
                tool_resources = self.mcp_tool.resources
                logger.info(f"MCP tool initialized with {len(tool_resources)} resources")
            except Exception as e:
                logger.error(f"Failed to initialize MCP tool: {e}")
        
        # Create run with MCP headers
        headers = {}
        if self.mcp_token:
            headers["Authorization"] = f"Bearer {self.mcp_token}"
        
        run = self.agents_client.runs.create(
            thread_id=thread_id,
            agent_id=self.agent_id,
            instructions="You are a helpful assistant, you will respond to the user's message and you will use the tools provided to you to help the user. You will justify what tools you are going to use before requesting them.",
            headers=headers,
            tool_resources=tool_resources
        )
        
        logger.info(f"✅ Created run: {run.id}")
        return run.id
    
    def submit_approvals(self, event: RequiresApprovalEvent, approved: bool) -> bool:
        """Submit tool approvals to Azure AI Foundry."""
        try:
            tool_approvals = []
            for tool_call in event.tool_calls:
                if isinstance(tool_call, RequiredMcpToolCall):
                    try:
                        tool_approvals.append(
                            ToolApproval(
                                tool_call_id=tool_call.id,
                                approve=approved,
                                headers=self.mcp_tool.headers,
                            )
                        )
                    except Exception as e:
                        logger.error(f"Error creating approval for {tool_call.id}: {e}")
            
            if tool_approvals:
                logger.info(f"Submitting {len(tool_approvals)} tool approvals (approved={approved})")
                self.agents_client.runs.submit_tool_outputs(
                    thread_id=event.thread_id,
                    run_id=event.run_id,
                    tool_approvals=tool_approvals
                )
                logger.info(f"✅ Submitted tool approvals")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to submit tool approvals: {e}")
            return False
    
    def create_thread(self) -> str:
        """Create a new thread and return thread_id."""
        thread = self.agents_client.threads.create()
        logger.info(f"✅ Created thread: {thread.id}")
        return thread.id

