#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
JSON参数解析工具
提供统一的JSON格式参数解析和向后兼容功能
"""

import json
import logging
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ParameterParseResult:
    """JSON参数解析结果"""
    is_valid: bool
    parsed_params: Dict[str, Any]
    errors: List[str]
    suggestions: List[str]
    original_format: str  # 'json' or 'legacy'

class JSONParameterParser:
    """
    JSON参数解析工具
    支持新的JSON格式和旧格式的向后兼容
    """
    
    def __init__(self, tool_manager=None):
        """
        初始化解析器
        
        Args:
            tool_manager: UnifiedToolManager实例，用于获取工具定义
        """
        self.tool_manager = tool_manager
        logger.debug("🔧 JSON参数解析器已初始化")
    
    def parse_tool_parameters(self, tool_id: str, action: str, raw_input: Union[str, dict]) -> ParameterParseResult:
        """
        解析工具参数，支持JSON格式和向后兼容
        
        Args:
            tool_id: 工具ID
            action: 动作名称
            raw_input: 原始输入 (JSON字符串、dict或旧格式文本)
            
        Returns:
            ParameterParseResult: 解析和验证结果
        """
        if not self.tool_manager:
            return ParameterParseResult(
                is_valid=False,
                parsed_params={},
                errors=["工具管理器未初始化"],
                suggestions=["请提供有效的工具管理器实例"],
                original_format="unknown"
            )
        
        try:
            # 标准化工具ID和动作
            standard_id = self.tool_manager.get_standard_id(tool_id)
            canonical_action = self.tool_manager._get_canonical_action(standard_id, action)
            
            # 验证工具和动作
            if not self.tool_manager.is_valid_action(standard_id, action):
                return ParameterParseResult(
                    is_valid=False,
                    parsed_params={},
                    errors=[f"工具 {standard_id} 不支持动作 {action}"],
                    suggestions=[f"支持的动作: {self.tool_manager.get_tool_actions(standard_id)}"],
                    original_format="unknown"
                )
            
            # 解析输入
            if isinstance(raw_input, dict):
                # 已经是字典格式
                return self._validate_json_parameters(standard_id, canonical_action, raw_input, "json")
            elif isinstance(raw_input, str):
                if self._looks_like_json(raw_input):
                    return self._parse_json_format(standard_id, canonical_action, raw_input)
                else:
                    return self._parse_legacy_format(standard_id, canonical_action, raw_input)
            else:
                return ParameterParseResult(
                    is_valid=False,
                    parsed_params={},
                    errors=[f"不支持的参数类型: {type(raw_input)}"],
                    suggestions=["参数必须是JSON字符串或字典"],
                    original_format="unknown"
                )
                
        except Exception as e:
            logger.error(f"参数解析失败: {e}")
            return ParameterParseResult(
                is_valid=False,
                parsed_params={},
                errors=[f"参数解析失败: {str(e)}"],
                suggestions=["请检查工具ID和参数格式"],
                original_format="unknown"
            )
    
    def _looks_like_json(self, text: str) -> bool:
        """判断输入是否为JSON格式"""
        text = text.strip()
        return (text.startswith('{') and text.endswith('}')) or \
               (text.startswith('[') and text.endswith(']'))
    
    def _parse_json_format(self, tool_id: str, action: str, json_input: str) -> ParameterParseResult:
        """解析JSON格式输入"""
        try:
            params = json.loads(json_input)
            if not isinstance(params, dict):
                return ParameterParseResult(
                    is_valid=False,
                    parsed_params={},
                    errors=["参数必须是JSON对象格式"],
                    suggestions=[self._generate_json_example(tool_id, action)],
                    original_format="json"
                )
            
            return self._validate_json_parameters(tool_id, action, params, "json")
            
        except json.JSONDecodeError as e:
            return ParameterParseResult(
                is_valid=False,
                parsed_params={},
                errors=[f"JSON格式错误: {str(e)}"],
                suggestions=[self._generate_json_example(tool_id, action)],
                original_format="json"
            )
    
    def _parse_legacy_format(self, tool_id: str, action: str, text_input: str) -> ParameterParseResult:
        """解析旧格式输入并转换为JSON格式"""
        text_input = text_input.strip()
        
        # 获取主要参数名称
        primary_param = self._get_primary_parameter(tool_id, action)
        if not primary_param:
            return ParameterParseResult(
                is_valid=False,
                parsed_params={},
                errors=[f"工具 {tool_id}.{action} 需要多个参数，请使用JSON格式"],
                suggestions=[self._generate_json_example(tool_id, action)],
                original_format="legacy"
            )
        
        # 转换为JSON格式
        params = {primary_param: text_input}
        
        return self._validate_json_parameters(tool_id, action, params, "legacy")
    
    def _get_primary_parameter(self, tool_id: str, action: str) -> Optional[str]:
        """获取工具的主要参数名称"""
        try:
            param_definitions = self.tool_manager.get_action_parameters(tool_id, action)
            required_params = [name for name, param_def in param_definitions.items() 
                              if param_def.get('required', False)]
            
            # 如果只有一个必需参数，返回它
            if len(required_params) == 1:
                return required_params[0]
            
            # 否则使用预定义的主要参数映射
            primary_param_mapping = {
                ("browser_use", "browser_use_execute_task"): "task",
                ("browser_use", "browser_search_google"): "query",
                ("browser_use", "browser_navigate"): "url",
                ("browser_use", "browser_extract_content"): "goal",
                ("microsandbox", "microsandbox_execute"): "code",
                ("deepsearch", "research"): "question"
            }
            
            return primary_param_mapping.get((tool_id, action))
            
        except Exception as e:
            logger.debug(f"获取主要参数失败: {e}")
            return None
    
    def _validate_json_parameters(self, tool_id: str, action: str, params: Dict[str, Any], 
                                 original_format: str) -> ParameterParseResult:
        """验证JSON参数"""
        try:
            # 使用工具管理器的validate_tool_call方法
            is_valid, errors = self.tool_manager.validate_tool_call(tool_id, action, params)
            
            suggestions = []
            if not is_valid:
                suggestions.append(self._generate_json_example(tool_id, action))
            
            return ParameterParseResult(
                is_valid=is_valid,
                parsed_params=params if is_valid else {},
                errors=errors,
                suggestions=suggestions,
                original_format=original_format
            )
            
        except Exception as e:
            logger.error(f"参数验证失败: {e}")
            return ParameterParseResult(
                is_valid=False,
                parsed_params={},
                errors=[f"参数验证失败: {str(e)}"],
                suggestions=[self._generate_json_example(tool_id, action)],
                original_format=original_format
            )
    
    def _generate_json_example(self, tool_id: str, action: str) -> str:
        """生成JSON格式示例"""
        try:
            param_definitions = self.tool_manager.get_action_parameters(tool_id, action)
            example_params = {}
            
            # 生成示例值
            for param_name, param_def in param_definitions.items():
                param_type = param_def.get("type", "string")
                required = param_def.get("required", False)
                
                if required:  # 只包含必需参数的示例
                    if param_type == "string":
                        if "task" in param_name:
                            example_params[param_name] = "搜索Python教程并打开第一个结果"
                        elif "query" in param_name:
                            example_params[param_name] = "Python机器学习教程"
                        elif "url" in param_name:
                            example_params[param_name] = "https://www.google.com"
                        elif "goal" in param_name:
                            example_params[param_name] = "提取所有产品信息"
                        elif "code" in param_name:
                            example_params[param_name] = "print('Hello World')"
                        elif "question" in param_name:
                            example_params[param_name] = "Python异步编程最佳实践"
                        else:
                            example_params[param_name] = f"示例{param_name}"
                    elif param_type == "integer":
                        example_params[param_name] = 10 if "steps" in param_name else 1
                    elif param_type == "boolean":
                        example_params[param_name] = True
                    elif param_type == "array":
                        example_params[param_name] = []
            
            # 为browser_use_execute_task添加常用可选参数示例
            if tool_id == "browser_use" and action == "browser_use_execute_task":
                example_params["max_steps"] = 10
                example_params["use_vision"] = True
            
            return f"建议JSON格式: {json.dumps(example_params, ensure_ascii=False)}"
            
        except Exception as e:
            logger.debug(f"生成JSON示例失败: {e}")
            return "建议使用JSON格式: {\"参数名\": \"参数值\"}"


# 便捷函数
def parse_tool_parameters(tool_manager, tool_id: str, action: str, raw_input: Union[str, dict]) -> ParameterParseResult:
    """
    便捷函数：解析工具参数
    
    Args:
        tool_manager: UnifiedToolManager实例
        tool_id: 工具ID
        action: 动作名称
        raw_input: 原始输入
        
    Returns:
        ParameterParseResult: 解析结果
    """
    parser = JSONParameterParser(tool_manager)
    return parser.parse_tool_parameters(tool_id, action, raw_input)


if __name__ == "__main__":
    # 测试代码需要实际的工具管理器实例
    print("🔧 JSON参数解析器测试")
    print("需要在实际环境中配合UnifiedToolManager测试")