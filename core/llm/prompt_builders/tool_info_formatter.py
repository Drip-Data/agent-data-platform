# -*- coding: utf-8 -*-
"""
Tool Info Formatter for LLM Prompts
"""

import logging
from typing import List, Dict, Any
from core.unified_tool_manager import UnifiedToolManager

logger = logging.getLogger(__name__)

class ToolInfoFormatter:
    """
    Formats the list of available tools into a string that is easy for the LLM to understand.
    This version is simplified to encourage the use of <tool_param> for discovering parameters.
    """

    def __init__(self, tool_manager: UnifiedToolManager):
        """
        Initializes the formatter with a tool manager instance.

        Args:
            tool_manager: An instance of UnifiedToolManager.
        """
        self.tool_manager = tool_manager

    def format_tools_for_prompt(self) -> str:
        """
        Generates a simplified, LLM-friendly string describing available tools
        without exposing parameter details.

        This encourages the LLM to use the <tool_param> query to discover
        parameters dynamically.

        Returns:
            A formatted string of available tools and their actions.
        """
        tools_for_llm = self.tool_manager.get_tools_for_llm()
        
        prompt_parts = ["Here are the available services and their tools. To see parameters for a specific tool, use the <tool_param> tag.\n"]
        
        for tool_info in tools_for_llm:
            server_name = tool_info.get('id')
            description = tool_info.get('description')
            actions = tool_info.get('actions', [])

            if not server_name or not actions:
                continue

            prompt_parts.append(f"**Service: {server_name}**")
            if description:
                prompt_parts.append(f"Description: {description}")
            
            prompt_parts.append("Tools:")
            for action_name in actions:
                # Only show the name. The LLM must query for params.
                prompt_parts.append(f"  - {action_name}")
            
            prompt_parts.append("")  # Add a blank line for spacing

        return "\n".join(prompt_parts)

def get_formatted_tool_info(tool_manager: UnifiedToolManager) -> str:
    """
    Convenience function to get the formatted tool information string.
    """
    formatter = ToolInfoFormatter(tool_manager)
    return formatter.format_tools_for_prompt()