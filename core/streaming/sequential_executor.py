"""
Sequential Streaming Executor - Sequential流式执行引擎
核心组件，实现多步骤XML工具调用序列的自动化执行
"""

import asyncio
import logging
import re
import uuid
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from .state_manager import StreamingStateManager, ExecutionStep, ExecutionContext
from .result_injector import ResultInjector

logger = logging.getLogger(__name__)

class SequentialStreamingExecutor:
    """Sequential流式执行引擎"""
    
    def __init__(self, llm_client=None, tool_executor=None):
        """
        初始化Sequential执行引擎
        
        Args:
            llm_client: LLM客户端，用于继续推理
            tool_executor: 工具执行器，用于执行具体工具调用
        """
        self.llm_client = llm_client
        self.tool_executor = tool_executor
        self.result_injector = ResultInjector()
        self.execution_id = str(uuid.uuid4())[:8]
        
        logger.info(f"🚀 SequentialStreamingExecutor初始化 - ID: {self.execution_id}")
    
    async def execute_streaming_task(self, initial_response: str, 
                                   task_description: str = "",
                                   max_steps: int = 10,
                                   timeout_per_step: int = 300,
                                   total_timeout: int = 1800) -> Dict[str, Any]:
        """
        执行Sequential流式任务
        
        Args:
            initial_response: 初始XML响应
            task_description: 任务描述
            max_steps: 最大步骤数
            timeout_per_step: 单步超时（秒）
            total_timeout: 总超时（秒）
            
        Returns:
            执行结果字典
        """
        logger.info(f"🎯 开始Sequential执行 - 任务: {task_description[:100]}...")
        
        # 创建执行上下文
        context = ExecutionContext(
            task_description=task_description,
            initial_response=initial_response,
            current_response=initial_response,
            max_steps=max_steps,
            timeout_per_step=timeout_per_step,
            total_timeout=total_timeout
        )
        
        # 初始化状态管理器
        state_manager = StreamingStateManager(context)
        
        try:
            # 阶段1: 解析步骤序列
            steps = self._parse_sequential_steps(initial_response)
            logger.info(f"📋 解析到 {len(steps)} 个执行步骤")
            
            # 添加步骤到状态管理器
            for step in steps:
                state_manager.add_step(step)
            
            # 阶段2: Sequential执行循环
            current_response = initial_response
            step_execution_count = 0
            
            while state_manager.has_pending_executions():
                # 检查停止条件
                should_stop, stop_reason = state_manager.should_stop_execution()
                if should_stop:
                    logger.warning(f"⏹️ Sequential执行停止: {stop_reason}")
                    break
                
                # 获取下一个可执行步骤
                next_step = state_manager.get_next_executable_step()
                if not next_step:
                    logger.warning("⚠️ 没有找到可执行的步骤，结束执行")
                    break
                
                logger.info(f"🔄 执行步骤 {step_execution_count + 1}: {next_step.step_type} - {next_step.step_id}")
                
                # 标记步骤开始执行
                state_manager.mark_step_executing(next_step.step_id)
                
                # 执行步骤
                try:
                    result = await self._execute_step(next_step, state_manager)
                    
                    # 保存步骤结果
                    state_manager.add_step_result(next_step.step_id, result)
                    
                    # 注入结果到响应流
                    if result.get('success', True):
                        current_response = self._inject_step_result(
                            current_response, next_step, result
                        )
                        state_manager.update_response(current_response)
                    
                    step_execution_count += 1
                    
                    # 检查是否需要继续推理（生成新步骤）
                    if self._should_continue_reasoning(next_step, result):
                        logger.info("🧠 触发LLM继续推理...")
                        new_response = await self._continue_llm_reasoning(
                            state_manager, current_response
                        )
                        
                        if new_response and new_response != current_response:
                            # 解析新的步骤
                            new_steps = self._parse_sequential_steps(new_response)
                            logger.info(f"🆕 LLM生成了 {len(new_steps)} 个新步骤")
                            
                            # 添加新步骤
                            for step in new_steps:
                                if not any(s.step_id == step.step_id for s in state_manager.steps):
                                    state_manager.add_step(step)
                            
                            current_response = new_response
                            state_manager.update_response(current_response)
                    
                except Exception as e:
                    logger.error(f"❌ 步骤执行失败: {next_step.step_id} - {e}")
                    error_result = {
                        'success': False,
                        'error': str(e),
                        'step_id': next_step.step_id
                    }
                    state_manager.add_step_result(next_step.step_id, error_result)
                    
                    # 决定是否继续执行
                    if not self._should_continue_after_error(e, state_manager):
                        logger.error("💥 错误过多，停止Sequential执行")
                        break
            
            # 检查是否有答案完成标志
            if '<answer>' in current_response:
                state_manager.mark_completed()
            
            # 阶段3: 构建最终结果
            final_result = self._build_final_result(state_manager, current_response)
            
            logger.info(f"🎉 Sequential执行完成 - 执行了 {step_execution_count} 个步骤")
            return final_result
            
        except Exception as e:
            logger.error(f"💥 Sequential执行异常: {e}")
            return {
                'success': False,
                'error': str(e),
                'execution_id': self.execution_id,
                'partial_results': state_manager.step_results,
                'execution_stats': state_manager.get_execution_stats()
            }
    
    def _parse_sequential_steps(self, xml_response: str) -> List[ExecutionStep]:
        """
        解析Sequential XML步骤序列
        
        Args:
            xml_response: XML响应
            
        Returns:
            执行步骤列表
        """
        steps = []
        
        # 正则匹配所有XML标签
        xml_pattern = r'<(think|microsandbox|deepsearch|browser|search|answer)>(.*?)</\\1>'
        
        for match in re.finditer(xml_pattern, xml_response, re.DOTALL):
            tag_name = match.group(1)
            content = match.group(2).strip()
            position = match.span()
            
            # 生成步骤ID
            step_id = f"{tag_name}_{len(steps)}_{uuid.uuid4().hex[:6]}"
            
            step = ExecutionStep(
                step_id=step_id,
                step_type=tag_name,
                content=content,
                position=position,
                needs_execution=tag_name in ['microsandbox', 'deepsearch', 'browser', 'search']
            )
            
            steps.append(step)
            logger.debug(f"📝 解析步骤: {step_id} ({tag_name}) - {content[:50]}...")
        
        return steps
    
    async def _execute_step(self, step: ExecutionStep, 
                          state_manager: StreamingStateManager) -> Dict[str, Any]:
        """
        执行单个步骤
        
        Args:
            step: 执行步骤
            state_manager: 状态管理器
            
        Returns:
            执行结果
        """
        if not self.tool_executor:
            logger.warning("⚠️ 没有工具执行器，返回模拟结果")
            return {
                'success': True,
                'output': f"[模拟执行] {step.step_type}: {step.content[:100]}",
                'step_id': step.step_id,
                'execution_time': 0.1
            }
        
        try:
            start_time = datetime.now()
            
            # 根据步骤类型执行相应的工具
            if step.step_type == 'microsandbox':
                result = await self._execute_microsandbox(step, state_manager)
            elif step.step_type == 'deepsearch':
                result = await self._execute_deepsearch(step, state_manager)
            elif step.step_type == 'browser':
                result = await self._execute_browser(step, state_manager)
            elif step.step_type == 'search':
                result = await self._execute_search(step, state_manager)
            else:
                result = {
                    'success': False,
                    'error': f"未知的步骤类型: {step.step_type}"
                }
            
            execution_time = (datetime.now() - start_time).total_seconds()
            result['execution_time'] = execution_time
            result['step_id'] = step.step_id
            
            logger.info(f"✅ 步骤执行完成: {step.step_id} - 耗时: {execution_time:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"❌ 步骤执行异常: {step.step_id} - {e}")
            return {
                'success': False,
                'error': str(e),
                'step_id': step.step_id,
                'execution_time': 0
            }
    
    async def _execute_microsandbox(self, step: ExecutionStep, 
                                  state_manager: StreamingStateManager) -> Dict[str, Any]:
        """执行microsandbox步骤"""
        # 构建tool_id和action
        tool_id = "microsandbox"
        action = "auto_select"  # 使用auto_select让系统自动选择
        parameters = {"instruction": step.content}
        
        # 调用工具执行器
        if hasattr(self.tool_executor, '_execute_tool_action'):
            return await self.tool_executor._execute_tool_action({
                'tool_id': tool_id,
                'action': action,
                'parameters': parameters,
                'thinking': f"Sequential执行步骤: {step.step_id}"
            })
        else:
            # 降级处理
            return {
                'success': True,
                'output': f"[microsandbox] 执行代码: {step.content[:100]}...",
                'tool_id': tool_id,
                'action': action
            }
    
    async def _execute_deepsearch(self, step: ExecutionStep, 
                                state_manager: StreamingStateManager) -> Dict[str, Any]:
        """执行deepsearch步骤"""
        tool_id = "mcp-deepsearch"
        action = "auto_select"
        parameters = {"instruction": step.content}
        
        if hasattr(self.tool_executor, '_execute_tool_action'):
            return await self.tool_executor._execute_tool_action({
                'tool_id': tool_id,
                'action': action,
                'parameters': parameters,
                'thinking': f"Sequential执行步骤: {step.step_id}"
            })
        else:
            return {
                'success': True,
                'output': f"[deepsearch] 研究结果: {step.content[:100]}...",
                'tool_id': tool_id,
                'action': action
            }
    
    async def _execute_browser(self, step: ExecutionStep, 
                             state_manager: StreamingStateManager) -> Dict[str, Any]:
        """执行browser步骤"""
        tool_id = "browser_use"
        action = "auto_select"
        parameters = {"instruction": step.content}
        
        if hasattr(self.tool_executor, '_execute_tool_action'):
            return await self.tool_executor._execute_tool_action({
                'tool_id': tool_id,
                'action': action,
                'parameters': parameters,
                'thinking': f"Sequential执行步骤: {step.step_id}"
            })
        else:
            return {
                'success': True,
                'output': f"[browser] 浏览器操作: {step.content[:100]}...",
                'tool_id': tool_id,
                'action': action
            }
    
    async def _execute_search(self, step: ExecutionStep, 
                            state_manager: StreamingStateManager) -> Dict[str, Any]:
        """执行search步骤"""
        tool_id = "mcp-search-tool"
        action = "auto_select"
        parameters = {"instruction": step.content}
        
        if hasattr(self.tool_executor, '_execute_tool_action'):
            return await self.tool_executor._execute_tool_action({
                'tool_id': tool_id,
                'action': action,
                'parameters': parameters,
                'thinking': f"Sequential执行步骤: {step.step_id}"
            })
        else:
            return {
                'success': True,
                'output': f"[search] 搜索结果: {step.content[:100]}...",
                'tool_id': tool_id,
                'action': action
            }
    
    def _inject_step_result(self, current_response: str, step: ExecutionStep, 
                          result: Dict[str, Any]) -> str:
        """注入步骤结果到响应流"""
        try:
            return self.result_injector.inject_result(
                current_response, step.position, result, step.step_id
            )
        except Exception as e:
            logger.error(f"❌ 结果注入失败: {step.step_id} - {e}")
            return current_response
    
    def _should_continue_reasoning(self, step: ExecutionStep, 
                                 result: Dict[str, Any]) -> bool:
        """
        判断是否需要继续推理
        
        Args:
            step: 当前步骤
            result: 执行结果
            
        Returns:
            是否需要继续推理
        """
        # 如果是最后一个工具调用，且没有answer标签，需要继续推理
        if step.step_type in ['microsandbox', 'deepsearch', 'browser', 'search']:
            if result.get('success', True):
                # 检查当前响应中是否已有answer标签
                current_response = result.get('current_response', '')
                if '<answer>' not in current_response:
                    return True
        
        return False
    
    async def _continue_llm_reasoning(self, state_manager: StreamingStateManager, 
                                    current_response: str) -> Optional[str]:
        """
        触发LLM继续推理
        
        Args:
            state_manager: 状态管理器
            current_response: 当前响应
            
        Returns:
            新的响应或None
        """
        if not self.llm_client:
            logger.warning("⚠️ 没有LLM客户端，无法继续推理")
            return None
        
        try:
            # 构建继续推理的prompt
            continue_prompt = self._build_continue_prompt(state_manager, current_response)
            
            # 调用LLM继续推理
            if hasattr(self.llm_client, 'generate_response'):
                new_response = await self.llm_client.generate_response(continue_prompt)
                return new_response
            else:
                logger.warning("⚠️ LLM客户端没有generate_response方法")
                return None
                
        except Exception as e:
            logger.error(f"❌ LLM继续推理失败: {e}")
            return None
    
    def _build_continue_prompt(self, state_manager: StreamingStateManager, 
                             current_response: str) -> str:
        """构建继续推理的prompt"""
        stats = state_manager.get_execution_stats()
        
        prompt = f"""Continue your reasoning based on the tool execution results:

Current progress:
{current_response}

Execution status:
- Completed steps: {stats['completed_steps']}
- Failed steps: {stats['failed_steps']}
- Success rate: {stats['success_rate']:.2f}

Please continue with your analysis and next steps. Use the same XML format:
- <think>your reasoning</think> for analysis
- <microsandbox>code</microsandbox> for code execution
- <deepsearch>question</deepsearch> for research
- <browser>task</browser> for web browsing  
- <search>query</search> for file searching
- <answer>final result</answer> when complete

Continue:"""
        
        return prompt
    
    def _should_continue_after_error(self, error: Exception, 
                                   state_manager: StreamingStateManager) -> bool:
        """判断错误后是否继续执行"""
        stats = state_manager.get_execution_stats()
        
        # 如果错误率过高，停止执行
        if stats['error_count'] >= 3:
            return False
        
        # 如果是超时错误，停止执行
        if isinstance(error, asyncio.TimeoutError):
            return False
        
        # 其他错误继续执行
        return True
    
    def _build_final_result(self, state_manager: StreamingStateManager, 
                          final_response: str) -> Dict[str, Any]:
        """构建最终执行结果"""
        stats = state_manager.get_execution_stats()
        
        # 提取最终答案
        final_answer = ""
        answer_match = re.search(r'<answer>(.*?)</answer>', final_response, re.DOTALL)
        if answer_match:
            final_answer = answer_match.group(1).strip()
        
        # 提取所有thinking内容
        thinking_segments = re.findall(r'<think>(.*?)</think>', final_response, re.DOTALL)
        complete_thinking = '\n\n'.join(segment.strip() for segment in thinking_segments)
        
        return {
            'success': stats['failed_steps'] == 0,
            'execution_id': self.execution_id,
            'final_answer': final_answer,
            'complete_thinking': complete_thinking,
            'final_response': final_response,
            'execution_stats': stats,
            'step_results': state_manager.step_results,
            'steps_executed': [
                {
                    'step_id': step.step_id,
                    'step_type': step.step_type,
                    'content': step.content[:100],
                    'status': step.status,
                    'execution_time': step.execution_time
                }
                for step in state_manager.steps if step.needs_execution
            ],
            'state_summary': state_manager.get_state_summary()
        }