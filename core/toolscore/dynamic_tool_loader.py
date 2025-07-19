#!/usr/bin/env python3
"""
Dynamic Tool Loader - 动态工具定义加载器

从 unified_tool_mappings.yaml 动态加载工具定义，实现单一可信源架构。
彻底消除多数据源问题，确保系统的一致性和可预测性。
"""

import yaml
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ToolDefinition:
    """工具定义数据结构"""
    name: str
    description: str
    parameters: Dict[str, Any]
    examples: List[Dict[str, Any]] = None

@dataclass 
class ServerDefinition:
    """服务器定义数据结构"""
    server_id: str
    name: str
    description: str
    version: str
    capabilities: List[ToolDefinition]
    tags: List[str]

class DynamicToolLoader:
    """动态工具定义加载器 - 单一可信源实现"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.config: Dict[str, Any] = {}
        self._load_config()
        
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        current_dir = Path(__file__).parent
        config_path = current_dir.parent.parent / "config" / "unified_tool_mappings.yaml"
        return str(config_path)
    
    def _load_config(self):
        """加载统一工具映射配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            logger.info(f"✅ 成功加载统一工具配置: {self.config_path}")
        except Exception as e:
            logger.error(f"❌ 加载统一工具配置失败: {e}")
            raise
    
    def get_server_definition(self, server_id: str) -> ServerDefinition:
        """获取指定服务器的完整定义"""
        try:
            # 从统一配置获取工具动作
            action_mappings = self.config.get('action_mappings', {})
            tool_parameters = self.config.get('tool_parameters', {})
            
            if server_id not in action_mappings:
                raise ValueError(f"服务器 {server_id} 未在统一配置中定义")
            
            server_actions = action_mappings[server_id]
            canonical_actions = server_actions.get('canonical_actions', [])
            
            # 构建工具定义列表
            capabilities = []
            for action in canonical_actions:
                tool_params = tool_parameters.get(server_id, {}).get(action, {})
                
                # 构建工具定义
                tool_def = ToolDefinition(
                    name=action,
                    description=self._generate_description(server_id, action),
                    parameters=tool_params,
                    examples=self._generate_examples(action, tool_params)
                )
                capabilities.append(tool_def)
            
            # 构建服务器定义
            server_def = ServerDefinition(
                server_id=server_id,
                name=self._generate_server_name(server_id),
                description=self._generate_server_description(server_id),
                version="1.0.0",
                capabilities=capabilities,
                tags=self._generate_server_tags(server_id)
            )
            
            logger.info(f"✅ 为服务器 {server_id} 生成了 {len(capabilities)} 个工具定义")
            return server_def
            
        except Exception as e:
            logger.error(f"❌ 获取服务器 {server_id} 定义失败: {e}")
            raise
    
    def get_capabilities_list(self, server_id: str) -> List[Dict[str, Any]]:
        """获取服务器能力列表（JSON格式）"""
        server_def = self.get_server_definition(server_id)
        
        capabilities = []
        for tool in server_def.capabilities:
            capability = {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
            }
            if tool.examples:
                capability["examples"] = tool.examples
            capabilities.append(capability)
        
        return capabilities
    
    def _generate_description(self, server_id: str, action: str) -> str:
        """生成工具描述"""
        descriptions = {
            'browser_use': {
                'browser_navigate': '导航到指定URL',
                'browser_extract_content': 'AI驱动的页面内容智能提取',
                'browser_get_content': '基于CSS选择器的精确内容提取',
                'browser_search_google': '执行Google搜索',
                'browser_click_element': '点击页面元素',
                'browser_input_text': '在元素中输入文本',
                'browser_screenshot': '截取页面截图',
                'browser_use_execute_task': 'AI驱动的复杂浏览器任务执行'
            },
            'microsandbox': {
                'microsandbox_execute': '在安全沙箱中执行Python代码',
                'microsandbox_install_package': '安装Python包',
                'microsandbox_list_sessions': '列出所有活动会话',
                'microsandbox_close_session': '关闭指定会话'
            },
            'deepsearch': {
                'research': '深度研究和信息收集',
                'quick_research': '快速研究',
                'comprehensive_research': '全面研究'
            }
        }
        
        return descriptions.get(server_id, {}).get(action, f"{server_id} {action} 操作")
    
    def _generate_examples(self, action: str, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成工具使用示例"""
        examples = []
        
        # 根据参数生成基本示例
        if parameters:
            example = {}
            for param_name, param_def in parameters.items():
                if param_def.get('required', False):
                    if param_def.get('type') == 'string':
                        example[param_name] = f"示例{param_name}"
                    elif param_def.get('type') == 'integer':
                        example[param_name] = 1
                    elif param_def.get('type') == 'boolean':
                        example[param_name] = True
            
            if example:
                examples.append(example)
        
        # 为常见工具添加特定示例
        if action == 'browser_navigate':
            examples.append({"url": "https://www.google.com"})
        elif action == 'browser_extract_content':
            examples.append({"goal": "提取页面主要内容", "include_links": False})
        elif action == 'browser_get_content':
            examples.append({"selector": "body"})
            examples.append({"selector": ".main-content"})
            examples.append({})  # 空选择器示例
        
        return examples if examples else [{}]
    
    def _generate_server_name(self, server_id: str) -> str:
        """生成服务器显示名称"""
        names = {
            'browser_use': 'Browser Use MCP Server',
            'microsandbox': 'MicroSandbox MCP Server', 
            'deepsearch': 'DeepSearch MCP Server',
            'mcp-search-tool': 'Search Tool MCP Server'
        }
        return names.get(server_id, f"{server_id.title()} MCP Server")
    
    def _generate_server_description(self, server_id: str) -> str:
        """生成服务器描述"""
        descriptions = {
            'browser_use': '基于Browser-Use的AI浏览器自动化服务器，完整实现browser-use的所有功能',
            'microsandbox': '安全的Python代码执行沙箱服务器',
            'deepsearch': '高级搜索和研究能力服务器',
            'mcp-search-tool': '文件系统搜索和内容分析服务器'
        }
        return descriptions.get(server_id, f"{server_id} MCP服务器")
    
    def _generate_server_tags(self, server_id: str) -> List[str]:
        """生成服务器标签"""
        tags = {
            'browser_use': ['browser', 'automation', 'ai', 'web-scraping', 'browser-use'],
            'microsandbox': ['python', 'execution', 'sandbox', 'security'],
            'deepsearch': ['search', 'research', 'information', 'analysis'],
            'mcp-search-tool': ['search', 'files', 'content', 'analysis']
        }
        return tags.get(server_id, [server_id, 'mcp'])
    
    def validate_server_consistency(self, server_id: str, actual_handlers: Dict[str, Any]) -> Dict[str, Any]:
        """验证服务器实现与配置的一致性"""
        try:
            server_def = self.get_server_definition(server_id)
            configured_actions = {tool.name for tool in server_def.capabilities}
            implemented_actions = set(actual_handlers.keys())
            
            missing_implementations = configured_actions - implemented_actions
            extra_implementations = implemented_actions - configured_actions
            
            validation_result = {
                'is_consistent': len(missing_implementations) == 0 and len(extra_implementations) == 0,
                'configured_actions': sorted(configured_actions),
                'implemented_actions': sorted(implemented_actions),
                'missing_implementations': sorted(missing_implementations),
                'extra_implementations': sorted(extra_implementations),
                'summary': {
                    'total_configured': len(configured_actions),
                    'total_implemented': len(implemented_actions),
                    'missing_count': len(missing_implementations),
                    'extra_count': len(extra_implementations)
                }
            }
            
            if validation_result['is_consistent']:
                logger.info(f"✅ 服务器 {server_id} 配置与实现完全一致")
            else:
                logger.warning(f"⚠️ 服务器 {server_id} 配置与实现不一致:")
                if missing_implementations:
                    logger.warning(f"  缺少实现: {missing_implementations}")
                if extra_implementations:
                    logger.warning(f"  多余实现: {extra_implementations}")
            
            return validation_result
            
        except Exception as e:
            logger.error(f"❌ 验证服务器 {server_id} 一致性失败: {e}")
            return {
                'is_consistent': False,
                'error': str(e)
            }
    
    def reload_config(self):
        """重新加载配置文件"""
        logger.info("🔄 重新加载统一工具配置...")
        self._load_config()
        logger.info("✅ 配置重新加载完成")


# 全局实例
_dynamic_tool_loader = None

def get_dynamic_tool_loader() -> DynamicToolLoader:
    """获取全局动态工具加载器实例"""
    global _dynamic_tool_loader
    if _dynamic_tool_loader is None:
        _dynamic_tool_loader = DynamicToolLoader()
    return _dynamic_tool_loader

def reload_tool_definitions():
    """重新加载工具定义"""
    global _dynamic_tool_loader
    if _dynamic_tool_loader is not None:
        _dynamic_tool_loader.reload_config()
    else:
        _dynamic_tool_loader = DynamicToolLoader()