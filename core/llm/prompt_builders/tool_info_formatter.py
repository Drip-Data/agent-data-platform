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

            # 🔧 按功能分类展示工具，提供完整参数信息和使用场景
            categorized_actions = self._categorize_actions(server_name, actions)
            
            for category, actions_in_category in categorized_actions.items():
                if actions_in_category:
                    prompt_parts.append(f"  **{category}:**")
                    
                    for action_name in actions_in_category:
                        tool_info = self._get_enhanced_tool_info(server_name, action_name)
                        
                        # XML示例
                        xml_example = f"  - <{server_name}><{action_name}>{tool_info['example']}</{action_name}></{server_name}>"
                        prompt_parts.append(xml_example)
                        
                        # 使用场景
                        prompt_parts.append(f"    💡 {tool_info['use_case']}")
                        
                        # 完整参数列表
                        if tool_info['parameters']:
                            prompt_parts.append(f"    📋 Parameters: {tool_info['parameters']}")
                        else:
                            prompt_parts.append("    📋 No parameters required")
                        
                        prompt_parts.append("")  # 工具间间隔
            
            prompt_parts.append("")  # Add a blank line for spacing

        return "\n".join(prompt_parts)
    
    def _categorize_actions(self, server_name: str, actions: List[str]) -> Dict[str, List[str]]:
        """🔧 按功能分类工具动作"""
        categories = {
            "Core Operations": [],
            "Advanced Features": [],
            "Management": [],
            "Diagnostics": [],
            "Page Interaction": [],
            "Tab Management": [],
            "Session Control": []
        }
        
        if server_name == 'microsandbox':
            action_categories = {
                "Core Operations": ['microsandbox_execute', 'microsandbox_install_package'],
                "Management": ['microsandbox_list_sessions', 'microsandbox_close_session', 'microsandbox_cleanup_expired'],
                "Diagnostics": ['microsandbox_get_performance_stats', 'microsandbox_get_health_status']
            }
        elif server_name == 'browser_use':
            action_categories = {
                "Core Operations": ['browser_navigate', 'browser_search_google', 'browser_extract_content', 'browser_use_execute_task']
            }
        elif server_name == 'deepsearch':
            action_categories = {
                "Core Operations": ['research', 'quick_research', 'comprehensive_research']
            }
        elif server_name == 'mcp-search-tool':
            action_categories = {
                "Core Operations": ['search_file_content', 'list_code_definitions'],
                "Advanced Features": ['analyze_tool_needs', 'search_and_install_tools']
            }
        else:
            action_categories = {"Core Operations": actions}
        
        # 分类动作
        for category, category_actions in action_categories.items():
            for action in actions:
                if action in category_actions:
                    categories[category].append(action)
        
        # 移除空分类
        return {k: v for k, v in categories.items() if v}
    
    def _get_enhanced_tool_info(self, server_name: str, action_name: str) -> Dict[str, str]:
        """🔧 获取增强的工具信息，包含使用场景和完整参数"""
        # 🔧 首先尝试从UnifiedToolManager获取真实参数
        real_params = self._get_real_parameters(server_name, action_name)
        
        tool_definitions = {
            # MicroSandbox工具定义
            'microsandbox_execute': {
                'example': "print('Hello World'); result = 2 + 3; print(result)",
                'use_case': "Execute Python code in secure sandbox environment",
                'parameters': "code (required), session_id (optional), timeout (optional)"
            },
            'microsandbox_install_package': {
                'example': "numpy",
                'use_case': "Install Python packages in sandbox environment",
                'parameters': "package_name (required), version (optional), session_id (optional)"
            },
            'microsandbox_list_sessions': {
                'example': "",
                'use_case': "List all active sandbox sessions",
                'parameters': ""
            },
            'microsandbox_close_session': {
                'example': "my-session-id",
                'use_case': "Close specific sandbox session",
                'parameters': "session_id (required)"
            },
            'microsandbox_cleanup_expired': {
                'example': "",
                'use_case': "Clean up expired sandbox sessions",
                'parameters': "max_age (optional, in seconds)"
            },
            'microsandbox_get_performance_stats': {
                'example': "",
                'use_case': "Get sandbox performance metrics and statistics",
                'parameters': ""
            },
            'microsandbox_get_health_status': {
                'example': "",
                'use_case': "Check sandbox service health and status",
                'parameters': ""
            },
            
            # Browser工具定义
            'browser_navigate': {
                'example': "https://www.example.com",
                'use_case': "Navigate to a specific URL",
                'parameters': "url (required)"
            },
            'browser_go_back': {
                'example': "",
                'use_case': "Go back to previous page",
                'parameters': ""
            },
            'browser_open_tab': {
                'example': "https://www.google.com",
                'use_case': "Open new tab with specified URL",
                'parameters': "url (required)"
            },
            'browser_close_tab': {
                'example': "1",
                'use_case': "Close specific tab by ID",
                'parameters': "page_id (required)"
            },
            'browser_switch_tab': {
                'example': "0",
                'use_case': "Switch to specific tab",
                'parameters': "page_id (required)"
            },
            'browser_click_element': {
                'example': "5",
                'use_case': "Click on page element by index",
                'parameters': "index (required)"
            },
            'browser_input_text': {
                'example': '{"index": 2, "text": "hello world"}',
                'use_case': "Input text into form field",
                'parameters': "index (required), text (required)"
            },
            'browser_send_keys': {
                'example': "Enter",
                'use_case': "Send keyboard keys (Enter, Escape, Ctrl+C, etc.)",
                'parameters': "keys (required)"
            },
            'browser_drag_drop': {
                'example': '{"element_source": ".item1", "element_target": ".dropzone"}',
                'use_case': "Drag and drop elements",
                'parameters': "element_source, element_target, or coordinates"
            },
            'browser_extract_content': {
                'example': "extract all product information",
                'use_case': "Extract specific content from current page",
                'parameters': "goal (required), include_links (optional)"
            },
            'browser_search_google': {
                'example': "Python machine learning tutorial",
                'use_case': "Search on Google with specified query",
                'parameters': "query (required)"
            },
            'browser_screenshot': {
                'example': "current_page.png",
                'use_case': "Take screenshot of current page",
                'parameters': "filename (optional)"
            },
            'browser_save_pdf': {
                'example': "",
                'use_case': "Save current page as PDF",
                'parameters': ""
            },
            'browser_get_ax_tree': {
                'example': "50",
                'use_case': "Get accessibility tree for page analysis",
                'parameters': "number_of_elements (required)"
            },
            'browser_get_dropdown_options': {
                'example': "3",
                'use_case': "Get all options from dropdown menu",
                'parameters': "index (required)"
            },
            'browser_select_dropdown_option': {
                'example': '{"index": 3, "text": "Option 1"}',
                'use_case': "Select option from dropdown menu",
                'parameters': "index (required), text (required)"
            },
            'browser_scroll_down': {
                'example': "500",
                'use_case': "Scroll page down by pixels or one page",
                'parameters': "amount (optional, in pixels)"
            },
            'browser_scroll_up': {
                'example': "300",
                'use_case': "Scroll page up by pixels or one page",
                'parameters': "amount (optional, in pixels)"
            },
            'browser_scroll_to_text': {
                'example': "Sign up",
                'use_case': "Scroll to element containing specific text",
                'parameters': "text (required)"
            },
            'browser_wait': {
                'example': "5",
                'use_case': "Wait for specified number of seconds",
                'parameters': "seconds (optional, default 3)"
            },
            'browser_done': {
                'example': '{"text": "Task completed", "success": true}',
                'use_case': "Mark browser task as completed",
                'parameters': "text (required), success (required)"
            },
            'browser_close_session': {
                'example': "",
                'use_case': "Close browser session and cleanup",
                'parameters': ""
            },
            'browser_get_page_info': {
                'example': "",
                'use_case': "Get current page information and metadata",
                'parameters': ""
            },
            'browser_get_current_url': {
                'example': "",
                'use_case': "Get current page URL",
                'parameters': ""
            },
            'browser_use_execute_task': {
                'example': "Search for Python tutorials and open the first result",
                'use_case': "Execute complex browser task using AI",
                'parameters': "task (required), max_steps (optional), use_vision (optional)"
            },
            
            # DeepSearch工具定义
            'research': {
                'example': "Python asyncio best practices",
                'use_case': "Professional deep research on any topic",
                'parameters': "question (required), initial_queries (optional), max_loops (optional)"
            },
            'quick_research': {
                'example': "machine learning basics",
                'use_case': "Quick research for basic information",
                'parameters': "question (required)"
            },
            'comprehensive_research': {
                'example': "blockchain technology trends 2024",
                'use_case': "Comprehensive in-depth research analysis",
                'parameters': "question (required), topic_focus (optional)"
            },
            
            # Search Tool工具定义
            'search_file_content': {
                'example': '{"file_path": "src/main.py", "regex_pattern": "def.*"}',
                'use_case': "Search for patterns in specific files",
                'parameters': "file_path (required), regex_pattern (required)"
            },
            'list_code_definitions': {
                'example': "src/",
                'use_case': "List all code definitions in directory",
                'parameters': "file_path (optional), directory_path (optional)"
            },
            'analyze_tool_needs': {
                'example': "create data visualization charts",
                'use_case': "Analyze what tools are needed for a task",
                'parameters': "task_description (required)"
            },
            'search_and_install_tools': {
                'example': "need to process PDF files",
                'use_case': "Search and install new tools for specific needs",
                'parameters': "task_description (required), reason (optional)"
            }
        }
        
        # 获取基础定义
        base_definition = tool_definitions.get(action_name, {
            'example': "...",
            'use_case': f"Use {action_name} for {server_name} operations",
            'parameters': "Check service documentation for parameters"
        })
        
        # 🔧 如果有真实参数，使用真实参数替换parameters字段
        if real_params:
            formatted_params = []
            for param_name, param_info in real_params.items():
                param_type = param_info.get('type', 'string')
                required = param_info.get('required', False)
                status = 'required' if required else 'optional'
                formatted_params.append(f"{param_name} ({status})")
            
            base_definition['parameters'] = ", ".join(formatted_params) if formatted_params else ""
        
        return base_definition
    
    def _get_real_parameters(self, server_name: str, action_name: str) -> Dict[str, Any]:
        """🔧 从UnifiedToolManager获取真实参数定义"""
        try:
            return self.tool_manager.get_action_parameters(server_name, action_name)
        except Exception:
            return {}

def get_formatted_tool_info(tool_manager: UnifiedToolManager) -> str:
    """
    Convenience function to get the formatted tool information string.
    """
    formatter = ToolInfoFormatter(tool_manager)
    return formatter.format_tools_for_prompt()
