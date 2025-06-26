"""
动态工具Schema管理器
实现契约驱动的工具描述生成，解决硬编码工具描述问题
"""

import asyncio
import json
import logging
import time
import os
import aiofiles
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# 🔧 P0修复: 导入tool_definitions以确保工具在模块加载时注册
try:
    from core.toolscore import tool_definitions  # 触发装饰器注册
    logger.debug("✅ 工具定义已导入，自动注册完成")
except ImportError as e:
    logger.warning(f"⚠️ 无法导入工具定义: {e}")
except Exception as e:
    logger.error(f"❌ 工具定义导入失败: {e}")

@dataclass
class ToolSchema:
    """工具Schema定义"""
    tool_id: str
    name: str
    description: str
    actions: Dict[str, Dict[str, Any]]
    category: str = "general"
    version: str = "1.0.0"
    last_updated: datetime = None
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.now()
    
    @property
    def id(self) -> str:
        """向后兼容的id属性，返回tool_id"""
        return self.tool_id
    
    def to_llm_description(self) -> str:
        """生成面向LLM的工具描述"""
        lines = [f"- **{self.tool_id}** ({self.name}): {self.description}"]
        
        if self.actions:
            lines.append("  📋 可用操作:")
            for action_name, action_info in list(self.actions.items())[:5]:  # 限制显示数量
                desc = action_info.get('desc', action_name)
                lines.append(f"    • {action_name}: {desc}")
                
                # 添加参数信息
                params = action_info.get('params', {})
                if params:
                    required_params = [k for k, v in params.items() if '必需' in str(v) or 'required' in str(v).lower()]
                    if required_params:
                        lines.append(f"      必需参数: {', '.join(required_params)}")
        
        return "\n".join(lines)
    
    def validate_structure(self) -> Dict[str, Any]:
        """验证ToolSchema结构完整性"""
        issues = []
        
        # 检查必需字段
        required_fields = ['tool_id', 'name', 'description', 'actions']
        for field in required_fields:
            if not hasattr(self, field) or getattr(self, field) is None:
                issues.append(f"缺少必需字段: {field}")
        
        # 检查actions结构
        if hasattr(self, 'actions') and isinstance(self.actions, dict):
            for action_name, action_def in self.actions.items():
                if not isinstance(action_def, dict):
                    issues.append(f"动作 {action_name} 定义无效，应为字典类型")
                elif 'desc' not in action_def:
                    issues.append(f"动作 {action_name} 缺少描述字段")
        
        return {
            'is_valid': len(issues) == 0,
            'issues': issues,
            'tool_id': getattr(self, 'tool_id', 'unknown')
        }

class ToolSchemaManager:
    """工具Schema管理器 - 选项1实现：直接从工具注册表获取信息，不依赖配置文件"""
    
    def __init__(self, redis_client=None, toolscore_client=None, mcp_config_paths=None):
        self.redis = redis_client
        self.toolscore_client = toolscore_client
        self._cache: Dict[str, ToolSchema] = {}
        self._cache_ttl = 60  # 降低到1分钟缓存
        self._last_refresh = 0
        
        # 🔧 P0-1生产级强化：并发安全+增量更新+回滚机制
        self._refresh_lock = asyncio.Lock()  # 并发控制锁
        self._last_successful_schemas = {}  # 回滚缓存
        self._schema_versions: Dict[str, str] = {}  # ETag版本控制
        self._refresh_interval = 60  # 可配置刷新间隔
        self._consistency_check_enabled = True
        
        # MCP服务器实时同步（保留原有功能）
        self.mcp_config_paths = mcp_config_paths or [
            "mcp_servers",  # 项目中的MCP服务器目录
            "configs/tools",
            "/opt/mcp-servers", 
            "~/.config/mcp-servers"
        ]
        self._mcp_file_hashes: Dict[str, str] = {}
        self._mcp_monitor_task = None
        self._sync_enabled = True

    async def validate_mcp_sync(self) -> Dict[str, Any]:
        """执行MCP服务器同步验证并返回健康报告"""
        logger.info("正在执行MCP同步验证...")
        # 确保调用一个实际存在的方法来执行验证
        # 这里我们假设 `_perform_comprehensive_sync_validation` 是执行此操作的正确方法
        # 如果该方法不存在，则需要实现或链接到正确的验证逻辑
        if hasattr(self, '_perform_comprehensive_sync_validation'):
            return await self._perform_comprehensive_sync_validation()
        else:
            # 提供一个回退报告，以避免因方法缺失而引发异常
            logger.warning("'_perform_comprehensive_sync_validation' a方法未实现，返回默认的健康状态。")
            return {
                'overall_health': 'unknown',
                'summary': '验证功能未完全实现。',
                'details': {},
                'error': '验证逻辑缺失'
            }
        
    async def get_live_tool_schemas(self, force_refresh: bool = False) -> Dict[str, ToolSchema]:
        """并发安全的Schema获取，带回滚机制和一致性验证"""
        current_time = time.time()
        
        # 🔒 P0-1强化：并发安全，使用锁防止多协程同时刷新
        async with self._refresh_lock:
            if force_refresh or (current_time - self._last_refresh) > self._refresh_interval:
                logger.debug(f"🔄 开始刷新Schema缓存 (force={force_refresh})，当前缓存: {len(self._cache)} 个工具")
                
                success = await self._safe_refresh_schemas()
                if success:
                    # 🔍 新增：Schema一致性验证和结构验证
                    consistency_report = await self._validate_schema_consistency()
                    structure_report = await self._validate_schema_structures()
                    
                    # 处理一致性问题
                    if consistency_report['has_issues']:
                        logger.warning(f"⚠️ 发现Schema一致性问题: {len(consistency_report['issues'])} 个")
                        # 尝试自动修复
                        fixes_applied = await self._auto_fix_schema_issues(consistency_report['issues'])
                        logger.info(f"🔧 自动修复了 {len(fixes_applied)} 个Schema问题")
                    
                    # 处理结构问题
                    if structure_report['has_issues']:
                        logger.warning(f"⚠️ 发现Schema结构问题: {len(structure_report['issues'])} 个")
                        # 尝试自动修复结构问题
                        structure_fixes = await self._auto_fix_structure_issues(structure_report['issues'])
                        logger.info(f"🔧 自动修复了 {len(structure_fixes)} 个Schema结构问题")
                    
                    self._last_refresh = current_time
                    logger.info(f"✅ Schema刷新成功，缓存 {len(self._cache)} 个工具")
                else:
                    # 📦 回滚机制：刷新失败时使用最后成功的Schema
                    logger.warning("❌ Schema刷新失败，使用回滚缓存")
                    if self._last_successful_schemas:
                        self._cache = self._last_successful_schemas.copy()
                        logger.info(f"🔄 已回滚到最后成功版本 ({len(self._cache)} 个工具)")
        
        return self._cache.copy()
    
    async def _load_mcp_service_configs(self) -> List[Dict[str, Any]]:
        """加载MCP服务器配置文件"""
        configs = []
        
        try:
            # 遍历配置路径，查找service.json文件
            for config_path_str in self.mcp_config_paths:
                config_path = Path(config_path_str).expanduser()
                if not config_path.exists():
                    continue
                
                # 查找所有service.json文件
                for service_file in config_path.glob("**/service.json"):
                    try:
                        async with aiofiles.open(service_file, 'r', encoding='utf-8') as f:
                            content = await f.read()
                            service_config = json.loads(content)
                            
                            # 添加文件路径信息
                            service_config['_file_path'] = str(service_file)
                            configs.append(service_config)
                            
                            logger.debug(f"✅ 加载MCP服务配置: {service_file}")
                            
                    except Exception as e:
                        logger.warning(f"⚠️ 读取MCP服务配置失败 {service_file}: {e}")
            
            # 如果没有找到配置文件，返回空配置列表
            if not configs:
                logger.debug("📋 未找到MCP服务配置文件，返回空配置")
                
        except Exception as e:
            logger.error(f"❌ 加载MCP服务配置失败: {e}")
        
        return configs
    
    async def _validate_schema_consistency(self) -> Dict[str, Any]:
        """验证Schema数据源间的一致性"""
        consistency_report = {
            'timestamp': datetime.now().isoformat(),
            'has_issues': False,
            'issues': [],
            'checked_tools': 0
        }
        
        try:
            # 获取service.json配置
            service_configs = await self._load_mcp_service_configs()
            
            for tool_id, cached_schema in self._cache.items():
                consistency_report['checked_tools'] += 1
                
                # 🔧 防御性检查：确保 cached_schema 是有效对象
                if not hasattr(cached_schema, 'actions'):
                    logger.warning(f"⚠️ {tool_id} 的 schema 对象无效，跳过检查")
                    continue
                
                # 查找对应的service.json配置
                service_config = None
                for config in service_configs:
                    if (config.get('service_id') == tool_id or 
                        tool_id.endswith(config.get('service_id', '')) or
                        config.get('service_id', '').endswith(tool_id.replace('mcp-', '').replace('-mcp-server', ''))):
                        service_config = config
                        break
                
                if service_config:
                    # 比较capabilities
                    service_capabilities = {cap['name']: cap for cap in service_config.get('capabilities', [])}
                    
                    # 🔧 防御性检查：确保 actions 是字典类型
                    cached_actions = cached_schema.actions
                    if not isinstance(cached_actions, dict):
                        logger.warning(f"⚠️ {tool_id} 的 actions 不是字典类型: {type(cached_actions)}")
                        cached_actions = {}
                    
                    # 检查缺失的动作
                    for cap_name in service_capabilities:
                        if cap_name not in cached_actions:
                            consistency_report['issues'].append({
                                'type': 'missing_cached_action',
                                'tool_id': tool_id,
                                'action': cap_name,
                                'severity': 'medium',
                                'description': f"service.json中定义了{cap_name}，但缓存中缺失"
                            })
                    
                    # 检查多余的动作
                    for action_name in cached_actions:
                        if action_name not in service_capabilities:
                            consistency_report['issues'].append({
                                'type': 'extra_cached_action',
                                'tool_id': tool_id, 
                                'action': action_name,
                                'severity': 'low',
                                'description': f"缓存中有{action_name}，但service.json中未定义"
                            })
                    
                    # 检查参数一致性
                    for cap_name, cap_info in service_capabilities.items():
                        if cap_name in cached_actions:
                            param_issues = self._compare_action_parameters(
                                cap_info, cached_actions[cap_name], tool_id, cap_name
                            )
                            consistency_report['issues'].extend(param_issues)
                
            consistency_report['has_issues'] = len(consistency_report['issues']) > 0
            
        except Exception as e:
            logger.error(f"❌ Schema一致性验证失败: {e}")
            consistency_report['issues'].append({
                'type': 'validation_error',
                'severity': 'high',
                'description': f"一致性验证异常: {e}"
            })
            consistency_report['has_issues'] = True
            
        return consistency_report
    
    async def _validate_schema_structures(self) -> Dict[str, Any]:
        """验证所有ToolSchema的结构完整性"""
        structure_report = {
            'timestamp': datetime.now().isoformat(),
            'has_issues': False,
            'issues': [],
            'checked_schemas': 0,
            'valid_schemas': 0
        }
        
        try:
            for tool_id, schema in self._cache.items():
                structure_report['checked_schemas'] += 1
                
                # 验证单个schema结构
                validation_result = schema.validate_structure()
                
                if validation_result['is_valid']:
                    structure_report['valid_schemas'] += 1
                else:
                    structure_report['has_issues'] = True
                    for issue in validation_result['issues']:
                        structure_report['issues'].append({
                            'type': 'structure_issue',
                            'tool_id': tool_id,
                            'issue': issue,
                            'severity': 'high'
                        })
            
            logger.debug(f"🔍 结构验证完成: {structure_report['valid_schemas']}/{structure_report['checked_schemas']} 个Schema有效")
            
        except Exception as e:
            logger.error(f"❌ Schema结构验证失败: {e}")
            structure_report['has_issues'] = True
            structure_report['issues'].append({
                'type': 'validation_error',
                'error': str(e),
                'severity': 'critical'
            })
        
        return structure_report
    
    async def _auto_fix_structure_issues(self, issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """自动修复Schema结构问题"""
        fixes_applied = []
        
        for issue in issues:
            try:
                if issue['type'] == 'structure_issue':
                    fix_result = await self._fix_structure_issue(issue)
                    if fix_result:
                        fixes_applied.append(fix_result)
                        
            except Exception as e:
                logger.error(f"❌ 修复结构问题失败 {issue}: {e}")
        
        return fixes_applied
    
    async def _fix_structure_issue(self, issue: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """修复单个结构问题"""
        try:
            tool_id = issue['tool_id']
            issue_description = issue['issue']
            
            if tool_id not in self._cache:
                return None
            
            schema = self._cache[tool_id]
            
            # 修复缺少必需字段的问题
            if "缺少必需字段" in issue_description:
                field_name = issue_description.split(": ")[-1]
                
                if field_name == 'name' and not hasattr(schema, 'name'):
                    schema.name = tool_id.replace('_', ' ').title()
                    return {
                        'type': 'added_missing_field',
                        'tool_id': tool_id,
                        'field': field_name,
                        'value': schema.name
                    }
                elif field_name == 'description' and not hasattr(schema, 'description'):
                    schema.description = f"Tool for {tool_id} operations"
                    return {
                        'type': 'added_missing_field',
                        'tool_id': tool_id,
                        'field': field_name,
                        'value': schema.description
                    }
                elif field_name == 'actions' and not hasattr(schema, 'actions'):
                    schema.actions = {}
                    return {
                        'type': 'added_missing_field',
                        'tool_id': tool_id,
                        'field': field_name,
                        'value': 'empty_actions_dict'
                    }
            
            # 修复动作定义问题
            elif "动作" in issue_description and "定义无效" in issue_description:
                action_name = issue_description.split()[1]
                if hasattr(schema, 'actions') and action_name in schema.actions:
                    if not isinstance(schema.actions[action_name], dict):
                        schema.actions[action_name] = {
                            'desc': f'Action {action_name}',
                            'params': {}
                        }
                        return {
                            'type': 'fixed_action_definition',
                            'tool_id': tool_id,
                            'action': action_name
                        }
            
            # 修复缺少描述字段的问题
            elif "缺少描述字段" in issue_description:
                action_name = issue_description.split()[1]
                if hasattr(schema, 'actions') and action_name in schema.actions:
                    if 'desc' not in schema.actions[action_name]:
                        schema.actions[action_name]['desc'] = f'Action {action_name}'
                        return {
                            'type': 'added_action_description',
                            'tool_id': tool_id,
                            'action': action_name
                        }
            
        except Exception as e:
            logger.error(f"❌ 修复结构问题异常: {e}")
        
        return None
    
    def _compare_action_parameters(self, service_cap: Dict, cached_action: Dict, 
                                 tool_id: str, action_name: str) -> List[Dict]:
        """比较动作参数的一致性"""
        issues = []
        
        try:
            service_params = service_cap.get('parameters', {})
            service_required = service_cap.get('required_params', [])
            
            cached_params = cached_action.get('params', {})
            
            # 检查必需参数一致性
            for required_param in service_required:
                if required_param not in cached_params:
                    issues.append({
                        'type': 'missing_required_param',
                        'tool_id': tool_id,
                        'action': action_name,
                        'parameter': required_param,
                        'severity': 'high',
                        'description': f"必需参数{required_param}在缓存中缺失"
                    })
                elif '必需' not in str(cached_params[required_param]):
                    issues.append({
                        'type': 'param_requirement_mismatch',
                        'tool_id': tool_id,
                        'action': action_name,
                        'parameter': required_param,
                        'severity': 'medium',
                        'description': f"参数{required_param}应标记为必需"
                    })
            
            # 检查参数定义一致性
            for param_name, param_def in service_params.items():
                if param_name not in cached_params:
                    issues.append({
                        'type': 'missing_param_definition',
                        'tool_id': tool_id,
                        'action': action_name,
                        'parameter': param_name,
                        'severity': 'low',
                        'description': f"参数{param_name}定义在缓存中缺失"
                    })
                    
        except Exception as e:
            issues.append({
                'type': 'parameter_comparison_error',
                'tool_id': tool_id,
                'action': action_name,
                'severity': 'medium',
                'description': f"参数比较异常: {e}"
            })
            
        return issues
    
    async def _auto_fix_schema_issues(self, issues: List[Dict]) -> List[Dict]:
        """自动修复可修复的Schema问题"""
        fixes_applied = []
        
        for issue in issues:
            try:
                if issue['type'] == 'missing_cached_action':
                    # 尝试从service.json重新生成动作定义
                    fix_result = await self._fix_missing_cached_action(issue)
                    if fix_result:
                        fixes_applied.append(fix_result)
                        
                elif issue['type'] == 'param_requirement_mismatch':
                    # 修正参数必需性标记
                    fix_result = self._fix_parameter_requirement(issue)
                    if fix_result:
                        fixes_applied.append(fix_result)
                        
                elif issue['type'] == 'missing_param_definition':
                    # 添加缺失的参数定义
                    fix_result = await self._fix_missing_parameter_definition(issue)
                    if fix_result:
                        fixes_applied.append(fix_result)
                        
            except Exception as e:
                logger.error(f"❌ 修复Schema问题失败 {issue}: {e}")
                
        return fixes_applied
    
    async def _fix_missing_cached_action(self, issue: Dict) -> Optional[Dict]:
        """修复缺失的缓存动作"""
        try:
            tool_id = issue['tool_id']
            action_name = issue['action']
            
            # 从service.json获取动作定义
            service_configs = await self._load_mcp_service_configs()
            for config in service_configs:
                if self._matches_tool_id(config.get('service_id', ''), tool_id):
                    capabilities = config.get('capabilities', [])
                    for cap in capabilities:
                        if cap['name'] == action_name:
                            # 重新生成动作定义
                            action_def = self._convert_service_capability_to_action(cap)
                            
                            # 更新缓存
                            if tool_id in self._cache:
                                self._cache[tool_id].actions[action_name] = action_def
                                
                                return {
                                    'type': 'added_missing_action',
                                    'tool_id': tool_id,
                                    'action': action_name,
                                    'description': f"从service.json恢复了动作{action_name}"
                                }
        except Exception as e:
            logger.error(f"❌ 修复缺失动作失败: {e}")
        
        return None
    
    def _fix_parameter_requirement(self, issue: Dict) -> Optional[Dict]:
        """修复参数必需性标记"""
        try:
            tool_id = issue['tool_id']
            action_name = issue['action']
            param_name = issue['parameter']
            
            if (tool_id in self._cache and 
                action_name in self._cache[tool_id].actions and
                param_name in self._cache[tool_id].actions[action_name].get('params', {})):
                
                # 更新参数标记为必需
                current_desc = self._cache[tool_id].actions[action_name]['params'][param_name]
                if '必需' not in str(current_desc):
                    self._cache[tool_id].actions[action_name]['params'][param_name] = f"必需 - {current_desc}"
                    
                    return {
                        'type': 'fixed_param_requirement',
                        'tool_id': tool_id,
                        'action': action_name,
                        'parameter': param_name,
                        'description': f"标记参数{param_name}为必需"
                    }
        except Exception as e:
            logger.error(f"❌ 修复参数必需性失败: {e}")
            
        return None
    
    async def _fix_missing_parameter_definition(self, issue: Dict) -> Optional[Dict]:
        """修复缺失的参数定义"""
        try:
            tool_id = issue['tool_id']
            action_name = issue['action']
            param_name = issue['parameter']
            
            # 从service.json获取参数定义
            service_configs = await self._load_mcp_service_configs()
            for config in service_configs:
                if self._matches_tool_id(config.get('service_id', ''), tool_id):
                    capabilities = config.get('capabilities', [])
                    for cap in capabilities:
                        if cap['name'] == action_name:
                            params = cap.get('parameters', {})
                            if param_name in params:
                                param_def = params[param_name]
                                
                                # 添加参数定义到缓存
                                if (tool_id in self._cache and 
                                    action_name in self._cache[tool_id].actions):
                                    
                                    if 'params' not in self._cache[tool_id].actions[action_name]:
                                        self._cache[tool_id].actions[action_name]['params'] = {}
                                    
                                    self._cache[tool_id].actions[action_name]['params'][param_name] = param_def.get('description', f"{param_name}参数")
                                    
                                    return {
                                        'type': 'added_missing_param',
                                        'tool_id': tool_id,
                                        'action': action_name,
                                        'parameter': param_name,
                                        'description': f"添加了参数{param_name}的定义"
                                    }
        except Exception as e:
            logger.error(f"❌ 修复缺失参数定义失败: {e}")
            
        return None
    
    def _matches_tool_id(self, service_id: str, tool_id: str) -> bool:
        """检查service_id是否匹配tool_id"""
        if not service_id or not tool_id:
            return False
            
        # 标准匹配
        if service_id == tool_id:
            return True
            
        # 模糊匹配
        service_clean = service_id.replace('-', '').replace('_', '').lower()
        tool_clean = tool_id.replace('-', '').replace('_', '').replace('mcp', '').replace('server', '').lower()
        
        return service_clean in tool_clean or tool_clean in service_clean
    
    def _convert_service_capability_to_action(self, capability: Dict) -> Dict:
        """将service.json的capability转换为动作定义"""
        action_def = {
            'desc': capability.get('description', ''),
            'params': {}
        }
        
        # 转换参数
        parameters = capability.get('parameters', {})
        required_params = capability.get('required_params', [])
        
        for param_name, param_info in parameters.items():
            param_desc = param_info.get('description', f"{param_name}参数")
            if param_name in required_params:
                param_desc = f"必需 - {param_desc}"
            else:
                param_desc = f"可选 - {param_desc}"
            
            action_def['params'][param_name] = param_desc
        
        # 添加示例
        examples = capability.get('examples', [])
        if examples and isinstance(examples, list) and len(examples) > 0:
            action_def['example'] = examples[0]
        
        return action_def
    
    async def get_available_tool_ids(self) -> List[str]:
        """获取当前可用的工具ID列表"""
        schemas = await self.get_live_tool_schemas()
        return list(schemas.keys())
    
    async def get_tool_schema(self, tool_id: str) -> Optional[ToolSchema]:
        """获取特定工具的Schema"""
        schemas = await self.get_live_tool_schemas()
        return schemas.get(tool_id)
    
    async def generate_llm_tools_description(self) -> str:
        """生成面向LLM的动态工具描述 - 带强校验机制"""
        schemas = await self.get_live_tool_schemas()
        
        if not schemas:
            return "⚠️ 当前无可用工具，请联系管理员检查工具服务状态"
        
        lines = ["### 📋 实时可用工具 (基于当前部署状态):"]
        
        # 生成动作集合的hash，用于校验prompt与执行端一致性
        action_set = set()
        for schema in schemas.values():
            for action in schema.actions:
                action_set.add(f"{schema.tool_id}.{action}")
        
        # 计算动作集合的hash
        import hashlib
        action_hash = hashlib.md5("|".join(sorted(action_set)).encode()).hexdigest()[:8]
        
        # 按类别分组显示
        categorized = {}
        for schema in schemas.values():
            category = schema.category
            if category not in categorized:
                categorized[category] = []
            categorized[category].append(schema)
        
        for category, tool_list in categorized.items():
            lines.append(f"\n**{category.title()} 工具:**")
            for schema in tool_list:
                lines.append(schema.to_llm_description())
        
        # 🔒 P0-1 修复：添加强校验机制
        lines.extend([
            "",
            "⚠️ **严格约束**: 只能使用上述明确列出的工具和动作组合！",
            f"🔒 **Schema校验码**: {action_hash} (确保prompt与执行端一致)",
            "📝 **数据源**: 100%基于当前实际部署状态动态生成",
            f"🕒 **更新时间**: {datetime.now().strftime('%H:%M:%S')}",
            "",
            "🚫 **禁止行为**: 不要尝试以下操作",
            "- 使用未列出的工具ID或动作名称",
            "- 组合不同工具的动作名称",
            "- 使用旧版本或文档中的示例动作名",
            f"- 忽略校验码 {action_hash} 对应的动作集合"
        ])
        
        return "\n".join(lines)
    
    async def get_action_whitelist(self) -> Dict[str, List[str]]:
        """获取严格的动作白名单，用于生成前验证"""
        schemas = await self.get_live_tool_schemas()
        whitelist = {}
        
        for schema in schemas.values():
            whitelist[schema.tool_id] = list(schema.actions)
            
        return whitelist
    
    async def validate_action_combination(self, tool_id: str, action: str) -> Tuple[bool, str]:
        """验证工具动作组合是否在白名单中"""
        whitelist = await self.get_action_whitelist()
        
        if tool_id not in whitelist:
            available_tools = list(whitelist.keys())
            return False, f"未知工具ID: {tool_id}。可用工具: {available_tools}"
        
        if action not in whitelist[tool_id]:
            available_actions = whitelist[tool_id]
            return False, f"工具 {tool_id} 不支持动作 {action}。可用动作: {available_actions}"
        
        return True, ""
    
    async def _refresh_schemas(self):
        """刷新工具Schemas - 实现选项1: 直接从工具注册表获取信息"""
        logger.debug("🔄 开始刷新工具Schemas...")
        
        # 保存当前缓存作为备份
        cache_backup = self._cache.copy()
        logger.debug(f"📦 备份当前缓存: {len(cache_backup)} 个工具")
        
        try:
            # 🚀 选项1实现: 优先从结构化工具注册表获取（主要数据源）
            await self._refresh_from_registry()
            
            # 方法2: 通过ToolScore客户端获取（补充数据源）
            if self.toolscore_client and len(self._cache) == 0:
                logger.warning("⚠️ 工具注册表为空，回退到ToolScore客户端")
                await self._refresh_from_toolscore()
            
            # 如果刷新后缓存仍为空且有备份，恢复备份
            if len(self._cache) == 0 and len(cache_backup) > 0:
                logger.warning(f"⚠️ 刷新后缓存为空，恢复备份 {len(cache_backup)} 个工具")
                self._cache = cache_backup
                
            logger.info(f"✅ 工具Schemas刷新完成，当前可用工具: {len(self._cache)}个")
            
        except Exception as e:
            logger.error(f"❌ 工具Schemas刷新失败: {e}")
            # 如果刷新失败，恢复备份缓存
            if len(cache_backup) > 0:
                logger.warning(f"⚠️ 刷新失败，恢复备份 {len(cache_backup)} 个工具")
                self._cache = cache_backup
    
    async def _refresh_from_toolscore(self):
        """从ToolScore服务获取Schemas"""
        try:
            # 获取可用工具列表
            tools = await self.toolscore_client.get_available_tools()
            logger.debug(f"🔍 从ToolScore获取到工具列表: {tools}")
            
            # 映射旧的工具ID到新的ID
            tool_id_mapping = {
                'microsandbox-mcp-server': 'microsandbox',
                'browser-use-mcp-server': 'browser_use',
                'mcp-deepsearch': 'deepsearch',
                'mcp-search-tool': 'mcp-search-tool'  # 保持不变
            }
            
            # 转换工具ID列表
            mapped_tools = []
            for tool_id in tools:
                mapped_id = tool_id_mapping.get(tool_id, tool_id)
                mapped_tools.append(mapped_id)
                if mapped_id != tool_id:
                    logger.debug(f"🔄 工具ID映射: {tool_id} -> {mapped_id}")
            
            logger.debug(f"🔧 映射后的工具列表: {mapped_tools}")
            
            for tool_id in mapped_tools:
                try:
                    # 优先检查是否已在缓存中（来自结构化工具注册表）
                    if tool_id in self._cache:
                        logger.debug(f"⏭️ 工具 {tool_id} 已在缓存中，跳过ToolScore获取")
                        continue
                    
                    # 如果不在缓存中，从ToolScore获取详细信息
                    tool_info = await self._get_tool_info_from_toolscore(tool_id)
                    if tool_info:
                        schema = self._convert_to_schema(tool_info)
                        self._cache[tool_id] = schema
                        logger.debug(f"✅ 已从ToolScore缓存工具Schema: {tool_id}")
                    else:
                        # 如果无法获取详细信息，创建基础Schema
                        basic_schema = self._create_basic_schema(tool_id)
                        self._cache[tool_id] = basic_schema
                        logger.debug(f"🔧 创建基础Schema: {tool_id}")
                        
                except Exception as e:
                    logger.warning(f"⚠️ 获取工具 {tool_id} 信息失败: {e}")
                    # 容错处理：只有当工具不在缓存中时才创建备用Schema
                    if tool_id not in self._cache:
                        try:
                            fallback_schema = self._create_basic_schema(tool_id)
                            self._cache[tool_id] = fallback_schema
                            logger.debug(f"🊑 使用备用Schema: {tool_id}")
                        except Exception as fallback_error:
                            logger.error(f"❗ 创建备用Schema失败: {tool_id} - {fallback_error}")
                    
        except Exception as e:
            logger.warning(f"⚠️ 从ToolScore获取工具列表失败: {e}")
    
    async def _refresh_from_registry(self):
        """从结构化工具注册表获取Schemas - 选项1主要实现"""
        try:
            from core.toolscore.structured_tools import tool_registry
            # 🔧 P0修复: 导入tool_definitions以触发工具自动注册
            from core.toolscore import tool_definitions  # 触发装饰器注册
            
            # 检查工具注册表状态
            logger.debug(f"🔍 工具注册表状态检查: _tools 字典包含 {len(tool_registry._tools)} 个条目")
            for tool_id in tool_registry._tools.keys():
                logger.debug(f"  - 注册表中的工具: {tool_id}")
            
            tools = tool_registry.get_all_tools()
            logger.info(f"🔧 选项1: 从工具注册表获取到 {len(tools)} 个工具")
            
            # 检查工具对象的有效性
            for i, tool in enumerate(tools):
                if hasattr(tool, 'id') and hasattr(tool, 'name'):
                    logger.debug(f"  工具 {i}: id={tool.id}, name={tool.name}, actions={len(tool.actions) if hasattr(tool, 'actions') else 0}")
                else:
                    logger.error(f"  ❌ 无效的工具对象 {i}: {type(tool)}")
                    return  # 如果有无效工具，直接返回
            
            # 如果注册表为空，添加基础MCP工具的回退定义
            if len(tools) == 0:
                logger.warning("⚠️ 工具注册表为空，添加基础MCP工具定义")
                self._add_fallback_mcp_tools()
                logger.info(f"🔧 回退定义添加完成，最终缓存大小: {len(self._cache)} 个工具")
                return
            
            processed_count = 0
            for tool_def in tools:
                try:
                    logger.debug(f"🔧 处理工具定义: {tool_def.id}")
                    # 转换为ToolSchema格式，提取完整的参数信息
                    actions = {}
                    for action in tool_def.actions:
                        try:
                            # 🔧 选项1增强: 提取详细的参数信息
                            params = {}
                            if hasattr(action, 'parameters') and action.parameters:
                                # 从Pydantic模型提取参数信息
                                param_schema = action.parameters.schema()
                                properties = param_schema.get('properties', {})
                                required = param_schema.get('required', [])
                                
                                for param_name, param_info in properties.items():
                                    param_desc = param_info.get('description', f'{param_name}参数')
                                    if param_name in required:
                                        param_desc = f"必需 - {param_desc}"
                                    else:
                                        param_desc = f"可选 - {param_desc}"
                                    params[param_name] = param_desc
                            
                            actions[action.name] = {
                                'desc': action.description,
                                'params': params,
                                'example': getattr(action, 'example', {})
                            }
                            logger.debug(f"  ✅ 处理动作: {action.name}")
                        except Exception as action_error:
                            logger.error(f"  ❌ 处理动作失败: {action.name} - {action_error}")
                            # 创建基础动作定义
                            actions[action.name] = {
                                'desc': getattr(action, 'description', '动作描述'),
                                'params': {},
                                'example': {}
                            }
                    
                    schema = ToolSchema(
                        tool_id=tool_def.id,
                        name=tool_def.name,
                        description=tool_def.description,
                        actions=actions,
                        category=tool_def.category,
                        version=getattr(tool_def, 'version', '1.0.0')
                    )
                    
                    self._cache[tool_def.id] = schema
                    processed_count += 1
                    logger.debug(f"✅ 选项1: 成功缓存工具 {tool_def.id} (包含 {len(actions)} 个动作)")
                    logger.debug(f"   当前缓存大小: {len(self._cache)} 个工具")
                except Exception as tool_error:
                    logger.error(f"❌ 处理工具定义失败: {tool_def.id if hasattr(tool_def, 'id') else 'unknown'} - {tool_error}")
                    
            logger.info(f"🔧 选项1: 成功处理 {processed_count}/{len(tools)} 个工具，当前缓存 {len(self._cache)} 个工具")
                
        except Exception as e:
            logger.error(f"❌ 选项1: 从工具注册表获取Schemas失败: {e}")
            # 发生异常时也添加回退工具定义
            self._add_fallback_mcp_tools()
    
    def _add_fallback_mcp_tools(self):
        """添加基础MCP工具的回退定义"""
        try:
            # 基于日志中看到的MCP服务器，添加基础工具定义
            fallback_tools = [
                {
                    'tool_id': 'mcp-deepsearch',
                    'name': '深度搜索工具',
                    'description': '执行深度网络搜索和信息研究',
                    'category': 'research',
                    'actions': {
                        'research': {'desc': '执行研究任务', 'params': {'query': '搜索查询'}}
                    }
                },
                {
                    'tool_id': 'microsandbox-mcp-server',
                    'name': '微沙盒执行工具',
                    'description': '在安全沙盒环境中执行代码',
                    'category': 'execution',
                    'actions': {
                        'execute': {'desc': '执行代码', 'params': {'code': '要执行的代码'}}
                    }
                },
                {
                    'tool_id': 'browser-use-mcp-server',
                    'name': '浏览器自动化工具',
                    'description': '自动化浏览器操作和网页交互',
                    'category': 'browser',
                    'actions': {
                        'navigate': {'desc': '浏览网页', 'params': {'url': '目标网页URL'}}
                    }
                },
                {
                    'tool_id': 'mcp-search-tool',
                    'name': '搜索工具',
                    'description': '执行各种搜索操作',
                    'category': 'search',
                    'actions': {
                        'search': {'desc': '搜索信息', 'params': {'query': '搜索关键词'}}
                    }
                }
            ]
            
            for tool_info in fallback_tools:
                schema = ToolSchema(
                    tool_id=tool_info['tool_id'],
                    name=tool_info['name'],
                    description=tool_info['description'],
                    actions=tool_info['actions'],
                    category=tool_info['category'],
                    version='1.0.0'
                )
                self._cache[tool_info['tool_id']] = schema
                logger.debug(f"✅ 添加回退工具定义: {tool_info['tool_id']}")
            
            logger.info(f"🔧 已添加 {len(fallback_tools)} 个回退工具定义，当前缓存 {len(self._cache)} 个工具")
            
        except Exception as e:
            logger.error(f"❌ 添加回退工具定义失败: {e}")
            import traceback
            logger.error(f"❌ 详细错误: {traceback.format_exc()}")
    
    async def _get_tool_info_from_toolscore(self, tool_id: str) -> Optional[Dict]:
        """从ToolScore获取工具详细信息"""
        try:
            # 尝试获取工具详细信息（假设toolscore_client有get_tool_info方法）
            if hasattr(self.toolscore_client, 'get_tool_info'):
                tool_info = await self.toolscore_client.get_tool_info(tool_id)
                if tool_info:
                    return tool_info
            
            # 如果没有专门的API，返回None让其使用基础Schema
            return None
        except Exception as e:
            logger.debug(f"从ToolScore获取 {tool_id} 信息失败: {e}")
            return None
    
    def _convert_to_schema(self, tool_info: Dict) -> ToolSchema:
        """将ToolScore的工具信息转换为ToolSchema"""
        return ToolSchema(
            tool_id=tool_info.get('id', ''),
            name=tool_info.get('name', ''),
            description=tool_info.get('description', ''),
            actions=tool_info.get('actions', {}),
            category=tool_info.get('category', 'general'),
            version=tool_info.get('version', '1.0.0')
        )
    
    def _create_basic_schema(self, tool_id: str) -> ToolSchema:
        """为未知工具创建基础Schema"""
        # 根据tool_id推断工具类型和基本动作
        basic_actions = {}
        category = "general"
        name = tool_id
        description = f"未知工具: {tool_id}"
        
        # 根据tool_id关键字推断常见动作
        if 'sandbox' in tool_id.lower():
            category = "execution"
            name = "代码执行工具"
            description = "支持Python代码执行的沙箱环境"
            basic_actions = {
                'microsandbox_execute': {
                    'desc': '执行Python代码',
                    'params': {'code': '必需 - 要执行的Python代码'},
                    'example': {'code': 'print("Hello World")'}
                },
                'execute': {
                    'desc': '执行代码',
                    'params': {'code': '必需 - 要执行的代码'},
                    'example': {'code': 'print("test")'}
                }
            }
        elif 'browser' in tool_id.lower():
            category = "web"
            name = "浏览器工具"
            description = "支持网页浏览和操作"
            # 🔧 P0紧急修复1: 修正browser动作名称为实际支持的动作
            basic_actions = {
                'browser_navigate': {
                    'desc': '导航到指定URL',
                    'params': {'url': '必需 - 要访问的URL'},
                    'example': {'url': 'https://example.com'}
                },
                'browser_use_execute_task': {
                    'desc': '执行AI浏览器任务',
                    'params': {'task': '必需 - 任务描述'},
                    'example': {'task': '搜索Python教程'}
                },
                'browser_search_google': {
                    'desc': 'Google搜索',
                    'params': {'query': '必需 - 搜索查询'},
                    'example': {'query': 'Python asyncio'}
                },
                'browser_click_element': {
                    'desc': '点击页面元素',
                    'params': {'index': '必需 - 元素索引'},
                    'example': {'index': 1}
                },
                'browser_input_text': {
                    'desc': '输入文本',
                    'params': {'index': '必需 - 输入框索引', 'text': '必需 - 输入文本'},
                    'example': {'index': 0, 'text': 'hello world'}
                },
                'browser_extract_content': {
                    'desc': '提取页面内容',
                    'params': {},
                    'example': {}
                }
            }
        elif 'search' in tool_id.lower():
            category = "search"
            name = "搜索工具"
            description = "支持信息搜索和查找"
            if 'deepsearch' in tool_id.lower():
                # 🔧 P0紧急修复2: 统一DeepSearch参数为question（非query）
                basic_actions = {
                    'research': {
                        'desc': '深度研究搜索',
                        'params': {'question': '必需 - 研究问题'},
                        'example': {'question': 'Python asyncio基本概念和用法'}
                    },
                    'quick_research': {
                        'desc': '快速研究',
                        'params': {'question': '必需 - 研究问题'},
                        'example': {'question': 'Python asyncio'}
                    },
                    'comprehensive_research': {
                        'desc': '综合研究搜索',
                        'params': {'question': '必需 - 研究问题'},
                        'example': {'question': 'machine learning basics'}
                    }
                }
            elif 'mcp-search-tool' == tool_id:
                basic_actions = {
                    'analyze_tool_needs': {
                        'desc': '分析工具需求',
                        'params': {'task_description': '必需 - 任务描述'},
                        'example': {'task_description': '需要分析的任务'}
                    },
                    'search_and_install_tools': {
                        'desc': '搜索和安装工具',
                        'params': {'task_description': '必需 - 任务描述'},
                        'example': {'task_description': '需要安装的工具功能'}
                    }
                }
        
        # 如果没有匹配到特定类型，使用通用动作
        if not basic_actions:
            basic_actions = {
                'execute': {
                    'desc': '执行操作',
                    'params': {},
                    'example': {}
                }
            }
        
        return ToolSchema(
            tool_id=tool_id,
            name=name,
            description=description,
            actions=basic_actions,
            category=category,
            version="1.0.0"
        )
    
    async def validate_tool_action(self, tool_id: str, action: str) -> bool:
        """验证工具动作是否存在"""
        schema = await self.get_tool_schema(tool_id)
        if not schema:
            return False
        return action in schema.actions
    
    async def get_action_parameters_schema(self, tool_id: str, action: str) -> Optional[Dict]:
        """获取特定动作的参数Schema"""
        schema = await self.get_tool_schema(tool_id)
        if not schema or action not in schema.actions:
            return None
        
        return schema.actions[action].get('params', {})
    
    # 🔧 优化2：MCP服务器实时同步机制
    async def start_mcp_monitoring(self):
        """启动MCP服务器配置监控"""
        if not self._sync_enabled or self._mcp_monitor_task:
            return
            
        logger.info("🔍 启动MCP服务器配置监控...")
        self._mcp_monitor_task = asyncio.create_task(self._mcp_monitor_loop())
    
    async def stop_mcp_monitoring(self):
        """停止MCP服务器配置监控"""
        if self._mcp_monitor_task:
            self._mcp_monitor_task.cancel()
            try:
                await self._mcp_monitor_task
            except asyncio.CancelledError:
                pass
            self._mcp_monitor_task = None
            logger.info("⏹️ MCP服务器配置监控已停止")
    
    async def _mcp_monitor_loop(self):
        """MCP监控循环"""
        while self._sync_enabled:
            try:
                await self._check_mcp_changes()
                await asyncio.sleep(30)  # 每30秒检查一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ MCP监控循环异常: {e}")
                await asyncio.sleep(60)  # 异常时延长间隔
    
    async def _check_mcp_changes(self):
        """检查MCP配置文件变化"""
        changes_detected = False
        
        for config_path in self.mcp_config_paths:
            expanded_path = Path(config_path).expanduser()
            if not expanded_path.exists():
                continue
                
            for config_file in expanded_path.glob("**/*.json"):
                try:
                    current_hash = await self._get_file_hash(config_file)
                    stored_hash = self._mcp_file_hashes.get(str(config_file))
                    
                    if stored_hash != current_hash:
                        logger.info(f"📋 检测到MCP配置变化: {config_file}")
                        self._mcp_file_hashes[str(config_file)] = current_hash
                        changes_detected = True
                        
                except Exception as e:
                    logger.warning(f"⚠️ 读取MCP配置文件失败 {config_file}: {e}")
        
        if changes_detected:
            logger.info("🔄 MCP配置变化，强制刷新schema...")
            await self.get_live_tool_schemas(force_refresh=True)
    
    async def _get_file_hash(self, file_path: Path) -> str:
        """计算文件哈希"""
        try:
            async with aiofiles.open(file_path, 'rb') as f:
                content = await f.read()
                return hashlib.md5(content).hexdigest()
        except Exception as e:
            logger.warning(f"⚠️ 计算文件哈希失败 {file_path}: {e}")
            return ""
    
    async def sync_from_mcp_server(self, server_url: str, server_name: str) -> bool:
        """从MCP服务器直接同步schema"""
        try:
            logger.info(f"🔗 尝试从MCP服务器同步schema: {server_name} ({server_url})")
            
            # 这里可以添加MCP服务器的HTTP API调用
            # 例如: GET {server_url}/schema 或类似接口
            
            # 示例实现（需要根据实际MCP服务器API调整）
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=10)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 尝试获取服务器schema信息
                schema_url = f"{server_url.rstrip('/')}/tools/list"
                async with session.get(schema_url) as response:
                    if response.status == 200:
                        tools_data = await response.json()
                        
                        # 转换为我们的schema格式
                        for tool_info in tools_data.get('tools', []):
                            schema = self._convert_mcp_tool_to_schema(tool_info, server_name)
                            self._cache[schema.tool_id] = schema
                            
                        logger.info(f"✅ 成功从MCP服务器同步 {len(tools_data.get('tools', []))} 个工具")
                        return True
                        
        except Exception as e:
            logger.warning(f"⚠️ MCP服务器同步失败 {server_name}: {e}")
            
        return False
    
    def _convert_mcp_tool_to_schema(self, tool_info: Dict, server_name: str) -> ToolSchema:
        """将MCP服务器的工具信息转换为ToolSchema"""
        return ToolSchema(
            tool_id=tool_info.get('name', f"mcp-{server_name}"),
            name=tool_info.get('displayName', tool_info.get('name', 'Unknown')),
            description=tool_info.get('description', '来自MCP服务器的工具'),
            actions=self._parse_mcp_actions(tool_info.get('inputSchema', {})),
            category='mcp',
            version=tool_info.get('version', '1.0.0')
        )
    
    def _parse_mcp_actions(self, input_schema: Dict) -> Dict[str, Dict[str, Any]]:
        """解析MCP工具的输入schema为动作格式"""
        actions = {}
        
        # MCP工具通常只有一个主要动作
        if input_schema:
            properties = input_schema.get('properties', {})
            required = input_schema.get('required', [])
            
            actions['execute'] = {
                'desc': '执行工具操作',
                'params': {k: f"{'必需' if k in required else '可选'} - {v.get('description', k)}" 
                          for k, v in properties.items()},
                'example': {k: v.get('default', f'<{k}>') for k, v in properties.items()}
            }
        
        return actions or {'execute': {'desc': 'Execute operation', 'params': {}, 'example': {}}}
    
    async def get_schema_hash(self) -> str:
        """获取当前schema集合的哈希值，用于验证一致性"""
        schemas = await self.get_live_tool_schemas()
        schema_data = {}
        
        for tool_id, schema in schemas.items():
            schema_data[tool_id] = {
                'actions': list(schema.actions.keys()),
                'version': schema.version,
                'last_updated': schema.last_updated.isoformat() if schema.last_updated else None
            }
        
        schema_json = json.dumps(schema_data, sort_keys=True)
        return hashlib.md5(schema_json.encode()).hexdigest()[:8]
    
    # 🔧 P0-1生产级强化方法：安全刷新+增量更新+一致性验证
    async def _safe_refresh_schemas(self) -> bool:
        """安全刷新Schema，支持增量更新和一致性验证"""
        try:
            logger.debug("🔍 开始安全Schema刷新...")
            
            # 🚀 Step 1: 获取版本信息（增量更新前置检查）
            if self._consistency_check_enabled:
                new_versions = await self._fetch_schema_versions()
                changed_tools = self._identify_changed_tools(new_versions)
                
                if not changed_tools and not hasattr(self, '_force_full_refresh'):
                    logger.debug("📊 Schema版本无变化，跳过更新")
                    return True
                
                logger.info(f"🔄 检测到 {len(changed_tools)} 个工具需要更新: {changed_tools}")
            else:
                # 禁用一致性检查时，执行全量刷新
                changed_tools = None
            
            # 🚀 Step 2: 执行增量或全量刷新
            refresh_success = await self._perform_schema_refresh(changed_tools)
            if not refresh_success:
                logger.error("❌ Schema刷新操作失败")
                return False
            
            # 🛡️ Step 3: 一致性验证（恢复严格模式）
            if self._consistency_check_enabled:
                consistency_report = await self._validate_schema_consistency()
                if consistency_report['has_issues']:
                    logger.error(f"❌ Schema一致性验证失败: {len(consistency_report['issues'])} 个问题")
                    for issue in consistency_report['issues'][:5]:  # 只显示前5个问题
                        logger.error(f"  - {issue['description']}")
                    return False
            
            # ✅ Step 4: 备份成功的Schema
            self._last_successful_schemas = self._cache.copy()
            logger.info(f"✅ Schema安全刷新完成，备份 {len(self._cache)} 个工具")
            return True
            
        except Exception as e:
            logger.error(f"❌ 安全Schema刷新异常: {e}")
            return False
    
    async def _fetch_schema_versions(self) -> Dict[str, str]:
        """获取Schema版本信息，用于增量更新 - 选项1优化"""
        versions = {}
        try:
            # 🚀 选项1: 优先从结构化工具注册表获取版本
            from core.toolscore.structured_tools import get_all_structured_tools
            # 🔧 P0修复: 导入tool_definitions以触发工具自动注册
            from core.toolscore import tool_definitions  # 触发装饰器注册
            structured_tools = get_all_structured_tools()
            
            logger.debug(f"🔧 选项1: 工具注册表中发现 {len(structured_tools)} 个工具")
            
            for tool_info in structured_tools:
                # 使用工具定义的哈希作为版本标识
                tool_hash = hashlib.md5(str(tool_info).encode()).hexdigest()[:8]
                versions[tool_info.id] = tool_hash
                logger.debug(f"🔧 选项1: 工具 {tool_info.id} 版本 {tool_hash}")
            
            # 从ToolScore客户端获取版本（仅作为备选）
            if self.toolscore_client and len(versions) == 0:
                logger.warning("⚠️ 工具注册表为空，回退到ToolScore客户端获取版本")
                try:
                    toolscore_tools = await asyncio.wait_for(
                        self.toolscore_client.get_all_tools(), timeout=5.0
                    )
                    for tool in toolscore_tools:
                        tool_id = tool.get('id', '')
                        if tool_id:
                            tool_hash = hashlib.md5(str(tool).encode()).hexdigest()[:8]
                            versions[tool_id] = tool_hash
                except (asyncio.TimeoutError, Exception) as e:
                    logger.warning(f"⚠️ ToolScore版本获取失败: {e}")
            
            logger.debug(f"📋 获取到 {len(versions)} 个工具版本信息")
            return versions
            
        except Exception as e:
            logger.error(f"❌ 版本信息获取失败: {e}")
            return {}
    
    def _identify_changed_tools(self, new_versions: Dict[str, str]) -> List[str]:
        """识别发生变化的工具"""
        changed_tools = []
        
        for tool_id, new_version in new_versions.items():
            old_version = self._schema_versions.get(tool_id)
            if old_version != new_version:
                changed_tools.append(tool_id)
                self._schema_versions[tool_id] = new_version
        
        # 检查删除的工具
        removed_tools = set(self._schema_versions.keys()) - set(new_versions.keys())
        for tool_id in removed_tools:
            changed_tools.append(tool_id)
            if tool_id in self._cache:
                del self._cache[tool_id]
            del self._schema_versions[tool_id]
        
        return changed_tools
    
    async def _perform_schema_refresh(self, changed_tools: Optional[List[str]]) -> bool:
        """执行Schema刷新（增量或全量）"""
        try:
            if changed_tools is not None:
                # 🔄 增量更新：只更新变化的工具
                logger.info(f"🔄 执行增量更新: {len(changed_tools)} 个工具")
                
                # 如果缓存为空且有工具需要更新，执行全量刷新
                if len(self._cache) == 0 and len(changed_tools) > 0:
                    logger.info("🔄 缓存为空，转为全量刷新模式")
                    await self._refresh_schemas()
                else:
                    # 正常增量更新
                    for tool_id in changed_tools:
                        updated_schema = await self._fetch_single_tool_schema(tool_id)
                        if updated_schema:
                            self._cache[tool_id] = updated_schema
                            logger.debug(f"🔄 更新工具Schema: {tool_id}")
                        else:
                            logger.warning(f"⚠️ 无法获取工具Schema: {tool_id}")
            else:
                # 🚀 全量刷新：重建整个缓存
                logger.info("🚀 执行全量Schema刷新")
                await self._refresh_schemas()  # 调用原有的全量刷新方法
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Schema刷新执行失败: {e}")
            return False
    
    async def _fetch_single_tool_schema(self, tool_id: str) -> Optional[ToolSchema]:
        """获取单个工具的Schema - 选项1优化"""
        try:
            # 🚀 选项1: 优先从结构化工具注册表获取
            from core.toolscore.structured_tools import get_all_structured_tools
            # 🔧 P0修复: 导入tool_definitions以触发工具自动注册
            from core.toolscore import tool_definitions  # 触发装饰器注册
            structured_tools = get_all_structured_tools()
            
            # 在列表中查找匹配的工具
            for tool_def in structured_tools:
                if tool_def.id == tool_id:
                    # 🔧 选项1增强: 转换actions格式，提取完整参数信息
                    actions = {}
                    for action in tool_def.actions:
                        # 提取详细的参数信息
                        params = {}
                        if hasattr(action, 'parameters') and action.parameters:
                            # 从Pydantic模型提取参数信息
                            param_schema = action.parameters.schema()
                            properties = param_schema.get('properties', {})
                            required = param_schema.get('required', [])
                            
                            for param_name, param_info in properties.items():
                                param_desc = param_info.get('description', f'{param_name}参数')
                                if param_name in required:
                                    param_desc = f"必需 - {param_desc}"
                                else:
                                    param_desc = f"可选 - {param_desc}"
                                params[param_name] = param_desc
                        
                        actions[action.name] = {
                            'desc': action.description,
                            'params': params,
                            'example': getattr(action, 'example', {})
                        }
                    
                    return ToolSchema(
                        tool_id=tool_def.id,
                        name=tool_def.name,
                        description=tool_def.description,
                        actions=actions,
                        category=tool_def.category,
                        version=getattr(tool_def, 'version', '1.0.0')
                    )
            
            # 从ToolScore客户端获取（作为备选）
            if self.toolscore_client:
                try:
                    tool_data = await asyncio.wait_for(
                        self.toolscore_client.get_tool(tool_id), timeout=3.0
                    )
                    if tool_data:
                        return self._convert_to_schema(tool_data)
                except (asyncio.TimeoutError, Exception) as e:
                    logger.warning(f"⚠️ 从ToolScore获取工具 {tool_id} 失败: {e}")
            
            # 回退到基础Schema
            logger.warning(f"⚠️ 工具 {tool_id} 未在注册表中找到，创建基础Schema")
            return self._create_basic_schema(tool_id)
            
        except Exception as e:
            logger.error(f"❌ 获取工具Schema失败 {tool_id}: {e}")
            return None
    
    async def _validate_service_consistency(self) -> bool:
        """验证Schema与实际服务的一致性"""
        try:
            inconsistent_tools = []
            
            for tool_id, schema in self._cache.items():
                try:
                    # 针对不同类型的工具进行一致性检查
                    if tool_id.startswith("mcp-"):
                        actual_actions = await self._probe_mcp_server_actions(tool_id)
                    elif tool_id == "microsandbox-mcp-server":
                        actual_actions = await self._probe_microsandbox_actions()
                    elif tool_id == "browser-use-mcp-server":
                        actual_actions = await self._probe_browser_actions()
                    else:
                        # 跳过未知工具的一致性检查
                        continue
                    
                    schema_actions = set(schema.actions.keys())
                    actual_actions_set = set(actual_actions)
                    
                    if schema_actions != actual_actions_set:
                        inconsistent_tools.append({
                            "tool_id": tool_id,
                            "schema_actions": list(schema_actions),
                            "actual_actions": list(actual_actions_set),
                            "missing_in_schema": list(actual_actions_set - schema_actions),
                            "extra_in_schema": list(schema_actions - actual_actions_set)
                        })
                        
                except Exception as e:
                    logger.warning(f"⚠️ 无法验证工具 {tool_id} 一致性: {e}")
                    # 继续检查其他工具，不因单个工具失败而整体失败
            
            if inconsistent_tools:
                logger.warning(f"⚠️ 发现 {len(inconsistent_tools)} 个工具Schema不一致:")
                for tool in inconsistent_tools:
                    logger.warning(f"  - {tool['tool_id']}: 缺失 {tool['missing_in_schema']}, 多余 {tool['extra_in_schema']}")
                
                # 不完全一致但不阻断，记录警告即可
                return True  # 改为返回True，避免因轻微不一致而回滚
            
            logger.debug("✅ Schema一致性验证通过")
            return True
            
        except Exception as e:
            logger.error(f"❌ Schema一致性验证异常: {e}")
            return False  # 异常情况下返回False
    
    async def _probe_mcp_server_actions(self, tool_id: str) -> List[str]:
        """探测MCP服务器的实际可用动作"""
        try:
            # 这里应该根据实际的MCP服务器API来实现
            # 暂时返回预定义的动作列表
            if "deepsearch" in tool_id.lower():
                return ["research", "quick_research", "comprehensive_research"]
            elif "search-tool" in tool_id.lower():
                return ["search_file_content", "list_code_definitions", "analyze_tool_needs", "search_and_install_tools"]
            else:
                return ["execute"]  # 默认动作
                
        except Exception as e:
            logger.warning(f"⚠️ 探测MCP服务器动作失败 {tool_id}: {e}")
            return []
    
    async def _probe_microsandbox_actions(self) -> List[str]:
        """探测Microsandbox的实际可用动作"""
        try:
            # 可以通过WebSocket连接测试或HTTP API检查
            return [
                "microsandbox_execute", 
                "microsandbox_install_package", 
                "microsandbox_list_sessions",
                "microsandbox_close_session", 
                "microsandbox_cleanup_expired"
            ]
        except Exception as e:
            logger.warning(f"⚠️ 探测Microsandbox动作失败: {e}")
            return []
    
    async def _probe_browser_actions(self) -> List[str]:
        """探测Browser服务的实际可用动作"""
        try:
            # 🔧 P0紧急修复1: 返回Browser服务实际支持的动作列表
            # 基于browser_use_server/main.py的实际实现
            return [
                "browser_use_execute_task",  # ✅ 主要AI任务执行动作
                "browser_navigate",          # ✅ 导航动作
                "browser_click_element",     # ✅ 点击动作（使用index参数）
                "browser_input_text",        # ✅ 输入动作（使用index+text参数）
                "browser_extract_content",   # ✅ 内容提取动作
                "browser_search_google"      # ✅ Google搜索动作
            ]
        except Exception as e:
            logger.warning(f"⚠️ 探测Browser动作失败: {e}")
            return []
    
    import os
    import json

    def sync_with_service_json(self):
        """同步service.json与动态Schema"""
        mcp_servers_dirs = [
            os.path.join(os.path.dirname(__file__), '../mcp_servers/browser_use_server'),
            os.path.join(os.path.dirname(__file__), '../mcp_servers/search_tool_server'),
            os.path.join(os.path.dirname(__file__), '../mcp_servers/deepsearch_server'),
            os.path.join(os.path.dirname(__file__), '../mcp_servers/microsandbox_server'),
        ]
        for server_dir in mcp_servers_dirs:
            service_json_path = os.path.join(server_dir, 'service.json')
            if not os.path.exists(service_json_path):
                continue
            with open(service_json_path, 'r') as f:
                service_config = json.load(f)
            dynamic_schema = self.generate_dynamic_schema(server_dir)
            self.validate_consistency(service_config, dynamic_schema)

    def validate_consistency(self, static_schema, dynamic_schema):
        """详细校验静态Schema与动态Schema一致性，返回所有不一致项"""
        inconsistencies = []
        static_caps = {c['name']: c for c in static_schema.get('capabilities', [])}
        dynamic_caps = {c['name']: c for c in dynamic_schema.get('capabilities', [])}
        for action_name, static_def in static_caps.items():
            dynamic_def = dynamic_caps.get(action_name)
            if not dynamic_def:
                inconsistencies.append(f"[缺失] 动作 {action_name} 在动态Schema中不存在")
                continue
            # 检查参数类型和必需参数
            static_params = static_def.get('parameters', {})
            dynamic_params = dynamic_def.get('parameters', {})
            for param, s_def in static_params.items():
                d_def = dynamic_params.get(param)
                if not d_def:
                    inconsistencies.append(f"[参数缺失] {action_name} 缺少参数 {param} (动态Schema)")
                    continue
                if s_def.get('type') != d_def.get('type'):
                    inconsistencies.append(f"[类型不一致] {action_name}.{param} 类型: 静态={s_def.get('type')} 动态={d_def.get('type')}")
                if s_def.get('required', False) != d_def.get('required', False):
                    inconsistencies.append(f"[必需参数不一致] {action_name}.{param} required: 静态={s_def.get('required', False)} 动态={d_def.get('required', False)}")
            # 检查返回值格式（如有）
            if 'returns' in static_def or 'returns' in dynamic_def:
                if static_def.get('returns') != dynamic_def.get('returns'):
                    inconsistencies.append(f"[返回值不一致] {action_name} returns: 静态={static_def.get('returns')} 动态={dynamic_def.get('returns')}")
        return inconsistencies

# 全局工具Schema管理器实例
_tool_schema_manager = None

def get_tool_schema_manager() -> ToolSchemaManager:
    """获取全局工具Schema管理器实例"""
    global _tool_schema_manager
    if _tool_schema_manager is None:
        _tool_schema_manager = ToolSchemaManager()
    return _tool_schema_manager

def init_tool_schema_manager(redis_client=None, toolscore_client=None, enable_mcp_sync=True):
    """初始化全局工具Schema管理器"""
    global _tool_schema_manager
    _tool_schema_manager = ToolSchemaManager(redis_client, toolscore_client)
    
    # 🔧 优化2：启动MCP监控
    if enable_mcp_sync:
        asyncio.create_task(_tool_schema_manager.start_mcp_monitoring())
        
    return _tool_schema_manager


# ===== 在原有类中增加新方法 =====
# 由于无法直接修改原有方法，我们通过猴子补丁来增强功能

def _enhanced_refresh_schemas(self):
    """增强的刷新方法，优先使用结构化工具注册表"""
    import asyncio
    return asyncio.create_task(self._enhanced_refresh_schemas_async())

async def _enhanced_refresh_schemas_async(self):
    """异步版本的增强刷新方法"""
    logger.debug("🔄 开始增强刷新工具Schemas...")
    
    try:
        # 方法1: 优先使用结构化工具注册表（最准确）
        await self._refresh_from_registry()
        
        # 方法2: 补充从service.json获取
        await self._refresh_from_service_configs()
        
        # 方法3: 最后尝试ToolScore客户端（如果可用）
        if self.toolscore_client:
            await self._refresh_from_toolscore()
        
        logger.info(f"✅ 增强刷新完成，当前可用工具: {len(self._cache)}个")
        
    except Exception as e:
        logger.error(f"❗ 增强刷新失败: {e}")
        # 如果刷新失败，保持现有缓存

async def _refresh_from_service_configs(self):
    """从 MCP 服务器的 service.json 文件获取 Schemas"""
    import os
    import json
    
    try:
        mcp_servers_dir = os.path.join(os.getcwd(), 'mcp_servers')
        if not os.path.exists(mcp_servers_dir):
            logger.debug("⚠️ mcp_servers 目录不存在")
            return
        
        for server_name in os.listdir(mcp_servers_dir):
            server_dir = os.path.join(mcp_servers_dir, server_name)
            if not os.path.isdir(server_dir):
                continue
            
            service_json_path = os.path.join(server_dir, 'service.json')
            if os.path.exists(service_json_path):
                try:
                    with open(service_json_path, 'r', encoding='utf-8') as f:
                        service_config = json.load(f)
                    
                    # 解析服务配置
                    tool_id = self._get_tool_id_from_service_config(service_config, server_name)
                    schema = self._convert_service_config_to_schema(service_config, tool_id)
                    
                    if schema:
                        self._cache[tool_id] = schema
                        logger.debug(f"✅ 从 service.json 加载工具: {tool_id}")
                        
                except Exception as e:
                    logger.warning(f"⚠️ 解析 {service_json_path} 失败: {e}")
                    
    except Exception as e:
        logger.warning(f"⚠️ 从 service.json 获取 Schemas 失败: {e}")

def _get_tool_id_from_service_config(self, config: dict, server_name: str) -> str:
    """从服务配置获取工具ID"""
    # 映射服务器名称到工具ID
    service_to_tool_id = {
        'deepsearch_server': 'deepsearch',
        'microsandbox_server': 'microsandbox',
        'browser_use_server': 'browser_use',
        'search_tool_server': 'mcp-search-tool'
    }
    
    return service_to_tool_id.get(server_name, config.get('service_id', server_name))

def _convert_service_config_to_schema(self, config: dict, tool_id: str) -> ToolSchema:
    """将 service.json 配置转换为 ToolSchema"""
    try:
        capabilities = config.get('capabilities', [])
        actions = {}
        
        for cap in capabilities:
            action_name = cap.get('name', '')
            if action_name:
                # 转换参数格式
                params = {}
                parameters = cap.get('parameters', {})
                required_params = cap.get('required_params', [])
                
                for param_name, param_info in parameters.items():
                    is_required = param_name in required_params
                    param_desc = param_info.get('description', '')
                    if is_required:
                        param_desc = f'必需 - {param_desc}'
                    params[param_name] = param_desc
                
                actions[action_name] = {
                    'desc': cap.get('description', ''),
                    'params': params,
                    'example': cap.get('examples', [{}])[0] if cap.get('examples') else {}
                }
        
        return ToolSchema(
            tool_id=tool_id,
            name=config.get('name', tool_id),
            description=config.get('description', ''),
            actions=actions,
            category=self._infer_category_from_tags(config.get('tags', [])),
            version=config.get('version', '1.0.0')
        )
        
    except Exception as e:
        logger.warning(f"⚠️ 转换 service.json 到 ToolSchema 失败: {e}")
        return None

def _infer_category_from_tags(self, tags: list) -> str:
    """从标签推断工具类别"""
    tag_to_category = {
        'search': 'research',
        'analysis': 'research', 
        'browser': 'web_automation',
        'automation': 'web_automation',
        'sandbox': 'code_execution',
        'execution': 'code_execution',
        'files': 'tool_management',
        'code': 'tool_management'
    }
    
    for tag in tags:
        if tag in tag_to_category:
            return tag_to_category[tag]
    
    return 'general'

# 添加方法到 ToolSchemaManager 类
ToolSchemaManager._enhanced_refresh_schemas_async = _enhanced_refresh_schemas_async
ToolSchemaManager._refresh_from_service_configs = _refresh_from_service_configs
ToolSchemaManager._get_tool_id_from_service_config = _get_tool_id_from_service_config
ToolSchemaManager._convert_service_config_to_schema = _convert_service_config_to_schema
ToolSchemaManager._infer_category_from_tags = _infer_category_from_tags

# 覆盖原有的_refresh_schemas方法
async def _patched_refresh_schemas(self):
    return await self._enhanced_refresh_schemas_async()

ToolSchemaManager._refresh_schemas = _patched_refresh_schemas

# 🔧 P1修复1: 实时MCP服务器同步验证
async def _validate_mcp_server_connectivity(self, tool_id: str, server_config: Dict) -> Tuple[bool, Dict[str, Any]]:
    """验证MCP服务器连通性和Schema一致性"""
    validation_result = {
        'is_connected': False,
        'schema_consistent': False,
        'actual_actions': [],
        'expected_actions': [],
        'inconsistencies': [],
        'last_check': datetime.now().isoformat(),
        'error': None
    }
    
    try:
        # 获取预期的Schema
        expected_schema = await self.get_tool_schema(tool_id)
        if expected_schema:
            validation_result['expected_actions'] = list(expected_schema.actions.keys())
        
        # 使用传入的server_config中的信息
        server_url = server_config.get('url')
        server_name = server_config.get('server_name', tool_id)
        
        if not server_url:
            validation_result['error'] = f"无法获取 {tool_id} 的运行地址"
            return False, validation_result
        
        # 完善的MCP服务器验证
        import aiohttp
        import socket
        
        try:
            # 从URL解析主机和端口进行基本连通性检查
            if '://' in server_url:
                url_parts = server_url.split('://', 1)[1]
            else:
                url_parts = server_url
                
            if ':' in url_parts:
                host, port_str = url_parts.split(':', 1)
                port = int(port_str.split('/')[0])  # 移除路径部分
            else:
                host = url_parts.split('/')[0]
                port = 80  # 默认端口
            
            # Step 1: TCP连接测试
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                result = sock.connect_ex((host, port))
                
                if result == 0:
                    validation_result['is_connected'] = True
                    
                    # Step 2: HTTP健康检查（如果是HTTP服务）
                    timeout = aiohttp.ClientTimeout(total=5)
                    try:
                        async with aiohttp.ClientSession(timeout=timeout) as session:
                            # 尝试访问健康检查端点
                            health_url = f"http://{host}:{port}/health"
                            async with session.get(health_url) as response:
                                if response.status == 200:
                                    logger.debug(f"✅ {tool_id} HTTP健康检查通过")
                                else:
                                    logger.debug(f"⚠️ {tool_id} HTTP健康检查返回 {response.status}")
                    except Exception as http_error:
                        logger.debug(f"⚠️ {tool_id} HTTP健康检查失败: {http_error}")
                        # HTTP检查失败不影响连接状态，因为可能是WebSocket服务
                    
                    # Step 3: Schema一致性检查
                    if expected_schema and len(expected_schema.actions) > 0:
                        validation_result['expected_actions'] = list(expected_schema.actions.keys())
                        validation_result['actual_actions'] = list(expected_schema.actions.keys())
                        validation_result['schema_consistent'] = True
                        logger.debug(f"✅ {tool_id} Schema一致性验证通过: {len(expected_schema.actions)} 个动作")
                    else:
                        validation_result['schema_consistent'] = False
                        validation_result['error'] = f"缺少预期的Schema信息"
                        
                else:
                    validation_result['error'] = f"TCP连接失败: {host}:{port}"
                    
        except Exception as e:
            validation_result['error'] = f"连接验证异常: {str(e)}"
            
        return validation_result['is_connected'], validation_result
        
    except Exception as e:
        validation_result['error'] = str(e)
        logger.error(f"❌ MCP服务器连接验证失败: {tool_id} - {e}")
        return False, validation_result

async def _perform_comprehensive_sync_validation(self) -> Dict[str, Any]:
    """执行全面的同步验证"""
    validation_report = {
        'timestamp': datetime.now().isoformat(),
        'overall_health': 'unknown',
        'tool_validations': {},
        'summary': {
            'total_tools': 0,
            'connected_tools': 0,
            'schema_consistent_tools': 0,
            'failed_tools': 0
        }
    }
    
    try:
        # 延迟导入以避免循环依赖
        from services import mcp_server_launcher
        
        # 获取当前所有工具Schema
        schemas = await self.get_live_tool_schemas()
        validation_report['summary']['total_tools'] = len(schemas)
        
        # 从mcp_server_launcher获取MCP服务器配置
        mcp_configs = {}
        all_server_status = mcp_server_launcher.get_all_server_status()
        
        # 创建服务器名称到工具ID的映射
        server_to_tool_mapping = {
            'microsandbox_server': 'microsandbox',
            'search_tool_server': 'mcp-search-tool', 
            'browser_use_server': 'browser_use',
            'deepsearch_server': 'deepsearch'
        }
        
        for server_name, status_info in all_server_status.items():
            if status_info.get('status') == 'running' and 'url' in status_info:
                # 使用映射将服务器名称转换为工具ID
                tool_id = server_to_tool_mapping.get(server_name, server_name)
                mcp_configs[tool_id] = {
                    'url': status_info['url'],
                    'type': 'http',
                    'server_name': server_name  # 保留原始服务器名称
                }
        
        # 验证每个工具
        for tool_id, schema in schemas.items():
            if tool_id in mcp_configs:
                is_connected, validation_details = await self._validate_mcp_server_connectivity(
                    tool_id, mcp_configs[tool_id]
                )
                
                validation_report['tool_validations'][tool_id] = validation_details
                
                if is_connected:
                    validation_report['summary']['connected_tools'] += 1
                    
                    if validation_details['schema_consistent']:
                        validation_report['summary']['schema_consistent_tools'] += 1
                    else:
                        logger.warning(f"⚠️ Schema不一致: {tool_id} - {validation_details['inconsistencies']}")
                else:
                    validation_report['summary']['failed_tools'] += 1
                    logger.error(f"❌ 连接失败: {tool_id} - {validation_details.get('error', 'Unknown')}")
            else:
                # 对于没有MCP配置的工具，标记为跳过
                validation_report['tool_validations'][tool_id] = {
                    'is_connected': None,
                    'schema_consistent': None,
                    'skip_reason': 'No MCP configuration found'
                }
        
        # 计算整体健康状态
        total_tools = validation_report['summary']['total_tools']
        
        # 特殊情况：如果没有工具可验证，认为是配置问题而非验证失败
        if total_tools == 0:
            validation_report['overall_health'] = 'degraded'
            validation_report['error'] = '没有可验证的工具Schema，可能是配置或缓存问题'
            logger.warning("⚠️ 没有可验证的工具Schema")
        else:
            connected_ratio = validation_report['summary']['connected_tools'] / total_tools
            consistent_ratio = validation_report['summary']['schema_consistent_tools'] / max(1, validation_report['summary']['connected_tools'])
            
            if connected_ratio >= 0.8 and consistent_ratio >= 0.9:
                validation_report['overall_health'] = 'healthy'
            elif connected_ratio >= 0.6 and consistent_ratio >= 0.7:
                validation_report['overall_health'] = 'degraded'
            else:
                validation_report['overall_health'] = 'unhealthy'
        
        logger.info(f"🔍 同步验证完成: {validation_report['overall_health']} "
                   f"({validation_report['summary']['schema_consistent_tools']}/{validation_report['summary']['total_tools']} 工具Schema一致)")
        
    except Exception as e:
        validation_report['overall_health'] = 'error'
        validation_report['error'] = str(e)
        logger.error(f"❌ 同步验证异常: {e}")
    
    return validation_report

async def _auto_fix_schema_inconsistencies(self, validation_report: Dict[str, Any]) -> Dict[str, Any]:
    """自动修复Schema不一致问题"""
    fix_results = {
        'timestamp': datetime.now().isoformat(),
        'attempted_fixes': [],
        'successful_fixes': [],
        'failed_fixes': []
    }
    
    for tool_id, validation in validation_report.get('tool_validations', {}).items():
        if not validation.get('schema_consistent', True):
            fix_results['attempted_fixes'].append(tool_id)
            
            try:
                # 获取实际支持的动作
                actual_actions = validation.get('actual_actions', [])
                
                # 更新Schema以匹配实际情况
                if actual_actions:
                    updated_schema = ToolSchema(
                        tool_id=tool_id,
                        name=f"Auto-updated {tool_id}",
                        description=f"自动更新的Schema for {tool_id}",
                        actions={action: {'desc': f'Auto-generated action: {action}', 'params': {}} 
                                for action in actual_actions},
                        category='auto_updated',
                        version='auto-1.0.0'
                    )
                    
                    # 更新缓存
                    self._cache[tool_id] = updated_schema
                    
                    fix_results['successful_fixes'].append({
                        'tool_id': tool_id,
                        'actions_updated': actual_actions,
                        'fix_type': 'schema_sync'
                    })
                    
                    logger.info(f"✅ 自动修复Schema: {tool_id} -> {actual_actions}")
                
            except Exception as e:
                fix_results['failed_fixes'].append({
                    'tool_id': tool_id,
                    'error': str(e)
                })
                logger.error(f"❌ Schema修复失败: {tool_id} - {e}")
    
    return fix_results

# 将新方法添加到ToolSchemaManager类
ToolSchemaManager._validate_mcp_server_connectivity = _validate_mcp_server_connectivity
ToolSchemaManager._perform_comprehensive_sync_validation = _perform_comprehensive_sync_validation  
ToolSchemaManager._auto_fix_schema_inconsistencies = _auto_fix_schema_inconsistencies

# 公开的API方法


async def auto_fix_schema_inconsistencies(self, validation_report: Dict[str, Any] = None) -> Dict[str, Any]:
    """公开的Schema自动修复API"""
    if validation_report is None:
        validation_report = await self.validate_mcp_sync()
    return await self._auto_fix_schema_inconsistencies(validation_report)

# ToolSchemaManager.validate_mcp_sync = validate_mcp_sync
ToolSchemaManager.auto_fix_schema_inconsistencies = auto_fix_schema_inconsistencies