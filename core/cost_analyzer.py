#!/usr/bin/env python3
"""
成本分析器 - 为轨迹和种子任务提供成本信息注入功能
"""

import logging
import os
import json
import yaml
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class CostAnalysis:
    """成本分析结果数据结构"""
    total_tokens: int
    total_cost_usd: float
    cost_breakdown: Dict[str, Any]

@dataclass
class SynthesisCostAnalysis:
    """种子任务合成成本分析结果"""
    total_synthesis_tokens: int
    total_synthesis_cost_usd: float
    synthesis_breakdown: Dict[str, float]
    source_trajectory_cost_usd: float

class CostAnalyzer:
    """成本分析器 - 提供统一的成本计算和分析功能"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 🆕 从配置文件加载LLM配置
        self.llm_config = self._load_llm_config()
        self.default_provider = self.llm_config.get('default_provider', 'gemini')
        
        # 🆕 多模型动态定价配置（基于实际API定价）
        self.model_pricing = {
            # Gemini模型定价
            'gemini-2.5-flash': {
                'input_cost_per_million': 0.30,
                'output_cost_per_million': 2.50
            },
            'gemini-2.5-flash-lite-preview-06-17': {
                'input_cost_per_million': 0.075,  # Flash Lite更便宜
                'output_cost_per_million': 0.30
            },
            'gemini-2.5-pro': {
                'input_cost_per_million': 3.50,
                'output_cost_per_million': 15.00
            },
            # OpenAI模型定价
            'gpt-4o': {
                'input_cost_per_million': 2.50,
                'output_cost_per_million': 10.00
            },
            'gpt-4o-mini': {
                'input_cost_per_million': 0.15,
                'output_cost_per_million': 0.60
            },
            # vLLM/本地模型（几乎免费）
            'default-model': {
                'input_cost_per_million': 0.001,
                'output_cost_per_million': 0.001
            }
        }
        
        # step_logs文件路径配置
        self.step_logs_base_path = "output/logs/grouped"
        
        # 工具Token使用模式估算（基于实际观察）
        self.tool_token_patterns = {
            "microsandbox": {
                "base_input_tokens": 50,     # 基础指令token
                "output_tokens_per_call": 100,  # 每次调用输出
                "tokens_per_code_line": 10,    # 每行代码额外token
                "description": "MicroSandbox代码执行"
            },
            "browser_use": {
                "base_input_tokens": 150,    # 浏览器指令相对复杂
                "output_tokens_per_call": 200,  # 返回HTML/状态信息
                "tokens_per_action": 50,      # 每个操作额外token
                "description": "浏览器自动化"
            },
            "deepsearch": {
                "base_input_tokens": 100,    # 搜索查询
                "output_tokens_per_call": 500,  # 搜索结果通常较长
                "tokens_per_result": 100,     # 每个结果额外token
                "description": "深度搜索"
            },
            "search_tool": {
                "base_input_tokens": 30,     # 简单搜索
                "output_tokens_per_call": 50,   # 基础搜索结果
                "tokens_per_match": 20,       # 每个匹配额外token
                "description": "基础搜索"
            },
            "default": {
                "base_input_tokens": 50,     # 默认工具
                "output_tokens_per_call": 100,  # 默认输出
                "tokens_per_operation": 25,   # 每个操作额外token
                "description": "其他工具默认成本"
            }
        }
    
    def _load_llm_config(self) -> Dict[str, Any]:
        """
        加载LLM配置文件
        
        Returns:
            Dict[str, Any]: LLM配置信息
        """
        try:
            config_path = "config/llm_config.yaml"
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    self.logger.debug(f"✅ 加载LLM配置: {config_path}")
                    return config
            else:
                self.logger.warning(f"⚠️ LLM配置文件不存在: {config_path}")
                return {}
        except Exception as e:
            self.logger.error(f"❌ 加载LLM配置失败: {e}")
            return {}
    
    def _get_model_pricing(self, model_name: str) -> Dict[str, float]:
        """
        根据模型名称获取定价信息
        
        Args:
            model_name: 模型名称
            
        Returns:
            Dict[str, float]: 包含input_cost_per_million和output_cost_per_million的定价信息
        """
        # 首先检查精确匹配
        if model_name in self.model_pricing:
            return self.model_pricing[model_name]
        
        # 模糊匹配常见模型名称变体
        model_lower = model_name.lower()
        
        # Gemini模型匹配
        if 'gemini-2.5-flash-lite' in model_lower:
            return self.model_pricing['gemini-2.5-flash-lite-preview-06-17']
        elif 'gemini-2.5-flash' in model_lower:
            return self.model_pricing['gemini-2.5-flash']
        elif 'gemini-2.5-pro' in model_lower:
            return self.model_pricing['gemini-2.5-pro']
        
        # OpenAI模型匹配
        elif 'gpt-4o-mini' in model_lower:
            return self.model_pricing['gpt-4o-mini']
        elif 'gpt-4o' in model_lower:
            return self.model_pricing['gpt-4o']
        
        # 本地/vLLM模型匹配
        elif any(keyword in model_lower for keyword in ['vllm', 'local', 'default']):
            return self.model_pricing['default-model']
        
        # 默认回退到配置文件中的默认模型定价
        default_model = self.llm_config.get('llm_providers', {}).get(self.default_provider, {}).get('model', 'gemini-2.5-flash-lite-preview-06-17')
        if default_model in self.model_pricing:
            self.logger.warning(f"⚠️ 未知模型 {model_name}，使用默认模型 {default_model} 的定价")
            return self.model_pricing[default_model]
        
        # 最终回退
        self.logger.warning(f"⚠️ 未知模型 {model_name}，使用Gemini Flash Lite默认定价")
        return self.model_pricing['gemini-2.5-flash-lite-preview-06-17']

    def _load_step_logs_for_task(self, task_id: str, date_str: str = None) -> List[Dict[str, Any]]:
        """
        根据任务ID和日期加载相应的step_logs数据
        
        Args:
            task_id: 任务ID
            date_str: 日期字符串，如果不提供则使用今天
            
        Returns:
            List[Dict[str, Any]]: 匹配的step_logs数据
        """
        try:
            if not date_str:
                date_str = datetime.now().strftime("%Y-%m-%d")
            
            step_logs_file = os.path.join(
                self.step_logs_base_path, 
                date_str, 
                f"step_logs_{date_str}.jsonl"
            )
            
            if not os.path.exists(step_logs_file):
                self.logger.warning(f"⚠️ step_logs文件不存在: {step_logs_file}")
                return []
            
            step_logs = []
            with open(step_logs_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        log_entry = json.loads(line.strip())
                        if log_entry.get('task_id') == task_id:
                            # 提取steps数据
                            steps = log_entry.get('steps', [])
                            step_logs.extend(steps)
                    except json.JSONDecodeError:
                        continue
            
            self.logger.debug(f"✅ 加载step_logs数据: {len(step_logs)}个步骤，任务ID: {task_id}")
            return step_logs
            
        except Exception as e:
            self.logger.error(f"❌ 加载step_logs失败: {e}")
            return []

    def analyze_trajectory_cost(self, trajectory_data: Dict[str, Any], 
                              step_logs: List[Dict[str, Any]] = None) -> CostAnalysis:
        """
        分析轨迹的完整成本信息
        
        Args:
            trajectory_data: 轨迹数据
            step_logs: 步骤日志列表（包含token使用信息），如果为None则自动加载
            
        Returns:
            CostAnalysis: 成本分析结果
        """
        try:
            # 🆕 如果没有提供step_logs，则尝试自动加载
            if step_logs is None:
                task_id = trajectory_data.get('task_id')
                if task_id:
                    # 尝试从今天的日期加载
                    step_logs = self._load_step_logs_for_task(task_id)
                    
                    # 如果今天没有，尝试从轨迹时间戳推断日期
                    if not step_logs and 'timestamp' in trajectory_data:
                        try:
                            timestamp = trajectory_data['timestamp']
                            if isinstance(timestamp, str):
                                date_str = timestamp[:10]  # 提取YYYY-MM-DD部分
                                step_logs = self._load_step_logs_for_task(task_id, date_str)
                        except Exception:
                            pass
            
            # 1. 从step_logs收集LLM成本信息
            llm_cost_usd = 0.0
            total_tokens = 0
            cache_savings_usd = 0.0
            
            if step_logs:
                for step_log in step_logs:
                    # 🆕 从步骤日志中提取真实token使用信息
                    token_usage = None
                    
                    # 检查多种可能的token_usage位置
                    if 'token_usage' in step_log:
                        token_usage = step_log['token_usage']
                    elif 'llm_interaction' in step_log and 'token_usage' in step_log['llm_interaction']:
                        token_usage = step_log['llm_interaction']['token_usage']
                    
                    if token_usage:
                        prompt_tokens = token_usage.get('prompt_tokens', 0)
                        completion_tokens = token_usage.get('completion_tokens', 0)
                        cached_tokens = token_usage.get('cached_tokens', 0)
                        data_source = token_usage.get('data_source', 'unknown')
                        model_name = token_usage.get('model', 'unknown')
                        
                        total_tokens += prompt_tokens + completion_tokens
                        
                        # 🆕 基于实际模型的动态定价计算真实成本
                        pricing = self._get_model_pricing(model_name)
                        input_cost = (prompt_tokens / 1_000_000) * pricing['input_cost_per_million']
                        output_cost = (completion_tokens / 1_000_000) * pricing['output_cost_per_million']
                        
                        llm_cost_usd += input_cost + output_cost
                        
                        # 缓存节省（如果有缓存token）
                        if cached_tokens > 0:
                            cache_savings_usd += (cached_tokens / 1_000_000) * pricing['input_cost_per_million']
                        
                        self.logger.debug(f"✅ 使用真实token数据: {prompt_tokens}+{completion_tokens}, 模型: {model_name}, 来源: {data_source}")
                    
                    # 备用：从cost_info提取成本信息
                    elif 'cost_info' in step_log:
                        cost_info = step_log['cost_info']
                        llm_cost_usd += cost_info.get('estimated_cost_usd', 0.0)
                        cache_savings_usd += cost_info.get('cache_savings_usd', 0.0)
                
                if total_tokens > 0:
                    self.logger.info(f"✅ 成功加载真实token数据: {total_tokens} tokens, LLM成本: ${llm_cost_usd:.6f}")
            
            # 2. 分析工具使用成本
            tool_costs = self._analyze_tool_costs(trajectory_data, step_logs)
            
            # 3. 计算存储成本（基于轨迹大小的简单估算）
            storage_cost_usd = self._estimate_storage_cost(trajectory_data)
            
            # 4. 构建成本分解
            cost_breakdown = {
                "llm_cost_usd": llm_cost_usd,
                "tool_costs": tool_costs,
                "storage_cost_usd": storage_cost_usd,
                "cache_savings_usd": cache_savings_usd
            }
            
            # 5. 计算总成本
            total_cost_usd = llm_cost_usd + sum(tool_costs.values()) + storage_cost_usd
            
            return CostAnalysis(
                total_tokens=total_tokens,
                total_cost_usd=total_cost_usd,
                cost_breakdown=cost_breakdown
            )
            
        except Exception as e:
            self.logger.error(f"轨迹成本分析失败: {e}")
            # 返回默认的成本分析结果
            return CostAnalysis(
                total_tokens=0,
                total_cost_usd=0.0,
                cost_breakdown={
                    "llm_cost_usd": 0.0,
                    "tool_costs": {
                        "microsandbox_cost_usd": 0.0,
                        "browser_use_cost_usd": 0.0,
                        "deepsearch_cost_usd": 0.0,
                        "other_tools_cost_usd": 0.0
                    },
                    "storage_cost_usd": 0.0,
                    "cache_savings_usd": 0.0
                }
            )
    
    def analyze_synthesis_cost(self, synthesis_phases: List[Dict[str, Any]], 
                             source_trajectory_cost: float = 0.0) -> SynthesisCostAnalysis:
        """
        分析种子任务合成过程的成本
        
        Args:
            synthesis_phases: 合成阶段列表，每个阶段包含token使用和成本信息
            source_trajectory_cost: 源轨迹的成本
            
        Returns:
            SynthesisCostAnalysis: 合成成本分析结果
        """
        try:
            total_tokens = 0
            total_cost = 0.0
            breakdown = {}
            
            # 预定义的合成阶段
            phase_names = {
                "seed_extraction": "seed_extraction_cost_usd",
                "task_expansion": "task_expansion_cost_usd", 
                "quality_validation": "quality_validation_cost_usd"
            }
            
            # 分析每个合成阶段的成本
            for phase in synthesis_phases:
                phase_name = phase.get('phase', 'unknown')
                phase_tokens = phase.get('tokens', 0)
                phase_cost = phase.get('cost_usd', 0.0)
                
                total_tokens += phase_tokens
                total_cost += phase_cost
                
                # 映射到标准阶段名称
                if phase_name in phase_names:
                    breakdown[phase_names[phase_name]] = phase_cost
                else:
                    # 处理未知阶段
                    breakdown[f"{phase_name}_cost_usd"] = phase_cost
            
            # 确保所有预期阶段都有数值
            for standard_phase in phase_names.values():
                if standard_phase not in breakdown:
                    breakdown[standard_phase] = 0.0
            
            return SynthesisCostAnalysis(
                total_synthesis_tokens=total_tokens,
                total_synthesis_cost_usd=total_cost,
                synthesis_breakdown=breakdown,
                source_trajectory_cost_usd=source_trajectory_cost
            )
            
        except Exception as e:
            self.logger.error(f"合成成本分析失败: {e}")
            # 返回默认值
            return SynthesisCostAnalysis(
                total_synthesis_tokens=0,
                total_synthesis_cost_usd=0.0,
                synthesis_breakdown={
                    "seed_extraction_cost_usd": 0.0,
                    "task_expansion_cost_usd": 0.0,
                    "quality_validation_cost_usd": 0.0
                },
                source_trajectory_cost_usd=source_trajectory_cost
            )
    
    def _analyze_tool_costs(self, trajectory_data: Dict[str, Any], 
                           step_logs: List[Dict[str, Any]] = None) -> Dict[str, float]:
        """分析工具使用成本（基于真实token使用）"""
        tool_costs = {
            "microsandbox_cost_usd": 0.0,
            "browser_use_cost_usd": 0.0, 
            "deepsearch_cost_usd": 0.0,
            "other_tools_cost_usd": 0.0
        }
        
        try:
            # 🆕 从step_logs中提取真实工具使用和token统计
            if step_logs:
                for step_log in step_logs:
                    # 🆕 从tool_executions中提取真实工具使用数据
                    tool_executions = step_log.get('tool_executions', [])
                    
                    # 获取该步骤的LLM交互token数据
                    llm_token_usage = step_log.get('llm_interaction', {}).get('token_usage', {})
                    
                    # 处理每个工具执行
                    for tool_execution in tool_executions:
                        # 从tool_execution中提取工具信息
                        action = tool_execution.get('action', {})
                        service = action.get('service', 'unknown')
                        tool_name = action.get('tool', 'unknown')
                        
                        # 构造tool_info
                        tool_info = {
                            'service': service,
                            'tool': tool_name,
                            'input': action.get('input', ''),
                            'execution_status': tool_execution.get('execution_status', 'unknown'),
                            'execution_duration': tool_execution.get('execution_timing', {}).get('execution_duration_seconds', 0)
                        }
                        
                        # 计算基于真实token使用的成本
                        # 使用该步骤的LLM交互token数据
                        tool_cost = self._calculate_tool_cost_from_tokens(
                            service,  # 使用service作为工具名称
                            tool_info,
                            llm_token_usage  # 传递真实LLM token使用数据
                        )
                        
                        # 分类累计成本
                        if service == "microsandbox":
                            tool_costs["microsandbox_cost_usd"] += tool_cost
                        elif service == "browser_use":
                            tool_costs["browser_use_cost_usd"] += tool_cost
                        elif service == "deepsearch":
                            tool_costs["deepsearch_cost_usd"] += tool_cost
                        else:
                            tool_costs["other_tools_cost_usd"] += tool_cost
                        
                        self.logger.debug(f"✅ 处理工具执行: {service}.{tool_name}, 成本: ${tool_cost:.6f}")
                            
                self.logger.info(f"✅ 工具成本分析完成（基于真实token数据）: "
                               f"MicroSandbox=${tool_costs['microsandbox_cost_usd']:.6f}, "
                               f"Browser=${tool_costs['browser_use_cost_usd']:.6f}, "
                               f"DeepSearch=${tool_costs['deepsearch_cost_usd']:.6f}, "
                               f"Other=${tool_costs['other_tools_cost_usd']:.6f}")
            
            # 🆕 从轨迹数据中推断工具使用（改进的智能估算）
            has_tool_executions = any(
                step_log.get('tool_executions') for step_log in (step_logs or [])
            )
            
            if trajectory_data and not any(tool_costs.values()):
                # 只有在没有从step_logs获取真实数据时才使用智能估算
                estimated_costs = self._estimate_tool_costs_from_trajectory(trajectory_data)
                for key, value in estimated_costs.items():
                    tool_costs[key] = max(tool_costs[key], value)
                
                # 更精确的警告信息
                if has_tool_executions:
                    self.logger.warning(f"⚠️ 使用轨迹数据估算工具成本（工具执行缺少真实token数据）")
                else:
                    self.logger.debug(f"📊 任务无工具调用，跳过工具成本分析")
            
        except Exception as e:
            self.logger.error(f"工具成本分析失败: {e}")
        
        return tool_costs
    
    def _calculate_tool_cost_from_tokens(self, tool_name: str, tool_info: Dict[str, Any], 
                                       token_usage: Dict[str, Any]) -> float:
        """基于真实token使用计算工具成本。优先使用真实API数据，备用智能估算。"""
        try:
            # 🆕 优先使用真实token数据（来自工具调用时的LLM交互）
            actual_input = token_usage.get('prompt_tokens', 0)
            actual_output = token_usage.get('completion_tokens', 0)
            data_source = token_usage.get('data_source', 'unknown')
            
            # 检测是否为真实API数据
            is_real_api = (
                data_source == 'real_api' or 
                'api' in str(data_source).lower() or
                (actual_input > 0 and actual_output > 0)
            )
            
            if is_real_api and (actual_input > 0 or actual_output > 0):
                # 使用真实API返回的token数据
                input_tokens = actual_input
                output_tokens = actual_output
                
                self.logger.info(f"✅ 使用真实API token数据计算工具成本 {tool_name}: "
                               f"input={input_tokens}, output={output_tokens}, "
                               f"source={data_source}")
                
            else:
                # 使用智能估算的token数据
                input_tokens, output_tokens = self._estimate_tool_tokens(tool_name, tool_info)
                
                self.logger.debug(f"⚠️ 使用估算token数据计算工具成本 {tool_name}: "
                                f"input={input_tokens}, output={output_tokens}")
            
            # 🆕 计算成本（使用动态模型定价）
            model_name = token_usage.get('model', 'unknown')
            if model_name == 'unknown':
                # 如果没有模型信息，使用配置文件中的默认模型
                model_name = self.llm_config.get('llm_providers', {}).get(self.default_provider, {}).get('model', 'gemini-2.5-flash-lite-preview-06-17')
            
            pricing = self._get_model_pricing(model_name)
            input_cost = (input_tokens / 1_000_000) * pricing['input_cost_per_million']
            output_cost = (output_tokens / 1_000_000) * pricing['output_cost_per_million']
            
            total_cost = input_cost + output_cost
            
            self.logger.debug(f"💰 工具成本计算完成 {tool_name}: "
                            f"input={input_tokens} tokens (${input_cost:.6f}), "
                            f"output={output_tokens} tokens (${output_cost:.6f}), "
                            f"model={model_name}, total=${total_cost:.6f}")
            
            return total_cost
            
        except Exception as e:
            self.logger.error(f"计算工具成本失败 {tool_name}: {e}")
            # 返回基础默认成本
            return 0.001
    
    def _estimate_tool_tokens(self, tool_name: str, tool_info: Dict[str, Any]) -> Tuple[int, int]:
        """基于工具信息估算token使用量"""
        try:
            # 获取工具的token使用模式
            pattern = self.tool_token_patterns.get(tool_name, self.tool_token_patterns["default"])
            
            # 从工具信息中提取具体参数
            call_count = tool_info.get('call_count', 1)
            code_lines = tool_info.get('code_lines', 0)  # 对于microsandbox
            actions_count = tool_info.get('actions_count', 0)  # 对于browser_use
            results_count = tool_info.get('results_count', 0)  # 对于deepsearch
            matches_count = tool_info.get('matches_count', 0)  # 对于search_tool
            
            # 计算输入token数量
            input_tokens = pattern["base_input_tokens"] * call_count
            
            # 根据工具类型添加额外token
            if tool_name == "microsandbox":
                input_tokens += code_lines * pattern["tokens_per_code_line"]
            elif tool_name == "browser_use":
                input_tokens += actions_count * pattern["tokens_per_action"]
            elif tool_name == "deepsearch":
                input_tokens += results_count * pattern["tokens_per_result"]
            elif tool_name == "search_tool":
                input_tokens += matches_count * pattern["tokens_per_match"]
            else:
                # 默认工具
                operations = tool_info.get('operations_count', 1)
                input_tokens += operations * pattern["tokens_per_operation"]
            
            # 计算输出token数量
            output_tokens = pattern["output_tokens_per_call"] * call_count
            
            return input_tokens, output_tokens
            
        except Exception as e:
            self.logger.error(f"估算工具token失败 {tool_name}: {e}")
            return 50, 100  # 默认基础估算
    
    def _estimate_tool_costs_from_trajectory(self, trajectory_data: Dict[str, Any]) -> Dict[str, float]:
        """从轨迹数据智能估算工具成本（备用方法）"""
        estimated_costs = {
            "microsandbox_cost_usd": 0.0,
            "browser_use_cost_usd": 0.0, 
            "deepsearch_cost_usd": 0.0,
            "other_tools_cost_usd": 0.0
        }
        
        try:
            task_type = trajectory_data.get('task_type', '')
            task_content = trajectory_data.get('task_content', '')
            
            # 根据任务类型和内容智能估算
            if task_type == 'code' or 'python' in task_content.lower():
                # 代码任务估算
                code_lines = len(task_content.split('\n'))
                estimated_costs["microsandbox_cost_usd"] = self._calculate_tool_cost_from_tokens(
                    "microsandbox", 
                    {'call_count': 1, 'code_lines': code_lines}, 
                    {}
                )
            elif task_type == 'web' or any(word in task_content.lower() for word in ['browser', 'website', 'scrape']):
                # Web任务估算
                actions_count = max(1, task_content.count('click') + task_content.count('fill'))
                estimated_costs["browser_use_cost_usd"] = self._calculate_tool_cost_from_tokens(
                    "browser_use", 
                    {'call_count': 1, 'actions_count': actions_count}, 
                    {}
                )
            elif task_type == 'research' or any(word in task_content.lower() for word in ['search', 'research', 'find']):
                # 研究任务估算
                query_count = max(1, task_content.count('?'))
                estimated_costs["deepsearch_cost_usd"] = self._calculate_tool_cost_from_tokens(
                    "deepsearch", 
                    {'call_count': 1, 'results_count': query_count * 3}, 
                    {}
                )
            else:
                # 其他任务使用默认工具成本
                estimated_costs["other_tools_cost_usd"] = self._calculate_tool_cost_from_tokens(
                    "default", 
                    {'call_count': 1, 'operations_count': 1}, 
                    {}
                )
            
        except Exception as e:
            self.logger.error(f"智能估算工具成本失败: {e}")
        
        return estimated_costs
    
    def _estimate_storage_cost(self, trajectory_data: Dict[str, Any]) -> float:
        """估算存储成本"""
        try:
            # 简单的存储成本估算：基于数据大小
            import json
            data_size = len(json.dumps(trajectory_data, ensure_ascii=False))
            # 假设每KB存储成本为0.000001美元
            storage_cost = (data_size / 1024) * 0.000001
            return round(storage_cost, 6)
        except:
            return 0.0
    
    def inject_trajectory_cost(self, trajectory_data: Dict[str, Any], 
                             step_logs: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        为轨迹数据注入成本信息
        
        Args:
            trajectory_data: 原始轨迹数据
            step_logs: 步骤日志列表
            
        Returns:
            Dict[str, Any]: 注入成本信息后的轨迹数据
        """
        try:
            # 分析成本
            cost_analysis = self.analyze_trajectory_cost(trajectory_data, step_logs)
            
            # 创建副本并注入成本信息
            enhanced_trajectory = trajectory_data.copy()
            enhanced_trajectory['cost_analysis'] = asdict(cost_analysis)
            
            self.logger.info(f"轨迹成本注入完成 - Token: {cost_analysis.total_tokens}, "
                           f"成本: ${cost_analysis.total_cost_usd:.4f}")
            
            return enhanced_trajectory
            
        except Exception as e:
            self.logger.error(f"轨迹成本注入失败: {e}")
            return trajectory_data
    
    def inject_synthesis_cost(self, seed_task_data: Dict[str, Any],
                            synthesis_phases: List[Dict[str, Any]] = None,
                            source_trajectory_cost: float = 0.0) -> Dict[str, Any]:
        """
        为种子任务数据注入合成成本信息
        
        Args:
            seed_task_data: 原始种子任务数据
            synthesis_phases: 合成阶段列表
            source_trajectory_cost: 源轨迹成本
            
        Returns:
            Dict[str, Any]: 注入成本信息后的种子任务数据
        """
        try:
            # 分析合成成本
            synthesis_cost = self.analyze_synthesis_cost(synthesis_phases or [], source_trajectory_cost)
            
            # 创建副本并注入成本信息
            enhanced_seed_task = seed_task_data.copy()
            cost_analysis_dict = asdict(synthesis_cost)
            
            # 🆕 添加原始synthesis_phases到成本分析中
            cost_analysis_dict['synthesis_phases'] = synthesis_phases or []
            
            enhanced_seed_task['synthesis_cost_analysis'] = cost_analysis_dict
            
            self.logger.info(f"种子任务合成成本注入完成 - Token: {synthesis_cost.total_synthesis_tokens}, "
                           f"成本: ${synthesis_cost.total_synthesis_cost_usd:.4f}, "
                           f"阶段数: {len(synthesis_phases or [])}")
            
            return enhanced_seed_task
            
        except Exception as e:
            self.logger.error(f"种子任务成本注入失败: {e}")
            return seed_task_data


# 全局成本分析器实例
_cost_analyzer = None

def get_cost_analyzer() -> CostAnalyzer:
    """获取全局成本分析器实例"""
    global _cost_analyzer
    if _cost_analyzer is None:
        _cost_analyzer = CostAnalyzer()
    return _cost_analyzer