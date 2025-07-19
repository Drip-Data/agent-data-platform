#!/usr/bin/env python3
"""
Action Handlers Synchronizer - 动作处理器同步器

确保 MCP 服务器的 _action_handlers 与 unified_tool_mappings.yaml 完全同步。
实现自动代码生成和验证，消除手动维护的一致性问题。
"""

import ast
import inspect
import logging
from pathlib import Path
from typing import Dict, List, Any, Set, Optional, Callable
from dataclasses import dataclass

from .dynamic_tool_loader import get_dynamic_tool_loader

logger = logging.getLogger(__name__)

@dataclass
class HandlerInfo:
    """处理器信息"""
    name: str
    method_name: str
    is_lambda: bool
    is_async: bool
    parameters: List[str]

class ActionHandlersSynchronizer:
    """动作处理器同步器 - 确保代码与配置完全一致"""
    
    def __init__(self, server_class_instance):
        self.server_instance = server_class_instance
        self.server_id = getattr(server_class_instance, 'server_id', 'unknown')
        self.loader = get_dynamic_tool_loader()
        
    def analyze_current_handlers(self) -> Dict[str, HandlerInfo]:
        """分析当前实现的动作处理器"""
        current_handlers = {}
        
        if hasattr(self.server_instance, '_action_handlers'):
            handlers_dict = self.server_instance._action_handlers
            
            for action_name, handler in handlers_dict.items():
                handler_info = self._analyze_handler(action_name, handler)
                current_handlers[action_name] = handler_info
        
        return current_handlers
    
    def _analyze_handler(self, action_name: str, handler: Callable) -> HandlerInfo:
        """分析单个处理器的信息"""
        try:
            is_lambda = lambda_check = '<lambda>' in str(handler)
            is_async = inspect.iscoroutinefunction(handler)
            
            # 获取参数信息
            try:
                sig = inspect.signature(handler)
                parameters = [param.name for param in sig.parameters.values() 
                             if param.name not in ['self', 'cls']]
            except:
                parameters = ['parameters']  # 默认参数
            
            # 确定方法名
            if is_lambda:
                method_name = f"_handle_{action_name}"  # 建议的方法名
            else:
                method_name = getattr(handler, '__name__', f"_handle_{action_name}")
            
            return HandlerInfo(
                name=action_name,
                method_name=method_name,
                is_lambda=is_lambda,
                is_async=is_async,
                parameters=parameters
            )
            
        except Exception as e:
            logger.warning(f"分析处理器 {action_name} 失败: {e}")
            return HandlerInfo(
                name=action_name,
                method_name=f"_handle_{action_name}",
                is_lambda=True,
                is_async=True,
                parameters=['parameters']
            )
    
    def get_required_actions(self) -> Set[str]:
        """从统一配置获取需要的动作列表"""
        try:
            server_def = self.loader.get_server_definition(self.server_id)
            return {tool.name for tool in server_def.capabilities}
        except Exception as e:
            logger.error(f"获取 {self.server_id} 需要的动作失败: {e}")
            return set()
    
    def validate_handlers_consistency(self) -> Dict[str, Any]:
        """验证处理器与配置的一致性"""
        current_handlers = self.analyze_current_handlers()
        required_actions = self.get_required_actions()
        
        implemented_actions = set(current_handlers.keys())
        
        missing_handlers = required_actions - implemented_actions
        extra_handlers = implemented_actions - required_actions
        
        validation_result = {
            'is_consistent': len(missing_handlers) == 0 and len(extra_handlers) == 0,
            'server_id': self.server_id,
            'required_actions': sorted(required_actions),
            'implemented_actions': sorted(implemented_actions),
            'missing_handlers': sorted(missing_handlers),
            'extra_handlers': sorted(extra_handlers),
            'handler_analysis': {
                action: {
                    'method_name': info.method_name,
                    'is_lambda': info.is_lambda,
                    'is_async': info.is_async,
                    'parameters': info.parameters
                }
                for action, info in current_handlers.items()
            },
            'recommendations': self._generate_recommendations(missing_handlers, current_handlers)
        }
        
        return validation_result
    
    def _generate_recommendations(self, missing_handlers: Set[str], 
                                current_handlers: Dict[str, HandlerInfo]) -> List[str]:
        """生成修复建议"""
        recommendations = []
        
        if missing_handlers:
            recommendations.append("需要实现以下缺失的处理器:")
            for action in sorted(missing_handlers):
                method_name = f"_handle_{action}"
                recommendations.append(f"  - {action}: 建议实现方法 {method_name}")
        
        # 检查lambda处理器，建议转换为专用方法
        lambda_handlers = [action for action, info in current_handlers.items() if info.is_lambda]
        if lambda_handlers:
            recommendations.append("建议将以下lambda处理器转换为专用方法以提高可维护性:")
            for action in sorted(lambda_handlers):
                info = current_handlers[action]
                recommendations.append(f"  - {action}: 转换为方法 {info.method_name}")
        
        return recommendations
    
    def generate_missing_handlers_code(self) -> str:
        """生成缺失处理器的代码模板"""
        validation = self.validate_handlers_consistency()
        missing_handlers = validation['missing_handlers']
        
        if not missing_handlers:
            return "# 所有处理器都已实现"
        
        code_lines = [
            "# 🤖 自动生成的缺失处理器代码模板",
            "# 请根据实际需求实现以下方法:",
            ""
        ]
        
        for action in sorted(missing_handlers):
            method_name = f"_handle_{action}"
            code_lines.extend([
                f"    async def {method_name}(self, parameters: Dict[str, Any]) -> Dict[str, Any]:",
                f'        """处理 {action} 动作"""',
                "        try:",
                f'            # TODO: 实现 {action} 的具体逻辑',
                "            return {",
                '                "success": True,',
                '                "data": {},',
                '                "error_message": "",',
                '                "error_type": ""',
                "            }",
                "        except Exception as e:",
                f'            logger.error(f"{action} 执行失败: {{e}}")',
                "            return {",
                '                "success": False,',
                '                "data": None,',
                f'                "error_message": f"{action} 执行失败: {{str(e)}}",',
                f'                "error_type": "{action.title()}Error"',
                "            }",
                ""
            ])
        
        # 生成更新后的_action_handlers映射
        code_lines.extend([
            "    # 🤖 更新 _action_handlers 映射:",
            "    def _update_action_handlers(self):",
            '        """更新动作处理器映射"""',
            "        additional_handlers = {"
        ])
        
        for action in sorted(missing_handlers):
            method_name = f"_handle_{action}"
            code_lines.append(f'            "{action}": self.{method_name},')
        
        code_lines.extend([
            "        }",
            "        self._action_handlers.update(additional_handlers)",
            ""
        ])
        
        return "\n".join(code_lines)
    
    def auto_fix_handlers_mapping(self) -> bool:
        """自动修复处理器映射（仅添加缺失的映射到现有方法）"""
        try:
            validation = self.validate_handlers_consistency()
            missing_handlers = validation['missing_handlers']
            
            if not missing_handlers:
                logger.info("✅ 所有处理器映射都已正确配置")
                return True
            
            # 检查是否有对应的方法已经存在但未映射
            fixed_handlers = {}
            for action in missing_handlers:
                potential_method_names = [
                    f"_handle_{action}",
                    f"_{action}_handler", 
                    f"_{action}",
                    action
                ]
                
                for method_name in potential_method_names:
                    if hasattr(self.server_instance, method_name):
                        method = getattr(self.server_instance, method_name)
                        if callable(method):
                            fixed_handlers[action] = method
                            logger.info(f"✅ 自动映射 {action} -> {method_name}")
                            break
            
            if fixed_handlers:
                # 更新_action_handlers
                if hasattr(self.server_instance, '_action_handlers'):
                    self.server_instance._action_handlers.update(fixed_handlers)
                    logger.info(f"✅ 自动修复了 {len(fixed_handlers)} 个处理器映射")
                    return True
            
            remaining_missing = set(missing_handlers) - set(fixed_handlers.keys())
            if remaining_missing:
                logger.warning(f"⚠️ 仍有 {len(remaining_missing)} 个处理器需要手动实现: {remaining_missing}")
            
            return len(remaining_missing) == 0
            
        except Exception as e:
            logger.error(f"自动修复处理器映射失败: {e}")
            return False
    
    def generate_sync_report(self) -> str:
        """生成同步状态报告"""
        validation = self.validate_handlers_consistency()
        
        report_lines = [
            f"# Action Handlers 同步报告 - {self.server_id}",
            f"生成时间: {self.loader.config.get('metadata', {}).get('last_updated', 'unknown')}",
            "",
            "## 📊 同步状态概览",
            f"- 服务器ID: {self.server_id}",
            f"- 需要的动作: {len(validation['required_actions'])} 个",
            f"- 已实现的动作: {len(validation['implemented_actions'])} 个", 
            f"- 同步状态: {'✅ 完全同步' if validation['is_consistent'] else '❌ 不同步'}",
            ""
        ]
        
        if validation['missing_handlers']:
            report_lines.extend([
                "## ❌ 缺失的处理器",
                ""
            ])
            for action in sorted(validation['missing_handlers']):
                report_lines.append(f"- `{action}`: 需要实现 `_handle_{action}` 方法")
            report_lines.append("")
        
        if validation['extra_handlers']:
            report_lines.extend([
                "## ⚠️ 多余的处理器",
                ""
            ])
            for action in sorted(validation['extra_handlers']):
                report_lines.append(f"- `{action}`: 未在统一配置中定义")
            report_lines.append("")
        
        if validation['recommendations']:
            report_lines.extend([
                "## 💡 修复建议",
                ""
            ])
            for rec in validation['recommendations']:
                report_lines.append(f"- {rec}")
            report_lines.append("")
        
        # 处理器分析详情
        if validation['handler_analysis']:
            report_lines.extend([
                "## 🔍 处理器分析详情",
                ""
            ])
            for action, analysis in validation['handler_analysis'].items():
                status = "lambda" if analysis['is_lambda'] else "method"
                async_status = "async" if analysis['is_async'] else "sync"
                report_lines.append(f"- `{action}`: {status}, {async_status}, 参数: {analysis['parameters']}")
            
        return "\n".join(report_lines)


def create_synchronizer_for_server(server_instance) -> ActionHandlersSynchronizer:
    """为服务器实例创建同步器"""
    return ActionHandlersSynchronizer(server_instance)

def validate_all_servers_sync() -> Dict[str, Dict[str, Any]]:
    """验证所有服务器的同步状态"""
    # 这个函数需要在系统启动时调用，验证所有MCP服务器
    # 具体实现需要根据系统的服务器注册机制来完善
    logger.info("🔍 验证所有MCP服务器的处理器同步状态...")
    
    results = {}
    # TODO: 实现对所有注册服务器的验证
    # 这需要访问系统的服务器注册表
    
    return results