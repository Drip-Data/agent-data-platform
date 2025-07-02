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
    Formats the list of available tools into a string that is easy for the LLM to understand
    and directly use, following the V4 XML specification.
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
        Generates a V4-compliant, LLM-friendly string describing available tools.

        This format provides concrete, copy-pasteable examples for the LLM,
        ensuring it understands the required XML structure perfectly.

        Returns:
            A formatted string of available tools with full XML examples.
        """
        tools_for_llm = self.tool_manager.get_tools_for_llm()
        
        prompt_parts = ["Here are the available services and their tools:\n"]
        
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
                params = self.tool_manager.get_action_parameters(server_name, action_name)
                param_names = list(params.keys())
                
                # Create a user-friendly placeholder for parameters
                if any(p in action_name for p in ['execute', 'install']) and 'code' in param_names:
                    param_placeholder = f"print('Your Python code here')"
                elif any(p in action_name for p in ['execute', 'install']) and 'package_name' in param_names:
                    param_placeholder = f"pandas"
                elif 'file_path' in param_names and 'pattern' in param_names:
                    param_placeholder = str({'file_path': 'path/to/your/file.py', 'pattern': 'your_regex'}).replace("'", '"')
                elif param_names:
                    param_placeholder = ", ".join(param_names)
                else:
                    param_placeholder = "..."

                # Construct the full XML tag example
                xml_example = f"  - <{server_name}><{action_name}>{param_placeholder}</{action_name}></{server_name}>"
                prompt_parts.append(xml_example)
            
            prompt_parts.append("")  # Add a blank line for spacing

        return "\n".join(prompt_parts)

def get_formatted_tool_info(tool_manager: UnifiedToolManager) -> str:
    """
    Convenience function to get the formatted tool information string.
    """
    formatter = ToolInfoFormatter(tool_manager)
    return formatter.format_tools_for_prompt()
