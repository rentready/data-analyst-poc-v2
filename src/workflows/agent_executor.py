import logging
from typing import Dict, Any


from ..agent_manager import AgentManager
from ..run_processor import RunProcessor

from agent_framework import (
    Executor, ChatMessage, WorkflowContext, handler
)


logger = logging.getLogger(__name__)


class CustomAzureAgentExecutor(Executor):
    """Custom executor that wraps Azure AI Agent for workflow integration."""
    
    def __init__(self, agent_manager: 'AgentManager', thread_id: str, executor_id: str = "azure_agent_executor"):
        """Initialize with AgentManager instance."""
        super().__init__(executor_id)
        self.agent_manager = agent_manager
        self.thread_id = thread_id
        logger.info("CustomAzureAgentExecutor initialized")
    
    @handler
    async def run(self, user_message: str, ctx: WorkflowContext[list[ChatMessage], str]) -> None:
        """
        Execute agent with given context.
        
        This wraps the Azure AI Agent run creation and execution.
        Returns the result in a format compatible with workflow framework.
        """

        # Create and execute run
        run_id = self.agent_manager.create_run(self.thread_id, user_message)
        processor = RunProcessor(self.agent_manager.agents_client)

        for event in processor.poll_run_events(self.thread_id, run_id):
            await ctx.yield_output(event)

        logger.info(f"Created run: {run_id}")