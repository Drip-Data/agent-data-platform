import asyncio
import logging
from typing import Dict, Any
from browser_use import Agent as BrowserAgent
from core.llm_client import LLMClient

logger = logging.getLogger(__name__)

class BrowserUseTool:
    """
    A tool that encapsulates the browser-use library to perform complex,
    natural language-based browser tasks.
    """

    def __init__(self):
        # The LLM client will be instantiated dynamically based on the runtime's configuration
        self.llm_client = None

    def _initialize_llm_client(self):
        """Initializes the LLM client if it hasn't been already."""
        if self.llm_client is None:
            # This configuration should ideally be passed in or accessed from a central place
            # For now, we'll use a default configuration that relies on environment variables
            config = {
                'provider': 'gemini', # Or detect from environment
            }
            self.llm_client = LLMClient(config)
            logger.info("BrowserUseTool: LLM Client initialized.")

    async def execute(self, task_description: str) -> Dict[str, Any]:
        """
        Executes a browser-based task.

        Args:
            task_description: A natural language description of the task to perform.

        Returns:
            A dictionary containing the results of the task execution.
        """
        self._initialize_llm_client()
        
        try:
            logger.info(f"Starting browser-use agent for task: '{task_description}'")
            
            # browser-use's Agent expects a LangChain-compatible LLM object
            # We need to get the underlying LangChain object from our LLMClient
            langchain_llm = self.llm_client.get_langchain_llm()

            agent = BrowserAgent(
                task=task_description,
                llm=langchain_llm,
            )
            
            # The run method in browser-use is asynchronous
            result = await agent.run()
            logger.info(f"Browser-use agent finished task. Result: {result}")
            
            return {
                "success": True,
                "final_result": result,
                "message": "Browser task completed successfully."
            }
        except Exception as e:
            logger.error(f"Browser-use agent failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": "An error occurred during the browser task."
            }

# Create a single, global instance of the tool
browser_use_tool = BrowserUseTool()