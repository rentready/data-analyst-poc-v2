import logging
from typing import Dict, Any


from ..agent_manager import AgentManager
from ..run_processor import RunProcessor
from ..run_events import RequiresApprovalEvent

from dataclasses import dataclass
from agent_framework import (
    Executor, ChatMessage, WorkflowContext, handler, executor, RequestInfoEvent, RequestResponse, AgentExecutorRequest, AgentExecutorResponse,
    RequestInfoMessage
)


logger = logging.getLogger(__name__)

@dataclass
class ToolApprovalRequest(RequestInfoMessage):
    """Request for tool approval."""
    event: RequiresApprovalEvent = None

class CustomAzureAgentExecutor(Executor):
    """Custom executor that wraps Azure AI Agent for workflow integration."""
    
    def __init__(self, agent_manager: 'AgentManager', thread_id: str, executor_id: str = "azure_agent_executor"):
        """Initialize with AgentManager instance."""
        super().__init__(executor_id)
        self.agent_manager = agent_manager
        self.thread_id = thread_id
        self.processor = None
        self.run_id = None
        logger.info("CustomAzureAgentExecutor initialized")
    
    @handler
    async def run(self, user_message: str, ctx: WorkflowContext[ToolApprovalRequest]) -> None:
        """
        Execute agent with given context.
        
        This wraps the Azure AI Agent run creation and execution.
        Returns the result in a format compatible with workflow framework.
        """

        logger.info(f"Running agent with message: {user_message}")

        # Create and execute run
        if not self.run_id:
            self.run_id = self.agent_manager.create_run(self.thread_id, user_message)
            self.processor = RunProcessor(self.agent_manager.agents_client)


        for event in self.processor.poll_run_events(self.thread_id, self.run_id):
            if event.is_blocking and isinstance(event, RequiresApprovalEvent):
                logger.info(f"Blocking event: {event}")
                await ctx.send_message(ToolApprovalRequest(event=event))
                logger.info(f"Added event: {event}")
                return
            else:
                await ctx.yield_output(event)
            logger.info(f"Yielded event: {event}")

        logger.info(f"Created run: {self.run_id}")
        
    @handler
    async def on_human_feedback(
        self,
        feedback: RequestResponse[ToolApprovalRequest, str],
        ctx: WorkflowContext[str],
    ) -> None:
        """Handle human feedback for tool approval.

        The RequestResponse contains both the human's string reply ("approved"/"denied") 
        and the correlated ToolApprovalRequest with the approval event.
        """

        logger.info(f"On human feedback: {feedback}")
        logger.info(f"Context: {ctx}")
        
        # Extract approval decision from feedback response
        approved = feedback.data == "approved"
        event = feedback.original_request.event
        
        # Submit approvals to Azure AI
        if self.agent_manager.submit_approvals(event, approved=approved):
            if approved:
                await ctx.yield_output(event)
            else:
                await ctx.yield_output(event)

        await ctx.send_message(feedback.data)