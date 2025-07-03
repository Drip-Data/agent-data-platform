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
            "cost_analysis": self._calculate_cost_metrics(enhanced_token_usage, duration)
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
        """🔧 增强Token使用统计 - 提供详细的成本分析数据"""
        if token_usage and all(key in token_usage for key in ['prompt_tokens', 'completion_tokens', 'total_tokens']):
            # 如果有真实的token数据，使用它
            enhanced = token_usage.copy()
        else:
            # 如果没有真实数据，使用估算
            prompt_text = " ".join([msg.get('content', '') for msg in prompt if isinstance(msg, dict)])
            estimated_prompt_tokens = len(prompt_text.split()) * 1.3  # 粗略估算：1.3 tokens per word
            estimated_completion_tokens = len(raw_response.split()) * 1.3
            
            enhanced = {
                "prompt_tokens": int(estimated_prompt_tokens),
                "completion_tokens": int(estimated_completion_tokens),
                "total_tokens": int(estimated_prompt_tokens + estimated_completion_tokens),
                "data_source": "estimated"  # 标记为估算数据
            }
        
        # 添加额外的分析字段
        enhanced.update({
            "response_length_chars": len(raw_response),
            "prompt_length_chars": sum(len(str(msg.get('content', ''))) for msg in prompt if isinstance(msg, dict)),
            "tokens_per_second": enhanced.get('completion_tokens', 0) / max(0.1, enhanced.get('response_time', 1)),
            "efficiency_ratio": enhanced.get('completion_tokens', 0) / max(1, enhanced.get('prompt_tokens', 1))
        })
        
        return enhanced
    
    def _calculate_cost_metrics(self, token_usage: Dict, duration: float) -> Dict:
        """💰 计算成本指标 - 支持多个LLM提供商的成本分析"""
        # 基础成本计算（以GPT-4为基准，可配置）
        cost_per_prompt_token = 0.00003  # $0.03 per 1K tokens
        cost_per_completion_token = 0.00006  # $0.06 per 1K tokens
        
        prompt_tokens = token_usage.get('prompt_tokens', 0)
        completion_tokens = token_usage.get('completion_tokens', 0)
        
        if isinstance(prompt_tokens, str) or isinstance(completion_tokens, str):
            # 如果是"unknown"等字符串，设为0
            prompt_tokens = 0
            completion_tokens = 0
        
        estimated_cost = (prompt_tokens * cost_per_prompt_token + 
                         completion_tokens * cost_per_completion_token) / 1000
        
        return {
            "estimated_cost_usd": round(estimated_cost, 6),
            "cost_per_second": round(estimated_cost / max(0.1, duration), 6),
            "tokens_per_dollar": int((prompt_tokens + completion_tokens) / max(0.000001, estimated_cost)),
            "efficiency_score": round(completion_tokens / max(0.1, duration), 2),  # tokens per second
            "cost_breakdown": {
                "prompt_cost": round(prompt_tokens * cost_per_prompt_token / 1000, 6),
                "completion_cost": round(completion_tokens * cost_per_completion_token / 1000, 6)
            }
        }
    
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