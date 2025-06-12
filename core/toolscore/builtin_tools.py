"""
内置工具注册模块
将ToolScore的核心功能注册为可调用的工具
"""

import logging
from typing import List, Dict, Any
from .interfaces import FunctionToolSpec, ToolCapability, ToolType
from .unified_tool_library import UnifiedToolLibrary

logger = logging.getLogger(__name__)

class BuiltinToolsRegistrar:
    """内置工具注册器"""
    
    def __init__(self, tool_library: UnifiedToolLibrary):
        self.tool_library = tool_library
    
    async def register_all_builtin_tools(self) -> Dict[str, Any]:
        """注册所有内置工具"""
        logger.info("📦 开始注册ToolScore内置工具...")
        
        registration_results = {
            "success_count": 0,
            "failed_count": 0,
            "results": []
        }
        
        # 定义所有内置工具
        builtin_tools = [
            self._create_mcp_search_tool_spec(),
            self._create_mcp_install_tool_spec(),
            self._create_tool_gap_analyzer_spec(),
            self._create_task_requirements_analyzer_spec()
        ]
        
        # 逐个注册
        for tool_spec in builtin_tools:
            try:
                result = await self.tool_library.register_function_tool(tool_spec)
                
                if result.success:
                    registration_results["success_count"] += 1
                    logger.info(f"✅ 注册内置工具: {tool_spec.name}")
                else:
                    registration_results["failed_count"] += 1
                    logger.error(f"❌ 注册失败: {tool_spec.name} - {result.error}")
                
                registration_results["results"].append({
                    "tool_id": tool_spec.tool_id,
                    "name": tool_spec.name,
                    "success": result.success,
                    "error": result.error if not result.success else None
                })
                
            except Exception as e:
                registration_results["failed_count"] += 1
                error_msg = str(e)
                logger.error(f"❌ 注册异常: {tool_spec.name} - {error_msg}")
                
                registration_results["results"].append({
                    "tool_id": tool_spec.tool_id,
                    "name": tool_spec.name,
                    "success": False,
                    "error": error_msg
                })
        
        logger.info(f"📦 内置工具注册完成: {registration_results['success_count']} 成功, {registration_results['failed_count']} 失败")
        return registration_results
    
    def _create_mcp_search_tool_spec(self) -> FunctionToolSpec:
        """创建MCP搜索工具规范"""
        capabilities = [
            ToolCapability(
                name="search_mcp_servers",
                description="Search for MCP servers based on task requirements and capabilities",
                parameters={
                    "task_description": {
                        "type": "string",
                        "description": "Description of the task that needs tool support",
                        "required": True
                    },
                    "required_capabilities": {
                        "type": "array",
                        "description": "List of required capabilities/features",
                        "items": {"type": "string"},
                        "required": False
                    },
                    "max_results": {
                        "type": "integer", 
                        "description": "Maximum number of search results to return",
                        "default": 5,
                        "required": False
                    }
                },
                examples=[
                    {
                        "task_description": "Generate a cat image in cartoon style",
                        "required_capabilities": ["image_generation", "ai_art"],
                        "max_results": 3
                    }
                ]
            )
        ]
        
        return FunctionToolSpec(
            tool_id="mcp_search_tool",
            name="MCP Server Search Tool",
            description="Intelligent search tool for finding and recommending MCP servers based on task requirements. Uses semantic analysis to match tasks with appropriate tools from a database of 300+ MCP servers.",
            tool_type=ToolType.FUNCTION,
            capabilities=capabilities,
            tags=["search", "mcp", "tool_discovery", "intelligent_matching"],
            enabled=True,
            module_path="core.toolscore.mcp_search_tool",
            class_name="MCPSearchTool"
        )
    
    def _create_mcp_install_tool_spec(self) -> FunctionToolSpec:
        """创建MCP安装工具规范"""
        capabilities = [
            ToolCapability(
                name="search_and_install_tools",
                description="Search for MCP servers and automatically install the best match for the given task",
                parameters={
                    "task_description": {
                        "type": "string",
                        "description": "Description of the task that needs tool support",
                        "required": True
                    },
                    "current_available_tools": {
                        "type": "array",
                        "description": "List of currently available tools",
                        "items": {"type": "object"},
                        "required": False,
                        "default": []
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason why new tools are needed",
                        "required": False,
                        "default": "Task requires additional capabilities"
                    }
                },
                examples=[
                    {
                        "task_description": "Create a data visualization dashboard from CSV data",
                        "current_available_tools": [],
                        "reason": "Need data processing and visualization capabilities"
                    }
                ]
            )
        ]
        
        return FunctionToolSpec(
            tool_id="mcp_install_tool",
            name="MCP Server Installation Tool", 
            description="Automated MCP server installation tool that searches for appropriate tools and installs them on-demand. Handles the complete workflow from search to deployment.",
            tool_type=ToolType.FUNCTION,
            capabilities=capabilities,
            tags=["install", "mcp", "automation", "tool_management"],
            enabled=True,
            module_path="core.toolscore.mcp_search_tool",
            class_name="MCPSearchTool"
        )
    
    def _create_tool_gap_analyzer_spec(self) -> FunctionToolSpec:
        """创建工具缺口分析器规范"""
        capabilities = [
            ToolCapability(
                name="analyze_tool_needs",
                description="Analyze task requirements to identify missing tools and capabilities",
                parameters={
                    "task_description": {
                        "type": "string",
                        "description": "Description of the task to analyze",
                        "required": True
                    },
                    "current_available_tools": {
                        "type": "array",
                        "description": "List of currently available tools",
                        "items": {"type": "object"},
                        "required": False,
                        "default": []
                    }
                },
                examples=[
                    {
                        "task_description": "Build a web scraper to collect product prices from e-commerce sites",
                        "current_available_tools": [
                            {"tool_id": "python-executor", "capabilities": ["code_execution"]}
                        ]
                    }
                ]
            )
        ]
        
        return FunctionToolSpec(
            tool_id="tool_gap_analyzer",
            name="Tool Gap Analyzer",
            description="Intelligent tool gap analysis system that compares task requirements with available tools to identify missing capabilities. Uses LLM-powered semantic analysis for accurate assessment.",
            tool_type=ToolType.FUNCTION,
            capabilities=capabilities,
            tags=["analysis", "gap_detection", "planning", "intelligence"],
            enabled=True,
            module_path="core.toolscore.mcp_search_tool",
            class_name="MCPSearchTool"
        )
    
    def _create_task_requirements_analyzer_spec(self) -> FunctionToolSpec:
        """创建任务需求分析器规范"""
        capabilities = [
            ToolCapability(
                name="analyze_task_requirements",
                description="Analyze task description to extract requirements, capabilities needed, and suggest tool types",
                parameters={
                    "task_description": {
                        "type": "string",
                        "description": "Description of the task to analyze",
                        "required": True
                    }
                },
                examples=[
                    {
                        "task_description": "Create an interactive dashboard showing real-time cryptocurrency prices with alerts"
                    }
                ]
            )
        ]
        
        return FunctionToolSpec(
            tool_id="task_requirements_analyzer", 
            name="Task Requirements Analyzer",
            description="Advanced LLM-powered task analysis tool that breaks down complex tasks into specific requirements, identifies needed capabilities, and suggests appropriate tool categories. Essential for intelligent tool selection.",
            tool_type=ToolType.FUNCTION,
            capabilities=capabilities,
            tags=["analysis", "requirements", "llm_powered", "planning"],
            enabled=True,
            module_path="core.llm_client",
            class_name="LLMClient"
        ) 