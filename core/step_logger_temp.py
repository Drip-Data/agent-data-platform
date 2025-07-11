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
            "total_cost_usd": self._calculate_simple_cost(enhanced_token_usage)
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
        """🔧 简化的Token使用统计 - 优先使用真实API数据"""
        
        # 检查是否有真实的API数据
        if token_usage and token_usage.get('data_source') in ['real_api', 'api_response', 'gemini_api']:
            # 使用真实API返回的token数据
            enhanced = {
                "prompt_tokens": token_usage.get('prompt_tokens', 0),
                "completion_tokens": token_usage.get('completion_tokens', 0),
                "total_tokens": token_usage.get('total_tokens', 0),
                "model": token_usage.get('model', 'gemini-2.5-flash-lite-preview-06-17'),
                "data_source": "real_api"
            }
        elif token_usage and all(key in token_usage for key in ['prompt_tokens', 'completion_tokens']):
            # 使用提供的token数据但标记为估算
            enhanced = {
                "prompt_tokens": token_usage.get('prompt_tokens', 0),
                "completion_tokens": token_usage.get('completion_tokens', 0),
                "total_tokens": token_usage.get('total_tokens', token_usage.get('prompt_tokens', 0) + token_usage.get('completion_tokens', 0)),
                "model": token_usage.get('model', 'gemini-2.5-flash-lite-preview-06-17'),
                "data_source": "estimation"
            }
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
    
