#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
工具参数示例生成器
提供各种工具的标准参数使用示例
"""

from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class ToolParameterExamples:
    """
    工具参数示例生成器
    为各种工具提供标准的参数使用示例
    """
    
    def __init__(self):
        """初始化示例映射"""
        self.examples = {
            # MicroSandbox 示例
            ("microsandbox", "microsandbox_execute"): {
                "code": "import math\nresult = math.factorial(10)\nprint(f'The factorial of 10 is: {result}')"
            },
            ("microsandbox", "microsandbox_install_package"): {
                "package_name": "numpy"
            },
            ("microsandbox", "microsandbox_close_session"): {
                "session_id": "my-session-id"
            },
            
            # Browser 示例
            ("browser_use", "browser_navigate"): {
                "url": "https://www.google.com"
            },
            ("browser_use", "browser_search_google"): {
                "query": "Python machine learning tutorials"
            },
            ("browser_use", "browser_use_execute_task"): {
                "task": "Search for Python tutorials and open the first result",
                "max_steps": 10,
                "use_vision": True
            },
            ("browser_use", "browser_extract_content"): {
                "goal": "extract all product information and prices"
            },
            ("browser_use", "browser_input_text"): {
                "index": 2,
                "text": "hello world"
            },
            ("browser_use", "browser_click_element"): {
                "index": 5
            },
            ("browser_use", "browser_send_keys"): {
                "keys": "Enter"
            },
            ("browser_use", "browser_scroll_down"): {
                "amount": 500
            },
            ("browser_use", "browser_done"): {
                "text": "Task completed successfully",
                "success": True
            },
            
            # DeepSearch 示例
            ("deepsearch", "research"): {
                "question": "Python asyncio best practices and performance optimization"
            },
            ("deepsearch", "quick_research"): {
                "question": "machine learning basics"
            },
            ("deepsearch", "comprehensive_research"): {
                "question": "blockchain technology trends 2024",
                "topic_focus": "technical implementation"
            },
            
            # Memory Staging 示例
            ("memory_staging", "memory_write"): {
                "key": "stock_price_aapl",
                "value": {"price": 150.25, "currency": "USD"},
                "data_type": "financial_data",
                "tags": ["stock", "apple"]
            },
            ("memory_staging", "memory_read"): {
                "key": "stock_price_aapl"
            },
            ("memory_staging", "memory_search"): {
                "query": "stock price",
                "search_in_values": True
            },
            ("memory_staging", "memory_list"): {
                "include_values": True
            },
            ("memory_staging", "memory_clear"): {
                "key": "old_data"
            },
            
            # Search Tool 示例
            ("mcp-search-tool", "search_file_content"): {
                "file_path": "src/main.py",
                "regex_pattern": "def.*"
            },
            ("mcp-search-tool", "list_code_definitions"): {
                "directory_path": "src/"
            },
            ("mcp-search-tool", "analyze_tool_needs"): {
                "task_description": "create data visualization charts"
            }
        }
    
    def generate_example(self, tool_id: str, action: str, param_definitions: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成工具参数的使用示例
        
        Args:
            tool_id: 工具ID
            action: 动作名称
            param_definitions: 参数定义字典
            
        Returns:
            参数示例字典
        """
        # 获取预定义示例
        example_key = (tool_id, action)
        if example_key in self.examples:
            logger.debug(f"Using predefined example for {tool_id}.{action}")
            return self.examples[example_key]
        
        # 如果没有预定义示例，基于参数定义生成基础示例
        logger.debug(f"Generating dynamic example for {tool_id}.{action}")
        return self._generate_dynamic_example(param_definitions)
    
    def _generate_dynamic_example(self, param_definitions: Dict[str, Any]) -> Dict[str, Any]:
        """
        基于参数定义动态生成示例
        
        Args:
            param_definitions: 参数定义字典
            
        Returns:
            生成的参数示例
        """
        generated_example = {}
        
        for param_name, param_info in param_definitions.items():
            if param_info.get('required', False):
                param_type = param_info.get('type', 'string')
                
                if param_type == 'string':
                    generated_example[param_name] = self._generate_string_example(param_name)
                elif param_type == 'integer':
                    generated_example[param_name] = self._generate_integer_example(param_name)
                elif param_type == 'boolean':
                    generated_example[param_name] = True
                elif param_type == 'array':
                    generated_example[param_name] = []
                elif param_type == 'object':
                    generated_example[param_name] = {}
        
        return generated_example
    
    def _generate_string_example(self, param_name: str) -> str:
        """
        根据参数名称生成字符串示例
        
        Args:
            param_name: 参数名称
            
        Returns:
            示例字符串
        """
        param_name_lower = param_name.lower()
        
        if 'code' in param_name_lower:
            return "print('Hello World')"
        elif 'query' in param_name_lower:
            return "search query example"
        elif 'question' in param_name_lower:
            return "example question"
        elif 'url' in param_name_lower:
            return "https://www.example.com"
        elif 'task' in param_name_lower:
            return "example task description"
        elif 'goal' in param_name_lower:
            return "example goal description"
        elif 'text' in param_name_lower:
            return "example text"
        elif 'key' in param_name_lower:
            return "example_key"
        elif 'session' in param_name_lower:
            return "session-id-example"
        elif 'file' in param_name_lower:
            return "example.txt"
        elif 'path' in param_name_lower:
            return "/path/to/example"
        else:
            return f"example_{param_name}"
    
    def _generate_integer_example(self, param_name: str) -> int:
        """
        根据参数名称生成整数示例
        
        Args:
            param_name: 参数名称
            
        Returns:
            示例整数
        """
        param_name_lower = param_name.lower()
        
        if 'steps' in param_name_lower or 'max' in param_name_lower:
            return 10
        elif 'timeout' in param_name_lower:
            return 30
        elif 'port' in param_name_lower:
            return 8080
        elif 'index' in param_name_lower:
            return 1
        elif 'amount' in param_name_lower:
            return 100
        else:
            return 1

    def add_custom_example(self, tool_id: str, action: str, example: Dict[str, Any]):
        """
        添加自定义示例
        
        Args:
            tool_id: 工具ID
            action: 动作名称
            example: 示例参数字典
        """
        self.examples[(tool_id, action)] = example
        logger.info(f"Added custom example for {tool_id}.{action}")

# 全局实例
_parameter_examples = ToolParameterExamples()

def generate_parameter_example(tool_id: str, action: str, param_definitions: Dict[str, Any]) -> Dict[str, Any]:
    """
    便捷函数：生成工具参数示例
    
    Args:
        tool_id: 工具ID
        action: 动作名称
        param_definitions: 参数定义字典
        
    Returns:
        参数示例字典
    """
    return _parameter_examples.generate_example(tool_id, action, param_definitions)

def add_custom_example(tool_id: str, action: str, example: Dict[str, Any]):
    """
    便捷函数：添加自定义示例
    
    Args:
        tool_id: 工具ID
        action: 动作名称  
        example: 示例参数字典
    """
    _parameter_examples.add_custom_example(tool_id, action, example)