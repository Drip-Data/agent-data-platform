

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
    
    def __init__(self, llm_client=None, tool_executor=None, memory_manager=None):
        """
        初始化Sequential执行引擎
        
        Args:
            llm_client: LLM客户端，用于继续推理
            tool_executor: 工具执行器，用于执行具体工具调用
            memory_manager: 记忆管理器，用于存储和检索上下文
        """
        self.llm_client = llm_client
        self.tool_executor = tool_executor
        self.memory_manager = memory_manager
        self.result_injector = ResultInjector()
        self.execution_id = str(uuid.uuid4())[:8]
        
        logger.info(f"🚀 SequentialStreamingExecutor初始化 - ID: {self.execution_id}")
    
    async def execute_streaming_task(self, initial_response: str, 
                                   task_description: str = "",
                                   max_steps: int = 10,
                                   timeout_per_step: int = 300,
                                   total_timeout: int = 1800,
                                   session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        执行Sequential流式任务
        
        Args:
            initial_response: 初始XML响应
            task_description: 任务描述
            max_steps: 最大步骤数
            timeout_per_step: 单步超时（秒）
            total_timeout: 总超时（秒）
            session_id: 当前任务的会话ID
        """
        logger.info(f"🎯 开始Sequential执行 - 任务: {task_description[:100]}...")
        
        if not session_id:
            session_id = f"session_{self.execution_id}"

        context = ExecutionContext(
            task_description=task_description,
            initial_response=initial_response,
            current_response=initial_response,
            max_steps=max_steps,
            timeout_per_step=timeout_per_step,
            total_timeout=total_timeout
        )
        
        state_manager = StreamingStateManager(context)
        
        try:
            steps = self._parse_sequential_steps(initial_response)
            logger.info(f"📋 解析到 {len(steps)} 个执行步骤")
            
            for step in steps:
                state_manager.add_step(step)
            
            current_response = initial_response
            step_execution_count = 0
            
            while state_manager.has_pending_executions():
                should_stop, stop_reason = state_manager.should_stop_execution()
                if should_stop:
                    logger.warning(f"⏹️ Sequential执行停止: {stop_reason}")
                    break
                
                next_step = state_manager.get_next_executable_step()
                if not next_step:
                    logger.warning("⚠️ 没有找到可执行的步骤，结束执行")
                    break
                
                logger.info(f"🔄 执行步骤 {step_execution_count + 1}: {next_step.step_type} - {next_step.step_id}")
                
                state_manager.mark_step_executing(next_step.step_id)
                
                try:
                    result = await self._execute_step(next_step, state_manager)
                    state_manager.add_step_result(next_step.step_id, result)
                    
                    if result.get('success', True):
                        current_response = self._inject_step_result(current_response, next_step, result)
                        state_manager.update_response(current_response)
                    
                    step_execution_count += 1
                    
                    if self._should_continue_reasoning(next_step, result, state_manager):
                        logger.info("🧠 触发LLM继续推理...")
                        new_response = await self._continue_llm_reasoning(state_manager, current_response)
                        
                        if new_response and new_response != current_response:
                            new_steps = self._parse_sequential_steps(new_response)
                            logger.info(f"🆕 LLM生成了 {len(new_steps)} 个新步骤")
                            for step in new_steps:
                                if not any(s.step_id == step.step_id for s in state_manager.steps):
                                    state_manager.add_step(step)
                            current_response = new_response
                            state_manager.update_response(current_response)
                    
                except Exception as e:
                    logger.error(f"❌ 步骤执行失败: {next_step.step_id} - {e}")
                    error_result = {'success': False, 'error': str(e), 'step_id': next_step.step_id}
                    state_manager.add_step_result(next_step.step_id, error_result)
                    if not self._should_continue_after_error(e, state_manager):
                        logger.error("💥 错误过多，停止Sequential执行")
                        break
            
            if '<answer>' in current_response:
                state_manager.mark_completed()
            
            final_result = self._build_final_result(state_manager, current_response)
            logger.info(f"🎉 Sequential执行完成 - 执行了 {step_execution_count} 个步骤")
            return final_result
            
        except Exception as e:
            logger.error(f"💥 Sequential执行异常: {e}", exc_info=True)
            return {'success': False, 'error': str(e), 'execution_id': self.execution_id}
    
    def _parse_sequential_steps(self, xml_response: str) -> List[ExecutionStep]:
        steps = []
        xml_pattern = r'<(think|microsandbox|deepsearch|browser|search|answer|parallel)>(.*?)</\1>'
        for match in re.finditer(xml_pattern, xml_response, re.DOTALL):
            tag_name, content, position = match.group(1), match.group(2).strip(), match.span()
            step_id = f"{tag_name}_{len(steps)}_{uuid.uuid4().hex[:6]}"
            
            if tag_name == 'parallel':
                step = ExecutionStep(step_id=step_id, step_type='parallel', content=self._parse_parallel_block(content, position), position=position, needs_execution=True)
            else:
                step = ExecutionStep(step_id=step_id, step_type=tag_name, content=content, position=position, needs_execution=tag_name in ['microsandbox', 'deepsearch', 'browser', 'search'])
            
            steps.append(step)
            logger.debug(f"📝 解析步骤: {step_id} ({tag_name})")
        return steps

    def _parse_parallel_block(self, block_content: str, parent_position: Tuple[int, int]) -> List[ExecutionStep]:
        sub_steps = []
        tool_pattern = r'<(microsandbox|deepsearch|browser|search)>(.*?)</\1>'
        for match in re.finditer(tool_pattern, block_content, re.DOTALL):
            tag_name, content = match.group(1), match.group(2).strip()
            position = (parent_position[0] + match.start(), parent_position[0] + match.end())
            step_id = f"{tag_name}_{len(sub_steps)}_{uuid.uuid4().hex[:6]}"
            sub_steps.append(ExecutionStep(step_id=step_id, step_type=tag_name, content=content, position=position, needs_execution=True))
        return sub_steps

    async def _execute_step(self, step: ExecutionStep, state_manager: StreamingStateManager) -> Dict[str, Any]:
        if not self.tool_executor:
            return {'success': True, 'output': f"[模拟执行] {step.step_type}", 'step_id': step.step_id}

        result = {}
        try:
            start_time = datetime.now()
            
            if step.step_type == 'parallel':
                result = await self._execute_parallel_block(step, state_manager)
            else:
                result = await self._execute_single_tool(step, state_manager)

            result['execution_time'] = (datetime.now() - start_time).total_seconds()
            result['step_id'] = step.step_id
            
            if not result.get('success', True):
                await self._handle_execution_error(step, result, state_manager)

            logger.info(f"✅ 步骤执行完成: {step.step_id} - 耗时: {result.get('execution_time', 0):.2f}s")
            
        except Exception as e:
            logger.error(f"❌ 步骤执行异常: {step.step_id} - {e}", exc_info=True)
            result = {'success': False, 'error': str(e), 'step_id': step.step_id}
            await self._handle_execution_error(step, result, state_manager)
        
        if self.memory_manager and state_manager.context.session_id:
            try:
                await self.memory_manager.store_conversation_step(
                    task_id=state_manager.context.session_id.split('_', 1)[1],
                    session_id=state_manager.context.session_id,
                    user_input=f"Execute step: {step.step_type}",
                    agent_output=str(result.get('output', result.get('error', ''))),
                    thinking_summary=f"Executing step {step.step_id}",
                    tools_used=[step.step_type],
                    success=result.get('success', True),
                    error_message=result.get('error'),
                    metadata={'step_id': step.step_id, 'content': step.content}
                )
                logger.debug(f"💾 步骤 {step.step_id} 已存储到记忆")
            except Exception as mem_e:
                logger.warning(f"存储步骤 {step.step_id} 到记忆时失败: {mem_e}")

        return result

    async def _handle_execution_error(self, failed_step: ExecutionStep, error_result: Dict[str, Any], state_manager: StreamingStateManager):
        if not self.llm_client:
            logger.error("LLM客户端未配置，无法进行错误反思")
            return

        try:
            current_xml_with_error = self.result_injector.inject_result(state_manager.context.current_response, failed_step.position, error_result, failed_step.step_id)
            prompt = f"""An error occurred. Analyze the error and provide a corrected plan.
**Task**: {state_manager.context.task_description}
**History & Error**:
{current_xml_with_error}
**Guideline**: Analyze the error and respond with new `<think>` and tool call XML tags to continue.
"""
            logger.info("🧠 请求LLM对错误进行反思和纠正...")
            correction_response = await self.llm_client._call_api([{"role": "user", "content": prompt}])
            
            if correction_response:
                logger.info(f"🆕 LLM提供了纠正计划:\n{correction_response}")
                new_response_with_correction = current_xml_with_error + "\n" + correction_response
                state_manager.update_response(new_response_with_correction)
                new_steps = self._parse_sequential_steps(correction_response)
                if new_steps:
                    logger.info(f"➕ 将 {len(new_steps)} 个纠正步骤添加到执行队列")
                    for step in new_steps:
                        if not any(s.step_id == step.step_id for s in state_manager.steps):
                            state_manager.add_step(step)
            else:
                logger.warning("LLM未能提供纠正计划。")
        except Exception as e:
            logger.error(f"处理执行错误时发生异常: {e}", exc_info=True)

    async def _execute_single_tool(self, step: ExecutionStep, state_manager: StreamingStateManager) -> Dict[str, Any]:
        tool_id, original_content = step.step_type, step.content
        action, parameters = None, {}
        
        try:
            is_nested_call = re.match(r'<(\w+)>.*</\1>', original_content, re.DOTALL)

            if not original_content or not is_nested_call:
                action, parameters = await self._request_action_selection(tool_id, original_content, state_manager)
                if not action:
                    return {'success': False, 'error': f"未能为 {tool_id} 选择具体动作"}
                step.content = f"<{action}>{parameters.get('instruction', '')}</{action}>"
                logger.debug(f"二级选择后，更新步骤内容为: {step.content}")
            else:
                action_match = re.match(r'<(\w+)>(.*)</\1>', original_content, re.DOTALL)
                if not action_match: raise ValueError("无效的嵌套工具调用格式")
                action, parameters = action_match.group(1), {"instruction": action_match.group(2).strip()}

            logger.info(f"🔧 准备��行: tool_id='{tool_id}', action='{action}'")
            
            execution_result = await self.tool_executor.execute_tool(
                tool_id=tool_id,
                action=action,
                parameters=parameters
            )

            if not isinstance(execution_result, dict):
                logger.warning(f"工具 '{tool_id}' 返回了非字典类型: {type(execution_result)}. 将其视为错误。")
                return {'success': False, 'error': f"工具返回了无效的响应类型: {str(execution_result)}"}

            return execution_result

        except Exception as e:
            logger.error(f"执行工具 '{tool_id}' 时发生异常: {e}", exc_info=True)
            return {'success': False, 'error': f"执行工具时发生内部异常: {e}"}

    async def _request_action_selection(self, tool_id: str, instruction: str, state_manager: StreamingStateManager) -> Tuple[Optional[str], Dict[str, Any]]:
        if not self.llm_client:
            logger.error("LLM客户端未配置，无法进行二级动作选择")
            return None, {}

        logger.debug(f"为服务 '{tool_id}' 请求二级动作选择，原始指令: '{instruction}'")
        try:
            tool_schema = await self.tool_executor.get_tool_schema(tool_id)
            if not tool_schema or 'actions' not in tool_schema:
                logger.error(f"未能获取 {tool_id} 的工具schema或actions")
                return None, {}
            
            actions_description = "\n".join([f"- <{action['name']}>: {action.get('description', 'No description')}" for action in tool_schema['actions']])
            logger.debug(f"从 Schema 获取到 '{tool_id}' 的可用动作:\n{actions_description}")

            prompt = f"""You have selected the '{tool_id}' service. Your instruction is: '{instruction}'.
Available actions:
{actions_description}
Choose the most appropriate action and respond with a single XML tag. Example: <chosen_action>parameters</chosen_action>"""
            logger.debug(f"发送给 LLM 的二级选择 Prompt:\n{prompt}")

            response = await self.llm_client._call_api([{"role": "user", "content": prompt}])
            logger.debug(f"LLM 返回的二级选择结果: {response.strip()}")

            action_match = re.match(r'<(\w+)>(.*)</\1>', response.strip(), re.DOTALL)
            if not action_match:
                logger.error(f"二级动作选择的LLM响应格式不正确: {response}")
                return None, {}
            
            action, params_str = action_match.group(1), action_match.group(2).strip()
            logger.info(f"✅ 二级动作选择成功: {action}")
            return action, {"instruction": params_str}
        except Exception as e:
            logger.error(f"请求二级动作选择时出错: {e}", exc_info=True)
            return None, {}

    async def _execute_parallel_block(self, parallel_step: ExecutionStep, state_manager: StreamingStateManager) -> Dict[str, Any]:
        sub_steps = parallel_step.content
        if not isinstance(sub_steps, list): return {'success': False, 'error': '无效的并行步骤格式'}
        logger.info(f"⚡️ 并发执行 {len(sub_steps)} 个子步骤...")
        tasks = [self._execute_single_tool(sub_step, state_manager) for sub_step in sub_steps]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        final_results, all_success = [], True
        for i, res in enumerate(results):
            sub_step = sub_steps[i]
            if isinstance(res, Exception):
                all_success = False
                final_results.append({'success': False, 'error': str(res), 'step_id': sub_step.step_id, 'position': sub_step.position})
            else:
                if not res.get('success', True): all_success = False
                final_results.append({**res, 'position': sub_step.position})
        return {'success': all_success, 'results': final_results, 'step_id': parallel_step.step_id}
    
    def _inject_step_result(self, current_response: str, step: ExecutionStep, result: Dict[str, Any]) -> str:
        try:
            if step.step_type == 'parallel' and 'results' in result:
                injection_data = [{'tool_call_pos': sub_res['position'], 'result': sub_res, 'step_id': sub_res['step_id']} for sub_res in result['results']]
                return self.result_injector.inject_multiple_results(current_response, injection_data)
            else:
                return self.result_injector.inject_result(current_response, step.position, result, step.step_id)
        except Exception as e:
            logger.error(f"❌ 结果注入失败: {step.step_id} - {e}")
            return current_response
    
    def _should_continue_reasoning(self, step: ExecutionStep, result: Dict[str, Any], state_manager: StreamingStateManager) -> bool:
        # 只有在成功执行且任务未完成时才继续
        if result.get('success', True) and not state_manager.is_completed:
             # 如果响应中没有answer标签，则需要继续
            return '<answer>' not in state_manager.context.current_response
        return False
    
    async def _continue_llm_reasoning(self, state_manager: StreamingStateManager, current_response: str) -> Optional[str]:
        if not self.llm_client: return None
        try:
            prompt = self._build_continue_prompt(state_manager, current_response)
            return await self.llm_client._call_api([{"role": "user", "content": prompt}])
        except Exception as e:
            logger.error(f"❌ LLM继续推理失败: {e}")
            return None
    
    def _build_continue_prompt(self, state_manager: StreamingStateManager, current_response: str) -> str:
        stats = state_manager.get_execution_stats()
        return f"""Continue your reasoning based on the tool execution results:
Current progress:
{current_response}
Execution status:
- Completed steps: {stats['completed_steps']}
- Failed steps: {stats['failed_steps']}
Please continue with your analysis and next steps in XML format.
Continue:"""
    
    def _should_continue_after_error(self, error: Exception, state_manager: StreamingStateManager) -> bool:
        stats = state_manager.get_execution_stats()
        return not (stats['error_count'] >= 3 or isinstance(error, asyncio.TimeoutError))
    
    def _build_final_result(self, state_manager: StreamingStateManager, final_response: str) -> Dict[str, Any]:
        stats = state_manager.get_execution_stats()
        answer_match = re.search(r'<answer>(.*?)</answer>', final_response, re.DOTALL)
        final_answer = answer_match.group(1).strip() if answer_match else ""
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
            'steps_executed': [{'step_id': s.step_id, 'step_type': s.step_type, 'content': s.content if isinstance(s.content, str) else f"Parallel block with {len(s.content)} steps", 'status': s.status, 'execution_time': s.execution_time} for s in state_manager.steps if s.needs_execution],
            'state_summary': state_manager.get_state_summary()
        }
