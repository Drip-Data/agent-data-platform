#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🔧 Agent Data Platform - 统一工具管理器
=====================================================

📋 核心功能：
- 统一管理所有工具ID和动作映射
- 解决系统中工具ID不一致的根本问题  
- 提供权威的工具定义和验证服务
- 避免在多个地方重复定义映射逻辑

⚠️  重要：本模块是工具管理的唯一权威来源！
🎯 目标：确保整个系统的工具ID和动作定义完全一致

作者：Agent Data Platform Team
创建时间：2025-06-25
版本：v1.0.0 - 初始统一版本
"""

import yaml
import logging
import os
from typing import Dict, List, Optional, Set, Any, Tuple
from pathlib import Path
import re

# Import memory staging tools
try:
    from tools.memory_staging_tool import (
        memory_write, memory_read, memory_list, 
        memory_search, memory_clear, memory_staging
    )
    MEMORY_STAGING_AVAILABLE = True
except ImportError:
    MEMORY_STAGING_AVAILABLE = False

# 设置日志
logger = logging.getLogger(__name__)

class UnifiedToolManager:
    """
    🌟 统一工具管理器
    
    职责：
    1. 加载和管理统一的工具定义配置
    2. 提供工具ID映射和验证服务
    3. 管理工具动作和参数定义
    4. 支持向后兼容的ID转换
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化统一工具管理器
        
        Args:
            config_path: 工具定义配置文件路径，默认使用标准位置
        """
        self.config_path = config_path or self._get_default_config_path()
        self.config: Dict[str, Any] = {}
        self._standard_ids: Set[str] = set()
        self._legacy_mapping: Dict[str, str] = {}
        self._tool_definitions: Dict[str, Dict] = {}
        
        # 加载配置
        self._load_config()
        
        logger.info(f"✅ 统一工具管理器初始化完成，管理 {len(self._standard_ids)} 个工具")
    
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        current_dir = Path(__file__).parent
        config_path = current_dir.parent / "config" / "unified_tool_mappings.yaml"
        return str(config_path)
    
    def _load_config(self) -> None:
        """
        🔄 加载统一工具映射配置
        
        从YAML配置文件中加载所有工具的ID和动作映射。
        """
        try:
            if not os.path.exists(self.config_path):
                raise FileNotFoundError(f"统一工具映射配置文件不存在: {self.config_path}")
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            
            # 加载工具ID映射
            tool_id_config = self.config.get('tool_id_mappings', {})
            self._standard_ids = set(tool_id_config.get('canonical_tool_ids', []))
            self._legacy_mapping = tool_id_config.get('tool_aliases', {})
            
            # 🔧 加载动作和参数定义 - 直接从MCP服务器定义加载
            self._tool_definitions = {}
            action_mappings = self.config.get('action_mappings', {})
            
            # 🔧 加载完整的工具参数定义
            tool_parameters = self.config.get('tool_parameters', {})

            for tool_id, mapping_info in action_mappings.items():
                if tool_id in self._standard_ids:
                    actions = {}
                    for action_name in mapping_info.get('canonical_actions', []):
                        # 🔧 从tool_parameters获取详细参数定义
                        params = tool_parameters.get(tool_id, {}).get(action_name, {})
                        actions[action_name] = {'parameters': params}
                    
                    self._tool_definitions[tool_id] = {
                        'id': tool_id,
                        'name': tool_id.replace('_', ' ').title(),
                        'description': f"Tool for {tool_id}",
                        'actions': actions
                    }

            logger.info(f"🔄 成功加载工具映射配置: {len(self._standard_ids)} 个标准工具")
            logger.debug(f"   - 标准工具ID: {sorted(self._standard_ids)}")
            logger.debug(f"   - 兼容映射: {len(self._legacy_mapping)} 个变体")
            
        except Exception as e:
            logger.error(f"❌ 加载工具映射配置失败: {e}")
            raise
    
    def _validate_config(self) -> None:
        """
        ✅ 验证配置文件的完整性和一致性
        
        检查项：
        - 标准ID与工具定义的一致性
        - 必需字段的完整性
        - 动作定义的有效性
        """
        # P2 暂时禁用验证，因为映射文件结构不同
        pass
    
    # ==================== 核心映射方法 ====================
    
    def get_standard_id(self, tool_id: str) -> str:
        """
        🔄 获取标准工具ID
        
        将任何形式的工具ID（包括旧版ID）转换为标准ID
        
        Args:
            tool_id: 输入的工具ID
            
        Returns:
            标准化后的工具ID
            
        Raises:
            ValueError: 如果工具ID无法识别
        """
        if not tool_id:
            raise ValueError("工具ID不能为空")
        
        # 先检查是否已经是标准ID
        if tool_id in self._standard_ids:
            logger.debug(f"🎯 工具ID已是标准格式: {tool_id}")
            return tool_id
        
        # 检查兼容性映射
        if tool_id in self._legacy_mapping:
            standard_id = self._legacy_mapping[tool_id]
            logger.debug(f"🔄 工具ID映射: {tool_id} -> {standard_id}")
            return standard_id
        
        # 尝试智能匹配（处理大小写、分隔符变体）
        smart_match = self._smart_match_tool_id(tool_id)
        if smart_match:
            logger.debug(f"🧠 智能匹配工具ID: {tool_id} -> {smart_match}")
            return smart_match
        
        # 如果都无法匹配，抛出错误
        available_ids = sorted(list(self._standard_ids) + list(self._legacy_mapping.keys()))
        raise ValueError(
            f"未知的工具ID: {tool_id}\n"
            f"可用的工具ID: {available_ids}"
        )
    
    def _smart_match_tool_id(self, tool_id: str) -> Optional[str]:
        """
        🧠 智能匹配工具ID
        
        处理常见的命名变体：
        - 大小写不敏感
        - 分隔符变体 (-, _, 空格)
        - 前后缀变体
        """
        # 规范化输入ID
        normalized_input = self._normalize_id(tool_id)
        
        # 检查标准ID的规范化版本
        for standard_id in self._standard_ids:
            if self._normalize_id(standard_id) == normalized_input:
                return standard_id
        
        # 检查兼容映射的规范化版本
        for legacy_id, standard_id in self._legacy_mapping.items():
            if self._normalize_id(legacy_id) == normalized_input:
                return standard_id
        
        return None
    
    def _normalize_id(self, tool_id: str) -> str:
        """规范化工具ID用于匹配"""
        # 转小写，移除常见分隔符和前后缀
        normalized = tool_id.lower()
        normalized = re.sub(r'[-_\s]+', '', normalized)
        normalized = re.sub(r'^(mcp|server)', '', normalized)
        normalized = re.sub(r'(mcp|server)$', '', normalized)
        return normalized
    
    def get_all_standard_ids(self) -> List[str]:
        """
        📋 获取所有标准工具ID列表
        
        Returns:
            按字母顺序排序的标准工具ID列表
        """
        return sorted(self._standard_ids)
    
    def _get_canonical_action(self, tool_id: str, action: str) -> str:
        """
        🔧 获取动作的标准名称（处理别名映射）
        
        Args:
            tool_id: 工具ID
            action: 动作名称（可能是别名）
            
        Returns:
            标准动作名称
        """
        try:
            from core.config.unified_mapping_manager import get_unified_mapping_manager
            mapping_manager = get_unified_mapping_manager()
            return mapping_manager.get_canonical_action(tool_id, action)
        except Exception as e:
            logger.debug(f"动作别名映射失败: {e}，使用原始动作名称")
            return action
    
    def is_valid_tool_id(self, tool_id: str) -> bool:
        """
        ✅ 检查工具ID是否有效
        
        Args:
            tool_id: 要检查的工具ID
            
        Returns:
            True表示有效，False表示无效
        """
        try:
            self.get_standard_id(tool_id)
            return True
        except ValueError:
            return False
    
    # ==================== 工具动作管理 ====================
    
    def get_tool_actions(self, tool_id: str) -> List[str]:
        """
        📋 获取工具支持的所有动作
        
        Args:
            tool_id: 工具ID（可以是任何格式）
            
        Returns:
            动作名称列表
        """
        standard_id = self.get_standard_id(tool_id)
        tool_def = self._tool_definitions.get(standard_id, {})
        actions = tool_def.get('actions', {})
        return list(actions.keys())
    
    def is_valid_action(self, tool_id: str, action: str) -> bool:
        """
        ✅ 检查工具动作是否有效（支持动作别名）
        
        Args:
            tool_id: 工具ID
            action: 动作名称（可以是别名）
            
        Returns:
            True表示有效，False表示无效
        """
        try:
            # 🔧 关键修复：集成动作别名映射
            canonical_action = self._get_canonical_action(tool_id, action)
            valid_actions = self.get_tool_actions(tool_id)
            return canonical_action in valid_actions
        except ValueError:
            return False
    
    def get_action_parameters(self, tool_id: str, action: str) -> Dict[str, Any]:
        """
        📋 获取动作的参数定义
        
        Args:
            tool_id: 工具ID
            action: 动作名称
            
        Returns:
            参数定义字典
        """
        standard_id = self.get_standard_id(tool_id)
        
        if not self.is_valid_action(tool_id, action):
            raise ValueError(f"工具 {standard_id} 不支持动作 {action}")
        
        tool_def = self._tool_definitions[standard_id]
        action_def = tool_def['actions'][action]
        return action_def.get('parameters', {})
    
    def get_required_parameters(self, tool_id: str, action: str) -> List[str]:
        """
        📋 获取动作的必需参数列表
        
        Args:
            tool_id: 工具ID  
            action: 动作名称
            
        Returns:
            必需参数名称列表
        """
        params = self.get_action_parameters(tool_id, action)
        required_params = []
        
        for param_name, param_def in params.items():
            if param_def.get('required', False):
                required_params.append(param_name)
        
        return required_params
    
    def get_default_action(self, tool_id: str) -> str:
        """
        🎯 获取工具的默认动作
        
        Args:
            tool_id: 工具ID
            
        Returns:
            默认动作名称
        """
        standard_id = self.get_standard_id(tool_id)
        
        # 从配置中获取推荐的默认动作
        llm_config = self.config.get('llm_tool_presentation', {})
        default_actions = llm_config.get('default_actions', {})
        
        if standard_id in default_actions:
            return default_actions[standard_id]
        
        # 如果没有配置，返回第一个动作
        actions = self.get_tool_actions(tool_id)
        if actions:
            return actions[0]
        
        raise ValueError(f"工具 {standard_id} 没有可用的动作")
    
    # ==================== 工具信息查询 ====================
    
    def get_tool_info(self, tool_id: str) -> Dict[str, Any]:
        """
        📋 获取工具的完整信息
        
        Args:
            tool_id: 工具ID
            
        Returns:
            工具信息字典
        """
        standard_id = self.get_standard_id(tool_id)
        tool_def = self._tool_definitions.get(standard_id, {})
        
        # 创建工具信息副本，避免意外修改原始配置
        tool_info = tool_def.copy()
        tool_info['standard_id'] = standard_id
        tool_info['action_count'] = len(tool_def.get('actions', {}))
        
        return tool_info
    
    def get_tool_display_name(self, tool_id: str) -> str:
        """
        🏷️ 获取工具的显示名称（用于LLM展示）
        
        Args:
            tool_id: 工具ID
            
        Returns:
            显示名称
        """
        standard_id = self.get_standard_id(tool_id)
        
        # 先从LLM展示配置中获取
        llm_config = self.config.get('llm_tool_presentation', {})
        display_names = llm_config.get('display_names', {})
        
        if standard_id in display_names:
            return display_names[standard_id]
        
        # 如果没有配置，使用工具定义中的名称
        tool_def = self._tool_definitions.get(standard_id, {})
        return tool_def.get('name', standard_id)
    
    def get_tools_for_llm(self) -> List[Dict[str, Any]]:
        """
        🤖 获取为LLM优化的工具列表
        
        按推荐顺序返回工具信息，包含LLM需要的关键信息
        
        Returns:
            LLM工具信息列表
        """
        llm_config = self.config.get('llm_tool_presentation', {})
        display_order = llm_config.get('display_order', self.get_all_standard_ids())
        
        tools = []
        for tool_id in display_order:
            if tool_id in self._tool_definitions:
                tool_info = {
                    'id': tool_id,
                    'name': self.get_tool_display_name(tool_id),
                    'description': self._tool_definitions[tool_id].get('description', ''),
                    'actions': self.get_tool_actions(tool_id),
                    'default_action': self.get_default_action(tool_id)
                }
                tools.append(tool_info)
        
        return tools
    
    # ==================== 内存暂存工具直接执行 ====================
    
    def is_memory_staging_tool(self, tool_id: str) -> bool:
        """检查是否为内存暂存工具"""
        try:
            standard_id = self.get_standard_id(tool_id)
            return standard_id == "memory_staging"
        except ValueError:
            return False
    
    def execute_memory_staging_action(self, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        直接执行内存暂存工具动作
        
        Args:
            action: 动作名称
            parameters: 参数字典
            
        Returns:
            执行结果
        """
        if not MEMORY_STAGING_AVAILABLE:
            return {
                "success": False,
                "error": "memory_staging_not_available",
                "message": "内存暂存工具不可用，请检查工具安装"
            }
        
        try:
            # 设置执行上下文
            current_step = parameters.get("_current_step")
            current_tool = parameters.get("_current_tool") 
            if current_step or current_tool:
                memory_staging.set_context(step=current_step, tool=current_tool)
            
            # 根据动作名称执行相应的函数
            if action == "memory_write":
                return memory_write(
                    key=parameters["key"],
                    value=parameters["value"],
                    data_type=parameters.get("data_type"),
                    tags=parameters.get("tags"),
                    ttl_hours=parameters.get("ttl_hours")
                )
            elif action == "memory_read":
                return memory_read(key=parameters["key"])
            elif action == "memory_list":
                return memory_list(include_values=parameters.get("include_values", False))
            elif action == "memory_search":
                return memory_search(
                    query=parameters["query"],
                    search_in_values=parameters.get("search_in_values", True)
                )
            elif action == "memory_clear":
                return memory_clear(key=parameters.get("key"))
            else:
                return {
                    "success": False,
                    "error": "unknown_action",
                    "message": f"未知的内存暂存动作: {action}"
                }
                
        except Exception as e:
            logger.error(f"❌ 执行内存暂存动作失败: {action}, 错误: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"执行内存暂存动作失败: {str(e)}"
            }
    
    def get_memory_staging_status(self) -> Dict[str, Any]:
        """获取内存暂存工具状态"""
        if not MEMORY_STAGING_AVAILABLE:
            return {
                "available": False,
                "error": "内存暂存工具不可用"
            }
        
        try:
            # 获取当前存储统计
            stats = memory_staging.list_all()
            return {
                "available": True,
                "storage_count": stats.get("total_count", 0),
                "max_entries": memory_staging.max_entries,
                "default_ttl_hours": memory_staging.default_ttl_hours
            }
        except Exception as e:
            return {
                "available": True,
                "error": f"获取状态失败: {str(e)}"
            }
    
    # ==================== 批量操作方法 ====================
    
    def validate_tool_call(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        🔍 验证工具调用的完整性
        
        Args:
            tool_id: 工具ID
            action: 动作名称
            parameters: 参数字典
            
        Returns:
            (是否有效, 错误信息列表)
        """
        errors = []
        
        try:
            # 验证工具ID
            standard_id = self.get_standard_id(tool_id)
        except ValueError as e:
            errors.append(str(e))
            return False, errors
        
        # 🔧 关键修复：验证动作（支持别名）
        canonical_action = self._get_canonical_action(standard_id, action)
        if not self.is_valid_action(standard_id, action):
            valid_actions = self.get_tool_actions(standard_id)
            if action != canonical_action:
                errors.append(f"工具 {standard_id} 不支持动作 {action}（映射为 {canonical_action}），可用动作: {valid_actions}")
            else:
                errors.append(f"工具 {standard_id} 不支持动作 {action}，可用动作: {valid_actions}")
            return False, errors
        
        # 验证参数（使用标准动作名称）
        try:
            required_params = self.get_required_parameters(standard_id, canonical_action)
            param_definitions = self.get_action_parameters(standard_id, canonical_action)
            
            # 检查必需参数
            missing_params = []
            for required_param in required_params:
                if required_param not in parameters:
                    missing_params.append(required_param)
            
            if missing_params:
                errors.append(f"缺少必需参数: {missing_params}")
            
            # 检查无效参数
            valid_param_names = set(param_definitions.keys())
            invalid_params = set(parameters.keys()) - valid_param_names
            if invalid_params:
                errors.append(f"无效参数: {list(invalid_params)}，有效参数: {list(valid_param_names)}")
        
        except Exception as e:
            errors.append(f"参数验证失败: {e}")
        
        return len(errors) == 0, errors
    
    def normalize_tool_call(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔧 规范化工具调用
        
        将工具调用转换为标准格式
        
        Args:
            tool_id: 工具ID
            action: 动作名称  
            parameters: 参数字典
            
        Returns:
            规范化后的工具调用字典
        """
        standard_id = self.get_standard_id(tool_id)
        
        # 验证调用有效性
        is_valid, errors = self.validate_tool_call(standard_id, action, parameters)
        if not is_valid:
            raise ValueError(f"工具调用无效: {'; '.join(errors)}")
        
        return {
            'tool_id': standard_id,
            'action': action,
            'parameters': parameters
        }
    
    # ==================== 统计和诊断方法 ====================
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        📊 获取工具管理统计信息
        
        Returns:
            统计信息字典
        """
        total_actions = sum(len(tool['actions']) for tool in self._tool_definitions.values())
        
        return {
            'total_tools': len(self._standard_ids),
            'total_legacy_mappings': len(self._legacy_mapping),
            'total_actions': total_actions,
            'config_file': self.config_path,
            'config_version': self.config.get('metadata', {}).get('version', 'unknown'),
            'tools_by_action_count': {
                tool_id: len(tool_def['actions'])
                for tool_id, tool_def in self._tool_definitions.items()
            }
        }
    
    def diagnose_tool_issues(self) -> Dict[str, List[str]]:
        """
        🔍 诊断工具配置问题
        
        Returns:
            问题诊断结果
        """
        issues = {
            'warnings': [],
            'suggestions': [],
            'info': []
        }
        
        # 检查是否有工具没有默认动作配置
        llm_config = self.config.get('llm_tool_presentation', {})
        default_actions = llm_config.get('default_actions', {})
        
        for tool_id in self._standard_ids:
            if tool_id not in default_actions:
                issues['suggestions'].append(f"建议为工具 {tool_id} 配置默认动作")
        
        # 检查动作数量异常的工具
        for tool_id, tool_def in self._tool_definitions.items():
            action_count = len(tool_def.get('actions', {}))
            if action_count == 0:
                issues['warnings'].append(f"工具 {tool_id} 没有定义任何动作")
            elif action_count > 20:
                issues['info'].append(f"工具 {tool_id} 定义了 {action_count} 个动作，功能丰富")
        
        return issues


# ==================== 全局实例和便捷函数 ====================

# 全局统一工具管理器实例
_global_tool_manager: Optional[UnifiedToolManager] = None

def get_tool_manager() -> UnifiedToolManager:
    """
    🌟 获取全局统一工具管理器实例
    
    使用单例模式，确保整个应用中使用相同的工具管理器
    
    Returns:
        UnifiedToolManager实例
    """
    global _global_tool_manager
    if _global_tool_manager is None:
        _global_tool_manager = UnifiedToolManager()
    return _global_tool_manager

def reset_tool_manager() -> None:
    """
    🔄 重置全局工具管理器（主要用于测试）
    """
    global _global_tool_manager
    _global_tool_manager = None

# 便捷函数
def get_standard_tool_id(tool_id: str) -> str:
    """便捷函数：获取标准工具ID"""
    return get_tool_manager().get_standard_id(tool_id)

def validate_tool_call(tool_id: str, action: str, parameters: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """便捷函数：验证工具调用"""
    return get_tool_manager().validate_tool_call(tool_id, action, parameters)

def get_tool_actions(tool_id: str) -> List[str]:
    """便捷函数：获取工具动作列表"""
    return get_tool_manager().get_tool_actions(tool_id)


if __name__ == "__main__":
    # 简单的命令行测试
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    try:
        manager = UnifiedToolManager()
        
        if len(sys.argv) > 1:
            test_tool_id = sys.argv[1]
            print(f"\n🔍 测试工具ID: {test_tool_id}")
            
            try:
                standard_id = manager.get_standard_id(test_tool_id)
                print(f"✅ 标准ID: {standard_id}")
                
                actions = manager.get_tool_actions(standard_id)
                print(f"📋 支持的动作 ({len(actions)}): {actions}")
                
                default_action = manager.get_default_action(standard_id)
                print(f"🎯 默认动作: {default_action}")
                
            except ValueError as e:
                print(f"❌ 错误: {e}")
        else:
            # 显示统计信息
            stats = manager.get_statistics()
            print("\n📊 工具管理统计:")
            for key, value in stats.items():
                print(f"  {key}: {value}")
            
            print(f"\n🔧 所有标准工具ID:")
            for tool_id in manager.get_all_standard_ids():
                action_count = len(manager.get_tool_actions(tool_id))
                display_name = manager.get_tool_display_name(tool_id)
                print(f"  - {tool_id} ({display_name}): {action_count} 个动作")
    
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        sys.exit(1)