#!/usr/bin/env python3
"""
步骤级诊断日志记录器

用于记录Agent执行的每一步详细信息，包括LLM原始输出、工具调用原始响应等
"""

import json
import os
import aiofiles
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class StepDiagnosticLogger:
    """步骤级诊断日志记录器"""
    
    def __init__(self, base_path: str = "output/logs"):
        self.base_path = base_path
        self.current_task_data = None
        self.current_step_data = None
        
    def start_task(self, task_id: str, task_description: str):
        """开始任务记录"""
        self.current_task_data = {
            "task_id": task_id,
            "task_description": task_description,
            "task_start_time": datetime.now().isoformat(),
            "task_end_time": None,
            "task_duration_seconds": None,
            "task_final_status": None,
            "task_final_result": None,
            "steps": []
        }
        logger.info(f"🔍 开始记录任务步骤日志: {task_id}")
        
    def start_step(self, step_index: int):
        """开始步骤记录"""
        if not self.current_task_data:
            logger.warning("⚠️ 尝试开始步骤记录，但任务未初始化")
            return
            
        self.current_step_data = {
            "step_index": step_index,
            "step_start_time": datetime.now().isoformat(),
            "step_end_time": None,
            "step_duration_seconds": None,
            "llm_interaction": {},
            "parsing_stage": {},
            "tool_executions": []
        }
        logger.debug(f"📝 开始记录步骤 {step_index}")
        
    def log_llm_call(self, prompt: List[Dict], raw_response: str, stop_sequence: str, 
                     start_time: float, end_time: float, token_usage: Optional[Dict] = None):
        """记录LLM调用的原始数据，包含完整的Token使用统计"""
        if not self.current_step_data:
            logger.warning("⚠️ 尝试记录LLM调用，但步骤未初始化")
            return
            
        duration = end_time - start_time
        
        # 🔧 增强Token使用统计 - 提供详细的成本分析数据
        enhanced_token_usage = self._enhance_token_usage(token_usage, raw_response, prompt)
        
        self.current_step_data["llm_interaction"] = {
            "llm_call_start_time": datetime.fromtimestamp(start_time).isoformat(),
            "llm_call_end_time": datetime.fromtimestamp(end_time).isoformat(),
            "llm_call_duration_seconds": round(duration, 3),
            "prompt_sent_to_llm": prompt,
            "raw_llm_response": raw_response,
            "stop_sequence_triggered": stop_sequence,
            "token_usage": enhanced_token_usage,
            "total_cost_usd": self._calculate_simple_cost(enhanced_token_usage),
            "cost_analysis": self._calculate_enhanced_cost_analysis(enhanced_token_usage, duration)
        }
        logger.debug(f"🤖 记录LLM调用，响应长度: {len(raw_response)} 字符")
        
    def log_parsing_result(self, think_content: Optional[str], execution_block: Optional[str],
                          answer_content: Optional[str], actions: List[Dict], 
                          parsing_errors: List[str], start_time: float, end_time: float):
        """记录解析结果"""
        if not self.current_step_data:
            logger.warning("⚠️ 尝试记录解析结果，但步骤未初始化")
            return
            
        duration = end_time - start_time
        self.current_step_data["parsing_stage"] = {
            "parsing_start_time": datetime.fromtimestamp(start_time).isoformat(),
            "parsing_duration_seconds": round(duration, 4),
            "extracted_think_content": think_content,
            "extracted_execution_block": execution_block,
            "extracted_answer_content": answer_content,
            "parsed_actions": actions,
            "parsing_errors": parsing_errors
        }
        logger.debug(f"🔍 记录解析结果，识别到 {len(actions)} 个动作")
        
    def log_step_error(self, step_index: int, error_type: str, error_message: str, 
                      recovery_attempted: bool = False):
        """
        记录步骤执行错误
        """
        if not self.current_step_data:
            logger.warning("⚠️ 尝试记录步骤错误，但步骤未初始化")
            return
        
        error_info = {
            "step_index": step_index,
            "error_type": error_type,
            "error_message": error_message,
            "error_time": datetime.now().isoformat(),
            "recovery_attempted": recovery_attempted
        }
        
        # 如果step_data中没有errors字段，创建一个
        if "errors" not in self.current_step_data:
            self.current_step_data["errors"] = []
        
        self.current_step_data["errors"].append(error_info)
        logger.debug(f"❌ 记录步骤错误: {error_type} - {error_message}")
        
    def log_tool_execution(self, execution_index: int, action: Dict, 
                          toolscore_request: Dict, raw_response: Dict,
                          formatted_result: str, start_time: float, end_time: float,
                          execution_status: str, error_details: Optional[str] = None):
        """记录工具执行的原始数据，包含结构化错误信息"""
        if not self.current_step_data:
            logger.warning("⚠️ 尝试记录工具执行，但步骤未初始化")
            return
            
        duration = end_time - start_time
        
        # 🔧 结构化错误信息处理
        structured_error = self._structure_error_details(error_details, raw_response, action) if error_details else None
        
        execution_data = {
            "execution_index": execution_index,
            "action": action,
            "execution_timing": {
                "call_start_time": datetime.fromtimestamp(start_time).isoformat(),
                "call_end_time": datetime.fromtimestamp(end_time).isoformat(),
                "execution_duration_seconds": round(duration, 3)
            },
            "toolscore_request": toolscore_request,
            "toolscore_raw_response": raw_response,
            "formatted_result_for_llm": formatted_result,
            "execution_status": execution_status,
            "error_details": error_details,
            "structured_error": structured_error,
            "success_metrics": self._calculate_execution_metrics(execution_status, duration, raw_response)
        }
        
        self.current_step_data["tool_executions"].append(execution_data)
        logger.debug(f"🔧 记录工具执行: {action.get('service')}/{action.get('tool')}")
        
    def finish_step(self, step_conclusion: Optional[str] = None):
        """完成步骤记录"""
        if not self.current_step_data or not self.current_task_data:
            logger.warning("⚠️ 尝试完成步骤记录，但数据未初始化")
            return
            
        self.current_step_data["step_end_time"] = datetime.now().isoformat()
        
        # 计算步骤持续时间
        start_time = datetime.fromisoformat(self.current_step_data["step_start_time"])
        end_time = datetime.fromisoformat(self.current_step_data["step_end_time"])
        duration = (end_time - start_time).total_seconds()
        self.current_step_data["step_duration_seconds"] = round(duration, 3)
        
        # 添加步骤结论
        if step_conclusion:
            self.current_step_data["step_conclusion"] = step_conclusion
            
        # 将步骤添加到任务数据中
        self.current_task_data["steps"].append(self.current_step_data)
        logger.debug(f"✅ 完成步骤 {self.current_step_data['step_index']} 记录")
        
        # 重置当前步骤数据
        self.current_step_data = None
        
    async def finalize_task(self, final_status: str, final_result: str):
        """完成任务并写入日志文件"""
        if not self.current_task_data:
            logger.warning("⚠️ 尝试完成任务记录，但任务数据未初始化")
            return
            
        # 完成任务元数据
        self.current_task_data["task_end_time"] = datetime.now().isoformat()
        self.current_task_data["task_final_status"] = final_status
        self.current_task_data["task_final_result"] = final_result
        
        # 计算任务总持续时间
        start_time = datetime.fromisoformat(self.current_task_data["task_start_time"])
        end_time = datetime.fromisoformat(self.current_task_data["task_end_time"])
        duration = (end_time - start_time).total_seconds()
        self.current_task_data["task_duration_seconds"] = round(duration, 3)
        
        # 写入日志文件
        await self._save_log_file()
        
        # 重置任务数据
        self.current_task_data = None
    
    async def get_execution_steps(self) -> List[Dict]:
        """🔧 新增：获取当前任务的执行步骤列表
        
        Returns:
            List[Dict]: 包含步骤信息的列表，兼容TrajectoryResult.steps格式
        """
        if not self.current_task_data or not self.current_task_data.get("steps"):
            return []
        
        # 转换内部步骤格式为ExecutionStep兼容格式
        execution_steps = []
        for step in self.current_task_data["steps"]:
            # 创建ExecutionStep兼容的字典
            execution_step = {
                "step_id": f"step_{step.get('step_index', 0)}",
                "thinking": step.get("parsing_stage", {}).get("think_content", ""),
                "action_type": "tool_call" if step.get("tool_executions") else "reasoning",
                "action_params": {},
                "observation": "",
                "success": True,
                "duration": step.get("step_duration_seconds", 0.0)
            }
            
            # 提取工具调用信息
            tool_executions = step.get("tool_executions", [])
            if tool_executions:
                # 使用第一个工具调用的信息
                first_tool = tool_executions[0]
                execution_step["action_params"] = {
                    "tool_id": first_tool.get("tool_id", "unknown"),
                    "input": first_tool.get("input_data", {}),
                }
                execution_step["observation"] = str(first_tool.get("output_data", ""))
                execution_step["success"] = first_tool.get("success", True)
            
            execution_steps.append(execution_step)
        
        return execution_steps
        
    async def _save_log_file(self):
        """保存日志文件到按日期分组的目录"""
        try:
            # 创建日期分组目录
            date_str = datetime.now().strftime("%Y-%m-%d")
            log_dir = os.path.join(self.base_path, "grouped", date_str)
            os.makedirs(log_dir, exist_ok=True)
            
            # 日志文件路径
            log_file = os.path.join(log_dir, f"step_logs_{date_str}.jsonl")
            
            # 异步写入JSONL文件（单行格式）
            async with aiofiles.open(log_file, 'a', encoding='utf-8') as f:
                json_line = json.dumps(self.current_task_data, ensure_ascii=False)
                await f.write(json_line + '\n')
                
            logger.info(f"📊 步骤日志已保存: {log_file}")
            
        except Exception as e:
            logger.error(f"❌ 保存步骤日志失败: {e}")
            
    def _extract_think_content(self, response_text: str) -> Optional[str]:
        """从LLM响应中提取思考内容"""
        import re
        think_pattern = r'<think>(.*?)</think>'
        match = re.search(think_pattern, response_text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None
        
    def _extract_answer_content(self, response_text: str) -> Optional[str]:
        """从LLM响应中提取答案内容"""
        import re
        answer_pattern = r'<answer>(.*?)</answer>'
        match = re.search(answer_pattern, response_text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None
        
    def _extract_execution_block(self, response_text: str) -> Optional[str]:
        """从LLM响应中提取执行块内容"""
        import re
        # 查找 <execute_tools> 到 </execute_tools> 或 <execute_tools/> 之间的内容
        pattern1 = r'<execute_tools>(.*?)</execute_tools>'
        pattern2 = r'<execute_tools\s*/>'
        
        match1 = re.search(pattern1, response_text, re.DOTALL)
        if match1:
            return match1.group(1).strip()
            
        match2 = re.search(pattern2, response_text)
        if match2:
            return match2.group(0)
            
        return None
    
    def _enhance_token_usage(self, token_usage: Optional[Dict], raw_response: str, prompt: List[Dict]) -> Dict:
        """🔧 简化的Token使用统计 - 优先使用真实API数据"""
        
        # 检查是否有真实的API数据 - 扩展检测逻辑
        data_source = token_usage.get('data_source', 'unknown') if token_usage else 'unknown'
        
        # 如果来源包含这些关键词，认为是真实API数据
        is_real_api = any(keyword in str(data_source).lower() for keyword in ['real_api', 'api_response', 'gemini_api', 'api_provided']) if data_source != 'enhanced_estimation' else False
        
        if token_usage and is_real_api:
            # 使用真实API返回的token数据
            enhanced = {
                "prompt_tokens": token_usage.get('prompt_tokens', 0),
                "completion_tokens": token_usage.get('completion_tokens', 0),
                "total_tokens": token_usage.get('total_tokens', 0),
                "model": token_usage.get('model', 'gemini-2.5-flash-lite-preview-06-17'),
                "data_source": "real_api"
            }
            # 添加一些有用的性能分析
            enhanced.update({
                "tokens_per_second": enhanced.get('completion_tokens', 0) / max(0.1, token_usage.get('response_time', 1)),
                "efficiency_ratio": enhanced.get('completion_tokens', 0) / max(1, enhanced.get('prompt_tokens', 1))
            })
        elif token_usage and all(key in token_usage for key in ['prompt_tokens', 'completion_tokens']):
            # 使用提供的token数据并保留有用分析
            enhanced = token_usage.copy()  # 保留原始数据
            
            # 确保基本字段存在并标记数据源
            enhanced.update({
                "prompt_tokens": token_usage.get('prompt_tokens', 0),
                "completion_tokens": token_usage.get('completion_tokens', 0),
                "total_tokens": token_usage.get('total_tokens', token_usage.get('prompt_tokens', 0) + token_usage.get('completion_tokens', 0)),
                "model": token_usage.get('model', 'gemini-2.5-flash-lite-preview-06-17'),
                "data_source": data_source  # 保持原始数据源标记
            })
        else:
            # 进行基础估算
            prompt_text = " ".join([msg.get('content', '') for msg in prompt if isinstance(msg, dict)])
            estimated_prompt_tokens = self._accurate_token_estimation(prompt_text)
            estimated_completion_tokens = self._accurate_token_estimation(raw_response)
            
            enhanced = {
                "prompt_tokens": estimated_prompt_tokens,
                "completion_tokens": estimated_completion_tokens,
                "total_tokens": estimated_prompt_tokens + estimated_completion_tokens,
                "model": "gemini-2.5-flash-lite-preview-06-17",
                "data_source": "estimation"
            }
        
        return enhanced
    
    def _estimate_tokens(self, text: str) -> int:
        """简单的token估算函数"""
        if not text:
            return 0
        
        # 简单的token估算：中文约1.5字符/token，英文约4字符/token
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        
        estimated_tokens = int(chinese_chars / 1.5 + other_chars / 4.0)
        return max(estimated_tokens, 1)
    
    def _accurate_token_estimation(self, text: str) -> int:
        """基于Gemini特性的准确token估算"""
        if not text:
            return 0
        
        # 中文字符统计
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        japanese_chars = sum(1 for c in text if '\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff')
        korean_chars = sum(1 for c in text if '\uac00' <= c <= '\ud7af')
        
        # 其他字符
        other_chars = len(text) - chinese_chars - japanese_chars - korean_chars
        
        # 基于Gemini tokenizer的改进估算
        # 中文: ~1.5 chars/token, 日文: ~2 chars/token, 韩文: ~2 chars/token, 英文: ~4 chars/token
        estimated_tokens = int(
            chinese_chars / 1.5 + 
            japanese_chars / 2.0 + 
            korean_chars / 2.0 + 
            other_chars / 4.0
        )
        
        # 考虑特殊标记和格式
        special_tokens = text.count('<') + text.count('>') + text.count('{') + text.count('}')
        estimated_tokens += special_tokens * 0.5  # 特殊标记通常占用额外token
        
        return max(estimated_tokens, 1)
    
    def _analyze_content_type(self, content: str) -> Dict[str, Any]:
        """分析内容类型和复杂度"""
        import re
        
        analysis = {
            "has_code": bool(re.search(r'```|`[^`]+`|def |class |import |function', content)),
            "has_json": bool(re.search(r'\{[^}]*\}|\[[^\]]*\]', content)),
            "has_xml": bool(re.search(r'<[^>]+>', content)),
            "has_markdown": bool(re.search(r'#+|[*_]{1,2}[^*_]+[*_]{1,2}|\[.*\]\(.*\)', content)),
            "line_count": content.count('\n') + 1,
            "avg_line_length": len(content) / max(1, content.count('\n') + 1),
            "complexity_score": self._calculate_content_complexity(content)
        }
        
        return analysis
    
    def _analyze_prompt_complexity(self, prompt: List[Dict]) -> Dict[str, Any]:
        """分析prompt复杂度"""
        total_length = sum(len(str(msg.get('content', ''))) for msg in prompt)
        message_count = len(prompt)
        
        # 检测特殊指令
        all_content = " ".join([str(msg.get('content', '')) for msg in prompt])
        
        complexity = {
            "message_count": message_count,
            "total_length": total_length,
            "avg_message_length": total_length / max(1, message_count),
            "has_system_prompt": any(msg.get('role') == 'system' for msg in prompt),
            "has_examples": 'example' in all_content.lower() or '示例' in all_content,
            "has_constraints": any(word in all_content.lower() for word in ['must', 'should', 'cannot', '必须', '不能']),
            "instruction_density": self._calculate_instruction_density(all_content)
        }
        
        return complexity
    
    def _calculate_content_complexity(self, content: str) -> float:
        """计算内容复杂度分数 (0-10)"""
        score = 0.0
        
        # 长度因子 (0-2分)
        score += min(2.0, len(content) / 1000)
        
        # 结构化内容 (0-3分)
        if '{' in content or '[' in content:
            score += 1.0
        if '<' in content and '>' in content:
            score += 1.0
        if '```' in content:
            score += 1.0
        
        # 特殊字符密度 (0-2分)
        special_chars = sum(1 for c in content if c in '{}[]()<>*_`#|\\')
        score += min(2.0, special_chars / max(1, len(content)) * 100)
        
        # 换行密度 (0-2分)
        line_density = content.count('\n') / max(1, len(content)) * 100
        score += min(2.0, line_density * 10)
        
        # 数字和标点密度 (0-1分)
        numbers_punct = sum(1 for c in content if c.isdigit() or c in '.,;:!?')
        score += min(1.0, numbers_punct / max(1, len(content)) * 50)
        
        return min(10.0, score)
    
    def _calculate_instruction_density(self, content: str) -> float:
        """计算指令密度"""
        instruction_words = [
            'please', 'must', 'should', 'need', 'require', 'ensure', 'make sure',
            '请', '必须', '需要', '确保', '要求', '应该', '务必'
        ]
        
        content_lower = content.lower()
        instruction_count = sum(1 for word in instruction_words if word in content_lower)
        word_count = len(content.split())
        
        return instruction_count / max(1, word_count) * 100
    
    def _estimate_cache_savings(self, prompt_tokens: int) -> Dict[str, Any]:
        """估算缓存节省（基于Gemini 2.5缓存机制）"""
        if prompt_tokens < 1024:  # 不满足Gemini 2.5最小缓存要求
            return {"eligible": False, "reason": "Below minimum 1024 tokens"}
        
        # 基于Gemini 2.5 Flash定价
        normal_cost = (prompt_tokens / 1_000_000) * 0.30  # $0.30 per 1M input tokens
        cache_cost = (prompt_tokens / 1_000_000) * 0.075  # $0.075 per 1M cached tokens (25% of input cost)
        
        savings_per_reuse = normal_cost - cache_cost
        
        return {
            "eligible": True,
            "normal_cost_usd": round(normal_cost, 6),
            "cache_cost_usd": round(cache_cost, 6),
            "savings_per_reuse_usd": round(savings_per_reuse, 6),
            "break_even_uses": 2,  # 缓存后第2次使用开始节省
            "potential_savings_5_uses": round(savings_per_reuse * 4, 6)  # 使用5次的节省
        }
    
    def _calculate_simple_cost(self, token_usage: Dict) -> float:
        """根据系统实际使用的模型计算简单成本"""
        prompt_tokens = token_usage.get('prompt_tokens', 0)
        completion_tokens = token_usage.get('completion_tokens', 0)
        model = token_usage.get('model', 'gemini-2.5-flash-lite-preview-06-17')
        
        # 确保token数为数字类型
        if isinstance(prompt_tokens, str):
            prompt_tokens = 0
        if isinstance(completion_tokens, str):
            completion_tokens = 0
        
        # Gemini 2.5系列定价（美元每100万token）
        pricing_config = {
            "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
            "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
            "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
            "gemini-2.5-flash-lite-preview-06-17": {"input": 0.10, "output": 0.40}  # 当前系统使用的模型
        }
        
        # 获取模型定价，默认使用flash-lite
        pricing = pricing_config.get(model, pricing_config["gemini-2.5-flash-lite"])
        
        # 计算总成本
        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]
        total_cost = input_cost + output_cost
        
        return round(total_cost, 6)
    
    def _calculate_enhanced_cost_analysis(self, token_usage: Dict, duration: float) -> Dict:
        """计算增强的成本分析 - 保留有用信息"""
        prompt_tokens = token_usage.get('prompt_tokens', 0)
        completion_tokens = token_usage.get('completion_tokens', 0)
        model = token_usage.get('model', 'gemini-2.5-flash-lite-preview-06-17')
        
        # 确保token数为数字类型
        if isinstance(prompt_tokens, str):
            prompt_tokens = 0
        if isinstance(completion_tokens, str):
            completion_tokens = 0
        
        # 定价配置
        pricing_config = {
            "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
            "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
            "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
            "gemini-2.5-flash-lite-preview-06-17": {"input": 0.10, "output": 0.40}
        }
        
        pricing = pricing_config.get(model, pricing_config["gemini-2.5-flash-lite"])
        
        # 计算成本分解
        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]
        total_cost = input_cost + output_cost
        
        # 性能指标
        tokens_per_second = completion_tokens / max(0.1, duration)
        cost_per_second = total_cost / max(0.1, duration)
        tokens_per_dollar = (prompt_tokens + completion_tokens) / max(0.000001, total_cost)
        efficiency_score = completion_tokens / max(0.1, duration)
        
        # 缓存分析
        cache_eligible = prompt_tokens >= 1024
        cache_savings_usd = 0.0
        cache_efficiency = 0.0
        
        if cache_eligible:
            # 计算缓存节省（估算75%节省）
            cache_cost = input_cost * 0.25  # 25%的原始成本
            cache_savings_usd = input_cost - cache_cost
            cache_efficiency = cache_savings_usd / input_cost if input_cost > 0 else 0
        
        # 优化建议
        optimization_suggestions = []
        if prompt_tokens >= 1024:
            optimization_suggestions.append("输入超过1024 tokens，建议启用上下文缓存以节省成本")
        if cache_efficiency == 0 and cache_eligible:
            optimization_suggestions.append("缓存使用率仅0.0%，可优化空间较大")
        
        return {
            "model": model,
            "estimated_cost_usd": round(total_cost, 6),
            "cost_per_second": round(cost_per_second, 6),
            "tokens_per_dollar": int(tokens_per_dollar),
            "efficiency_score": round(efficiency_score, 2),
            "cost_breakdown": {
                "input_cost": round(input_cost, 6),
                "output_cost": round(output_cost, 6),
                "total_cost": round(total_cost, 6)
            },
            "cache_analysis": {
                "cache_eligible": cache_eligible,
                "cache_savings_usd": round(cache_savings_usd, 6),
                "cache_efficiency": round(cache_efficiency, 3),
                "without_cache_cost": round(input_cost + output_cost, 6)
            },
            "performance_metrics": {
                "tokens_per_second": round(tokens_per_second, 1),
                "cost_per_input_token": round(pricing["input"] / 1_000_000, 6),
                "cost_per_output_token": round(pricing["output"] / 1_000_000, 6),
                "total_tokens": prompt_tokens + completion_tokens,
                "cost_efficiency_rating": self._get_efficiency_rating(efficiency_score)
            },
            "optimization_suggestions": optimization_suggestions
        }
    
    def _get_efficiency_rating(self, efficiency_score: float) -> str:
        """根据效率分数获取评级"""
        if efficiency_score >= 200:
            return "Excellent"
        elif efficiency_score >= 100:
            return "Good"
        elif efficiency_score >= 50:
            return "Fair"
        else:
            return "Poor"
    
    def _calculate_cost_metrics(self, token_usage: Dict, duration: float) -> Dict:
        """💰 基于Gemini 2.5实际定价的精确成本计算"""
        
        prompt_tokens = token_usage.get('prompt_tokens', 0)
        completion_tokens = token_usage.get('completion_tokens', 0)
        cached_tokens = token_usage.get('cached_tokens', 0)
        model = token_usage.get('model', 'gemini-2.5-flash')
        
        # 确保token数为数字类型
        if isinstance(prompt_tokens, str) or isinstance(completion_tokens, str):
            prompt_tokens = 0
            completion_tokens = 0
        
        # Gemini 2.5系列实际定价（美元每100万token）
        pricing_config = {
            "gemini-2.5-pro": {
                "input": 1.25,      # $1.25 per 1M input tokens
                "output": 10.0,     # $10.0 per 1M output tokens  
                "cache": 0.3125,    # $0.3125 per 1M cached tokens (25% of input)
                "storage_per_hour": 4.50  # $4.50 per 1M tokens per hour storage
            },
            "gemini-2.5-flash": {
                "input": 0.30,      # $0.30 per 1M input tokens
                "output": 2.50,     # $2.50 per 1M output tokens
                "cache": 0.075,     # $0.075 per 1M cached tokens (25% of input)
                "storage_per_hour": 1.0   # $1.0 per 1M tokens per hour storage
            },
            "gemini-2.5-flash-lite": {
                "input": 0.10,      # $0.10 per 1M input tokens
                "output": 0.40,     # $0.40 per 1M output tokens
                "cache": 0.025,     # $0.025 per 1M cached tokens (25% of input)
                "storage_per_hour": 1.0   # Same as flash
            }
        }
        
        # 获取模型定价，默认使用flash
        pricing = pricing_config.get(model, pricing_config["gemini-2.5-flash"])
        
        # 计算实际输入成本（排除缓存部分）
        actual_input_tokens = max(0, prompt_tokens - cached_tokens)
        input_cost = (actual_input_tokens / 1_000_000) * pricing["input"]
        
        # 缓存成本（如果有使用缓存）
        cache_cost = (cached_tokens / 1_000_000) * pricing["cache"]
        
        # 输出成本
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]
        
        # 总成本
        total_cost = input_cost + cache_cost + output_cost
        
        # 计算如果没有缓存的成本（用于比较节省）
        no_cache_cost = (prompt_tokens / 1_000_000) * pricing["input"] + output_cost
        cache_savings = no_cache_cost - total_cost
        
        return {
            "model": model,
            "estimated_cost_usd": round(total_cost, 6),
            "cost_per_second": round(total_cost / max(0.1, duration), 6),
            "tokens_per_dollar": int((prompt_tokens + completion_tokens) / max(0.000001, total_cost)),
            "efficiency_score": round(completion_tokens / max(0.1, duration), 2),
            
            # 详细成本分解
            "cost_breakdown": {
                "input_cost": round(input_cost, 6),
                "cache_cost": round(cache_cost, 6),
                "output_cost": round(output_cost, 6),
                "total_cost": round(total_cost, 6)
            },
            
            # 缓存效益分析
            "cache_analysis": {
                "cached_tokens": cached_tokens,
                "cache_savings_usd": round(cache_savings, 6),
                "cache_efficiency": round(cache_savings / max(0.000001, no_cache_cost) * 100, 2),
                "without_cache_cost": round(no_cache_cost, 6)
            },
            
            # 性能指标
            "performance_metrics": {
                "cost_per_input_token": round(total_cost / max(1, prompt_tokens) * 1000, 6),  # 每1K输入token成本
                "cost_per_output_token": round(output_cost / max(1, completion_tokens) * 1000, 6),  # 每1K输出token成本
                "total_tokens": prompt_tokens + completion_tokens,
                "cost_efficiency_rating": self._calculate_cost_efficiency_rating(total_cost, prompt_tokens + completion_tokens)
            },
            
            # 优化建议
            "optimization_suggestions": self._generate_cost_optimization_suggestions(
                model, total_cost, prompt_tokens, completion_tokens, cached_tokens
            )
        }
    
    def _calculate_cost_efficiency_rating(self, cost: float, total_tokens: int) -> str:
        """计算成本效率评级"""
        if total_tokens == 0:
            return "N/A"
        
        cost_per_1k_tokens = (cost / total_tokens) * 1000
        
        if cost_per_1k_tokens <= 0.0001:
            return "Excellent"
        elif cost_per_1k_tokens <= 0.0005:
            return "Good"
        elif cost_per_1k_tokens <= 0.002:
            return "Fair"
        else:
            return "Expensive"
    
    def _generate_cost_optimization_suggestions(self, model: str, cost: float, 
                                              prompt_tokens: int, completion_tokens: int, 
                                              cached_tokens: int) -> List[str]:
        """生成成本优化建议"""
        suggestions = []
        
        # 模型选择建议
        if model == "gemini-2.5-pro" and completion_tokens < 1000:
            suggestions.append("对于简短回复，考虑使用gemini-2.5-flash以降低成本")
        
        if model == "gemini-2.5-flash" and prompt_tokens > 50000:
            suggestions.append("大量输入时，gemini-2.5-flash-lite可能更经济")
        
        # 缓存建议
        if prompt_tokens > 1024 and cached_tokens == 0:
            suggestions.append("输入超过1024 tokens，建议启用上下文缓存以节省成本")
        
        if cached_tokens > 0:
            cache_ratio = cached_tokens / prompt_tokens
            if cache_ratio > 0.5:
                suggestions.append(f"缓存效果良好（{cache_ratio:.1%}），继续保持")
            else:
                suggestions.append("缓存使用率较低，可优化重复内容的识别")
        
        # 成本警告
        if cost > 0.01:  # 超过1美分
            suggestions.append("单次请求成本较高，建议检查输入长度和模型选择")
        
        # 效率建议
        if completion_tokens > prompt_tokens * 2:
            suggestions.append("输出远超输入，考虑优化prompt以获得更简洁的回复")
        
        return suggestions
    
    def _structure_error_details(self, error_details: str, raw_response: Dict, action: Dict) -> Dict:
        """🔧 结构化错误信息 - 便于自动化错误分析"""
        from core.interfaces import ErrorMessageConstants
        
        structured = {
            "error_message": error_details,
            "error_category": self._categorize_error(error_details),
            "error_source": self._identify_error_source(raw_response, action),
            "recoverable": self._assess_error_recoverability(error_details),
            "suggested_actions": self._suggest_error_recovery(error_details, action),
            "error_context": {
                "tool_service": action.get('service', 'unknown'),
                "tool_action": action.get('tool', 'unknown'),
                "parameters": action.get('parameters', {}),
                "response_status": raw_response.get('status', 'unknown') if isinstance(raw_response, dict) else 'no_response'
            }
        }
        
        return structured
    
    def _categorize_error(self, error_details: str) -> str:
        """分类错误类型"""
        error_lower = error_details.lower()
        
        if any(keyword in error_lower for keyword in ['timeout', '超时', 'timed out']):
            return 'timeout_error'
        elif any(keyword in error_lower for keyword in ['connection', '连接', 'network']):
            return 'network_error'
        elif any(keyword in error_lower for keyword in ['parameter', '参数', 'invalid']):
            return 'parameter_error'
        elif any(keyword in error_lower for keyword in ['permission', '权限', 'unauthorized']):
            return 'permission_error'
        elif any(keyword in error_lower for keyword in ['not found', '未找到', '404']):
            return 'resource_not_found'
        else:
            return 'general_error'
    
    def _identify_error_source(self, raw_response: Dict, action: Dict) -> str:
        """识别错误来源"""
        if not isinstance(raw_response, dict):
            return 'response_format_error'
        
        if 'error' in raw_response:
            return 'tool_service_error'
        elif raw_response.get('status') == 'timeout':
            return 'execution_timeout'
        elif not raw_response.get('result'):
            return 'empty_response'
        else:
            return 'unknown_source'
    
    def _assess_error_recoverability(self, error_details: str) -> bool:
        """评估错误是否可恢复"""
        error_lower = error_details.lower()
        
        # 不可恢复的错误
        non_recoverable = ['permission denied', '权限不足', 'unauthorized', 'not found', '未找到']
        if any(keyword in error_lower for keyword in non_recoverable):
            return False
        
        # 可能可恢复的错误
        recoverable = ['timeout', '超时', 'connection', '连接', 'parameter', '参数']
        if any(keyword in error_lower for keyword in recoverable):
            return True
        
        return False  # 默认认为不可恢复
    
    def _suggest_error_recovery(self, error_details: str, action: Dict) -> List[str]:
        """建议错误恢复方案"""
        suggestions = []
        error_lower = error_details.lower()
        
        if 'timeout' in error_lower or '超时' in error_lower:
            suggestions.extend([
                "增加工具执行超时时间",
                "重试执行，使用更短的参数",
                "检查网络连接状态"
            ])
        elif 'parameter' in error_lower or '参数' in error_lower:
            suggestions.extend([
                "检查参数格式是否正确",
                "验证必需参数是否完整",
                "参考工具文档确认参数名称"
            ])
        elif 'connection' in error_lower or '连接' in error_lower:
            suggestions.extend([
                "检查服务是否正常运行",
                "验证网络连接",
                "重启相关服务"
            ])
        else:
            suggestions.append("查看详细错误日志确定具体原因")
        
        return suggestions
    
    def _calculate_execution_metrics(self, execution_status: str, duration: float, raw_response: Dict) -> Dict:
        """计算执行成功指标"""
        is_success = execution_status == 'success'
        
        # 响应质量评估
        response_quality = 0.0
        if isinstance(raw_response, dict):
            if raw_response.get('result'):
                response_quality += 0.5
            if raw_response.get('status') == 'success':
                response_quality += 0.3
            if 'error' not in raw_response:
                response_quality += 0.2
        
        return {
            "success": is_success,
            "execution_duration_seconds": round(duration, 3),
            "performance_rating": "fast" if duration < 2.0 else "normal" if duration < 5.0 else "slow",
            "response_quality_score": round(response_quality, 2),
            "execution_efficiency": round(1.0 / max(0.1, duration), 3)  # executions per second potential
        }