"""
LLM工具能力增强系统 - 场景化工具包管理
让LLM拥有更丰富的工具库和更好的工具感知能力
基于场景/任务的分层工具管理架构
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional, Callable, Protocol
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class TaskScenario(Enum):
    """任务场景枚举 - 基于实际使用场景分类"""
    WEB_INTERACTION = "web_interaction"      # 网页交互场景
    DATA_PROCESSING = "data_processing"      # 数据处理场景  
    CODE_DEVELOPMENT = "code_development"    # 代码开发场景
    FILE_MANAGEMENT = "file_management"      # 文件管理场景
    RESEARCH_ANALYSIS = "research_analysis"  # 研究分析场景
    AUTOMATION = "automation"                # 自动化场景
    COMMUNICATION = "communication"          # 通信场景
    CONTENT_CREATION = "content_creation"    # 内容创建场景

@dataclass
class ToolCapability:
    """工具能力描述"""
    name: str
    description: str
    parameters_schema: Dict[str, Any]
    examples: List[Dict[str, Any]]
    success_indicators: List[str]
    common_errors: List[str]
    usage_tips: List[str] = None  # 使用技巧

class ToolInterface(Protocol):
    """工具接口协议"""
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具操作"""
        ...
    
    def get_capabilities(self) -> List[ToolCapability]:
        """获取工具能力描述"""
        ...
    
    def get_scenarios(self) -> List[TaskScenario]:
        """获取工具适用的场景"""
        ...
    
    def get_description(self) -> str:
        """获取工具整体描述"""
        ...

@dataclass
class ToolPackage:
    """工具包 - 特定场景下的工具集合"""
    package_name: str
    package_description: str
    scenarios: List[TaskScenario]
    tools: Dict[str, ToolInterface]
    enabled: bool = True

class ScenarioBasedToolRegistry:
    """基于场景的工具注册中心"""
    
    def __init__(self):
        self._tool_packages: Dict[str, ToolPackage] = {}
        self._scenario_mappings: Dict[TaskScenario, List[str]] = {}  # scenario -> package_names
        self._all_tools: Dict[str, ToolInterface] = {}  # 所有工具的扁平化索引
        
    def register_tool_package(self, 
                             package_name: str,
                             package_description: str, 
                             scenarios: List[TaskScenario],
                             tools: Dict[str, ToolInterface]) -> bool:
        """注册工具包"""
        try:
            package = ToolPackage(
                package_name=package_name,
                package_description=package_description,
                scenarios=scenarios,
                tools=tools
            )
            
            self._tool_packages[package_name] = package
            
            # 更新场景映射
            for scenario in scenarios:
                if scenario not in self._scenario_mappings:
                    self._scenario_mappings[scenario] = []
                self._scenario_mappings[scenario].append(package_name)
            
            # 更新工具索引
            for tool_name, tool_instance in tools.items():
                self._all_tools[tool_name] = tool_instance
            
            logger.info(f"Successfully registered tool package: {package_name} for scenarios: {[s.value for s in scenarios]}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register tool package {package_name}: {e}")
            return False
    
    def get_available_packages(self, scenarios: Optional[List[TaskScenario]] = None) -> List[str]:
        """获取可用的工具包"""
        available = []
        
        for package_name, package in self._tool_packages.items():
            if not package.enabled:
                continue
                
            if scenarios is None:
                available.append(package_name)
            else:
                # 检查是否有场景匹配
                if any(scenario in package.scenarios for scenario in scenarios):
                    available.append(package_name)
        
        return available
    
    def get_package_tools(self, package_name: str) -> Optional[Dict[str, ToolInterface]]:
        """获取工具包中的所有工具"""
        package = self._tool_packages.get(package_name)
        return package.tools if package and package.enabled else None
    
    def analyze_task_scenarios(self, task_description: str) -> List[TaskScenario]:
        """分析任务描述，推测可能的场景（辅助功能，最终决策权在LLM）"""
        task_lower = task_description.lower()
        
        # 场景关键词映射
        scenario_keywords = {
            TaskScenario.WEB_INTERACTION: ["网页", "浏览", "搜索", "点击", "导航", "页面", "链接", "网站"],
            TaskScenario.DATA_PROCESSING: ["数据", "分析", "处理", "清洗", "统计", "计算", "表格"],
            TaskScenario.CODE_DEVELOPMENT: ["代码", "编程", "开发", "函数", "算法", "Python", "程序"],
            TaskScenario.FILE_MANAGEMENT: ["文件", "保存", "下载", "上传", "目录", "文档"],
            TaskScenario.RESEARCH_ANALYSIS: ["研究", "调研", "分析", "报告", "总结", "对比"],
            TaskScenario.AUTOMATION: ["自动化", "批量", "定时", "流程", "任务"],
            TaskScenario.COMMUNICATION: ["发送", "通知", "邮件", "消息", "通信"],
            TaskScenario.CONTENT_CREATION: ["创建", "生成", "制作", "编写", "设计", "图表", "可视化"]
        }
        
        detected_scenarios = []
        for scenario, keywords in scenario_keywords.items():
            if any(keyword in task_lower for keyword in keywords):
                detected_scenarios.append(scenario)
        
        return detected_scenarios if detected_scenarios else list(TaskScenario)  # 如果没有匹配，返回所有场景
    
    def get_llm_package_overview(self, package_names: List[str]) -> str:
        """为LLM生成工具包概览，让LLM自主选择需要的工具包"""
        overview_parts = []
        
        overview_parts.append("🧰 **可用工具包概览** (请根据任务需求自主选择需要的工具包):")
        
        for package_name in package_names:
            package = self._tool_packages.get(package_name)
            if not package:
                continue
                
            scenarios_desc = ", ".join([s.value for s in package.scenarios])
            tools_list = list(package.tools.keys())
            
            package_info = f"""
- **{package_name}**: {package.description}
  适用场景: {scenarios_desc}
  包含工具: {', '.join(tools_list)}"""
            
            overview_parts.append(package_info)
        
        overview_parts.append("\n💡 **选择策略**: 请根据你的分析，选择最适合当前任务的一个或多个工具包。")
        
        return "\n".join(overview_parts)
    
    def get_tools_description_for_llm(self, selected_package_names: List[str]) -> str:
        """为选中的工具包生成详细的工具描述"""
        descriptions = []
        
        descriptions.append("🔧 **你选择的工具包详细能力**:")
        
        for package_name in selected_package_names:
            package = self._tool_packages.get(package_name)
            if not package:
                continue
                
            descriptions.append(f"\n## {package_name} 工具包")
            descriptions.append(f"{package.description}")
            
            for tool_name, tool_instance in package.tools.items():
                tool_desc_parts = [f"\n### {tool_name}"]
                tool_desc_parts.append(f"{tool_instance.get_description()}")
                
                capabilities = tool_instance.get_capabilities()
                for capability in capabilities:
                    param_desc = ", ".join([f"{k}: {v.get('type', 'any')}" for k, v in capability.parameters_schema.items()])
                    action_desc = f"- **{capability.name}**: {capability.description}"
                    if param_desc:
                        action_desc += f"\n  参数: {{{param_desc}}}"
                    tool_desc_parts.append(action_desc)
                    
                    # 添加示例
                    if capability.examples:
                        example = capability.examples[0]
                        tool_desc_parts.append(f"  示例: {example}")
                    
                    # 添加使用技巧
                    if capability.usage_tips:
                        tips = "; ".join(capability.usage_tips)
                        tool_desc_parts.append(f"  技巧: {tips}")
                
                descriptions.append("\n".join(tool_desc_parts))
        
        return "\n".join(descriptions)
    
    async def execute_tool(self, tool_name: str, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具操作"""
        if tool_name not in self._all_tools:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' not found",
                "error_type": "ToolNotFound"
            }
        
        try:
            result = await self._all_tools[tool_name].execute(action, params)
            return result
        except Exception as e:
            logger.error(f"Tool execution failed - {tool_name}.{action}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_type": "ToolExecutionError"
            }
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """获取注册中心统计信息"""
        stats = {
            "total_packages": len(self._tool_packages),
            "enabled_packages": len([p for p in self._tool_packages.values() if p.enabled]),
            "total_tools": len(self._all_tools),
            "scenarios": {scenario.value: packages for scenario, packages in self._scenario_mappings.items()},
            "package_details": {
                name: {
                    "description": pkg.package_description,
                    "scenarios": [s.value for s in pkg.scenarios],
                    "tools": list(pkg.tools.keys()),
                    "enabled": pkg.enabled
                }
                for name, pkg in self._tool_packages.items()
            }
        }
        return stats

# 全局工具注册中心实例
scenario_tool_registry = ScenarioBasedToolRegistry() 