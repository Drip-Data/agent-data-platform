"""
🔧 P1修复2: 统一映射管理器
管理所有工具ID、动作和参数映射的单一配置源
"""

import yaml
import logging
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import hashlib
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class MappingRule:
    """映射规则"""
    source: str
    target: str
    rule_type: str  # 'tool_id', 'action', 'parameter'
    tool_context: Optional[str] = None
    validation_required: bool = True

@dataclass 
class ValidationResult:
    """验证结果"""
    is_valid: bool
    original_value: str
    mapped_value: str
    mapping_type: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

class UnifiedMappingManager:
    """统一映射管理器 - 单一配置源管理"""
    
    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "unified_tool_mappings.yaml"
        
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self._last_modified = 0
        self._config_hash = ""
        
        # 缓存映射表以提高性能
        self._tool_id_cache: Dict[str, str] = {}
        self._action_cache: Dict[str, Dict[str, str]] = {}
        self._parameter_cache: Dict[str, Dict[str, str]] = {}
        
        # 加载配置
        self._load_config()
    
    def _load_config(self) -> bool:
        """加载统一配置文件"""
        try:
            if not self.config_path.exists():
                logger.error(f"❌ 统一映射配置文件不存在: {self.config_path}")
                return False
            
            # 检查文件修改时间
            current_modified = self.config_path.stat().st_mtime
            if current_modified == self._last_modified:
                return True  # 文件未修改，使用缓存
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f)
            
            # 验证配置结构
            if not self._validate_config_structure():
                return False
            
            # 重建缓存
            self._rebuild_caches()
            
            # 更新元数据
            self._last_modified = current_modified
            self._config_hash = self._calculate_config_hash()
            
            logger.info(f"✅ 统一映射配置已加载: {self.config_path}")
            logger.info(f"🔒 配置哈希: {self._config_hash}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 加载统一映射配置失败: {e}")
            return False
    
    def _validate_config_structure(self) -> bool:
        """验证配置文件结构"""
        required_sections = [
            'tool_id_mappings',
            'action_mappings', 
            'parameter_mappings',
            'error_corrections',
            'validation_rules'
        ]
        
        for section in required_sections:
            if section not in self._config:
                logger.error(f"❌ 配置文件缺少必需部分: {section}")
                return False
        
        return True
    
    def _rebuild_caches(self):
        """重建映射缓存"""
        # 重建工具ID缓存
        self._tool_id_cache.clear()
        tool_aliases = self._config.get('tool_id_mappings', {}).get('tool_aliases', {})
        for alias, canonical in tool_aliases.items():
            self._tool_id_cache[alias] = canonical
        
        # 重建动作缓存
        self._action_cache.clear()
        action_mappings = self._config.get('action_mappings', {})
        for tool_id, tool_actions in action_mappings.items():
            action_aliases = tool_actions.get('action_aliases', {})
            self._action_cache[tool_id] = action_aliases
        
        # 重建参数缓存
        self._parameter_cache.clear()
        parameter_mappings = self._config.get('parameter_mappings', {})
        
        # 通用参数别名
        common_aliases = parameter_mappings.get('common_aliases', {})
        self._parameter_cache['_common'] = common_aliases
        
        # 工具特定参数映射
        tool_specific = parameter_mappings.get('tool_specific', {})
        for tool_id, tool_params in tool_specific.items():
            self._parameter_cache[tool_id] = tool_params
    
    def _calculate_config_hash(self) -> str:
        """计算配置哈希值"""
        config_str = yaml.dump(self._config, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()[:8]
    
    def get_canonical_tool_id(self, tool_id: str) -> str:
        """获取规范化的工具ID"""
        # 刷新配置（如果需要）
        self._load_config()
        
        # 如果已经是规范ID，直接返回
        canonical_ids = self._config.get('tool_id_mappings', {}).get('canonical_tool_ids', [])
        if tool_id in canonical_ids:
            return tool_id
        
        # 查找别名映射
        return self._tool_id_cache.get(tool_id, tool_id)
    
    def get_canonical_action(self, tool_id: str, action: str) -> str:
        """获取规范化的动作名称"""
        self._load_config()
        
        # 先获取规范化的工具ID
        canonical_tool_id = self.get_canonical_tool_id(tool_id)
        
        # 检查是否已经是规范动作
        action_config = self._config.get('action_mappings', {}).get(canonical_tool_id, {})
        canonical_actions = action_config.get('canonical_actions', [])
        
        if action in canonical_actions:
            return action
        
        # 查找动作别名映射
        action_aliases = self._action_cache.get(canonical_tool_id, {})
        return action_aliases.get(action, action)
    
    def get_canonical_parameter(self, tool_id: str, parameter: str) -> str:
        """获取规范化的参数名称"""
        self._load_config()
        
        # 先获取规范化的工具ID
        canonical_tool_id = self.get_canonical_tool_id(tool_id)
        
        # 优先查找工具特定的参数映射
        tool_params = self._parameter_cache.get(canonical_tool_id, {})
        if parameter in tool_params:
            return tool_params[parameter]
        
        # 查找通用参数别名
        common_params = self._parameter_cache.get('_common', {})
        return common_params.get(parameter, parameter)
    
    def validate_tool_action_combination(self, tool_id: str, action: str) -> ValidationResult:
        """验证工具动作组合"""
        self._load_config()
        
        result = ValidationResult(
            is_valid=False,
            original_value=f"{tool_id}.{action}",
            mapped_value="",
            mapping_type="tool_action_combination"
        )
        
        try:
            # 获取规范化的工具ID和动作
            canonical_tool_id = self.get_canonical_tool_id(tool_id)
            canonical_action = self.get_canonical_action(tool_id, action)
            
            result.mapped_value = f"{canonical_tool_id}.{canonical_action}"
            
            # 检查是否为弃用的组合
            deprecated_combinations = self._config.get('validation_rules', {}).get('deprecated_combinations', [])
            for dep_combo in deprecated_combinations:
                if (dep_combo.get('tool_id') == canonical_tool_id and 
                    dep_combo.get('action') == action):
                    
                    replacement = dep_combo.get('replacement', {})
                    replacement_action = replacement.get('action', canonical_action)
                    
                    result.warnings.append(
                        f"动作 '{action}' 已弃用，建议使用 '{replacement_action}'"
                    )
                    result.mapped_value = f"{canonical_tool_id}.{replacement_action}"
                    break
            
            # 检查是否为有效组合
            action_config = self._config.get('action_mappings', {}).get(canonical_tool_id, {})
            canonical_actions = action_config.get('canonical_actions', [])
            action_aliases = action_config.get('action_aliases', {})
            
            all_valid_actions = set(canonical_actions + list(action_aliases.keys()))
            
            if canonical_action in canonical_actions or action in all_valid_actions:
                result.is_valid = True
            else:
                result.errors.append(
                    f"工具 '{canonical_tool_id}' 不支持动作 '{action}'"
                )
                
                # 建议相似的动作
                suggestions = self._find_similar_actions(canonical_tool_id, action)
                if suggestions:
                    result.warnings.append(f"建议的动作: {suggestions}")
            
        except Exception as e:
            result.errors.append(f"验证异常: {e}")
        
        return result
    
    def _find_similar_actions(self, tool_id: str, action: str) -> List[str]:
        """查找相似的动作名称"""
        action_config = self._config.get('action_mappings', {}).get(tool_id, {})
        canonical_actions = action_config.get('canonical_actions', [])
        action_aliases = action_config.get('action_aliases', {})
        
        all_actions = canonical_actions + list(action_aliases.keys())
        
        # 简单的相似性匹配（基于子字符串）
        suggestions = []
        action_lower = action.lower()
        
        for available_action in all_actions:
            if (action_lower in available_action.lower() or 
                available_action.lower() in action_lower):
                suggestions.append(available_action)
        
        return suggestions[:3]  # 最多返回3个建议
    
    def get_required_parameters(self, tool_id: str, action: str) -> List[str]:
        """获取指定工具动作的必需参数"""
        self._load_config()
        
        canonical_tool_id = self.get_canonical_tool_id(tool_id)
        canonical_action = self.get_canonical_action(tool_id, action)
        
        # 查找验证规则中的必需参数
        validation_rules = self._config.get('validation_rules', {})
        required_combinations = validation_rules.get('required_combinations', [])
        
        for combo in required_combinations:
            if (combo.get('tool_id') == canonical_tool_id and 
                combo.get('action') == canonical_action):
                return combo.get('required_params', [])
        
        return []
    
    def auto_correct_request(self, tool_id: str, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """自动修正请求"""
        self._load_config()
        
        corrected_request = {
            'tool_id': self.get_canonical_tool_id(tool_id),
            'action': self.get_canonical_action(tool_id, action),
            'parameters': {}
        }
        
        # 修正参数名称
        for param_name, param_value in parameters.items():
            canonical_param = self.get_canonical_parameter(tool_id, param_name)
            corrected_request['parameters'][canonical_param] = param_value
        
        return corrected_request
    
    def get_error_correction(self, error_message: str) -> Optional[Dict[str, Any]]:
        """根据错误消息获取修正建议"""
        self._load_config()
        
        error_corrections = self._config.get('error_corrections', {})
        
        # 检查动作错误
        action_errors = error_corrections.get('action_errors', {})
        for error_pattern, correction in action_errors.items():
            if error_pattern in error_message:
                return {
                    'type': 'action_error',
                    'correction': correction
                }
        
        # 检查参数错误
        parameter_errors = error_corrections.get('parameter_errors', {})
        for error_pattern, correction in parameter_errors.items():
            if error_pattern in error_message:
                return {
                    'type': 'parameter_error',
                    'correction': correction
                }
        
        return None
    
    def get_config_metadata(self) -> Dict[str, Any]:
        """获取配置元数据"""
        self._load_config()
        
        metadata = self._config.get('metadata', {})
        metadata.update({
            'current_hash': self._config_hash,
            'last_loaded': datetime.now().isoformat(),
            'config_path': str(self.config_path)
        })
        
        return metadata
    
    def export_mapping_summary(self) -> Dict[str, Any]:
        """导出映射摘要（用于调试和文档）"""
        self._load_config()
        
        return {
            'tool_id_mappings': {
                'canonical_count': len(self._config.get('tool_id_mappings', {}).get('canonical_tool_ids', [])),
                'alias_count': len(self._tool_id_cache)
            },
            'action_mappings': {
                'tool_count': len(self._action_cache),
                'total_aliases': sum(len(aliases) for aliases in self._action_cache.values())
            },
            'parameter_mappings': {
                'common_aliases': len(self._parameter_cache.get('_common', {})),
                'tool_specific_count': len([k for k in self._parameter_cache.keys() if k != '_common'])
            },
            'validation_rules': {
                'required_combinations': len(self._config.get('validation_rules', {}).get('required_combinations', [])),
                'deprecated_combinations': len(self._config.get('validation_rules', {}).get('deprecated_combinations', []))
            },
            'metadata': self.get_config_metadata()
        }

# 全局实例
_unified_mapping_manager = None

def get_unified_mapping_manager() -> UnifiedMappingManager:
    """获取统一映射管理器的全局实例"""
    global _unified_mapping_manager
    if _unified_mapping_manager is None:
        _unified_mapping_manager = UnifiedMappingManager()
    return _unified_mapping_manager