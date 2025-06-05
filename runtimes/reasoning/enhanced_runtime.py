"""
增强推理运行时 - 使用新的工具注册系统
支持动态工具管理和LLM自主工具选择
"""

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Dict, Any, Optional, List
from core.interfaces import RuntimeInterface, TaskSpec, TrajectoryResult, ExecutionStep, ErrorType, ActionType
from core.llm_client import LLMClient
from core.metrics import EnhancedMetrics
from core.toolscore.unified_tool_library import UnifiedToolLibrary
from core.toolscore.interfaces import ToolType, FunctionToolSpec, ToolCapability
from core.toolscore.mcp_client import MCPToolClient # 导入MCPClient

logger = logging.getLogger(__name__)

class EnhancedReasoningRuntime(RuntimeInterface):
    """增强推理运行时 - 支持动态工具管理"""
    
    def __init__(self):
        self._runtime_id = f"enhanced-reasoning-{uuid.uuid4()}"
        self.config = {
            'vllm_url': os.getenv('VLLM_URL', 'http://vllm:8000'),
            'gemini_api_key': os.getenv('GEMINI_API_KEY', ''),
            'gemini_api_url': os.getenv('GEMINI_API_URL', ''),
            'provider': 'gemini',
            'save_individual_trajectories': os.getenv("SAVE_INDIVIDUAL_TRAJECTORIES", "").lower() in ("1", "true", "yes")
        }
        self.client = LLMClient(self.config)
        self.redis_url = os.getenv('REDIS_URL', 'redis://redis:6379')
        self.metrics = EnhancedMetrics(port=8003)
        
        toolscore_url = os.getenv('TOOLSCORE_URL', 'ws://toolscore:8080/websocket') # 获取TOOLSCORE_URL
        self.mcp_client = MCPToolClient(toolscore_url) # 实例化MCPClient
        self.tool_library = UnifiedToolLibrary(mcp_client=self.mcp_client) # 将MCPClient传递给UnifiedToolLibrary
        
    async def initialize(self):
        """初始化运行时和工具库"""
        await self.tool_library.initialize()
        
    @property
    def runtime_id(self) -> str:
        return self._runtime_id

    @property
    async def capabilities(self) -> list: # 标记为async
        """动态获取可用工具的ID列表"""
        # 返回工具ID列表，LLMClient可能需要这个格式
        return [tool.tool_id for tool in await self.tool_library.get_all_tools()] # 添加await

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 传递工具ID列表给LLMClient
            await self.client.generate_reasoning("health check", await self.capabilities, [])
            return True
        except Exception as e: # 捕获具体异常
            logger.error(f"Health check failed: {e}")
            return False

    async def execute(self, task: TaskSpec) -> TrajectoryResult:
        """执行推理任务 - 支持动态工具调用"""
        start_time = time.time()
        trajectory_id = str(uuid.uuid4())
        steps: List[ExecutionStep] = []
        current_outputs: List[str] = []
        success = False
        final_trajectory_error_type: Optional[ErrorType] = None
        final_trajectory_error_message: Optional[str] = None
        
        # 获取所有可用工具的ToolSpec列表
        all_available_tool_specs = await self.tool_library.get_all_tools()
        
        # 为LLM生成所有工具的增强描述
        all_tools_description_for_llm = await self.tool_library.get_all_tools_description_for_agent()
        
        logger.info(f"Task: {task.description}")
        logger.info(f"All available tools (for LLM): {all_tools_description_for_llm}")
        
        # LLM决策时，将所有工具的描述传递给它，让它自主选择
        # available_tools 参数现在传递的是ToolSpec列表，而不是简单的名称列表
        available_tools_for_llm_client = [tool.tool_id for tool in all_available_tool_specs]

        for step_id in range(1, task.max_steps + 1):
            # 浏览器上下文现在由浏览器工具本身管理，这里不再需要
            current_browser_context_for_llm = None

            # 生成推理决策 - 使用丰富的工具描述
            serializable_steps = [s.to_dict() if hasattr(s, 'to_dict') else s.__dict__ for s in steps]
            
            decision = await self.client.generate_enhanced_reasoning(
                task_description=task.description,
                available_tools=available_tools_for_llm_client, # 传递工具ID列表
                tool_descriptions=all_tools_description_for_llm, # 传递详细描述
                previous_steps=serializable_steps,
                browser_context=current_browser_context_for_llm
            )
            
            thinking = decision.get('thinking', f"Step {step_id}: Analyzing task and deciding next action")
            action = decision.get('action')
            tool_id = decision.get('tool') # 从tool_name改为tool_id
            params = decision.get('parameters', {})
            confidence = decision.get('confidence', 0.0)

            # 使用UnifiedToolLibrary执行工具调用
            max_retries = 1
            retry_delay_seconds = 3
            action_type = ActionType.TOOL_CALL

            for attempt in range(max_retries + 1):
                tool_start = time.time()
                observation = ''
                tool_success = False
                current_attempt_err_type: Optional[ErrorType] = None # 明确类型
                current_attempt_err_msg: Optional[str] = None # 明确类型

                execution_code = json.dumps({
                    'action': action,
                    'tool_id': tool_id, # 从tool改为tool_id
                    'parameters': params
                }, ensure_ascii=False)

                # 特殊处理complete_task
                if action == 'complete_task':
                    summary = await self.client.generate_task_summary(
                        task.description, [s.__dict__ for s in steps], current_outputs
                    )
                    success = True
                    observation = summary
                    tool_success = True
                    action_type = ActionType.TOOL_CALL
                    
                    duration = time.time() - tool_start
                    steps.append(ExecutionStep(
                        step_id=step_id,
                        action_type=action_type,
                        action_params=params,
                        observation=observation,
                        success=True,
                        thinking=thinking,
                        execution_code=execution_code,
                        error_type=None,
                        error_message=None,
                        timestamp=time.time(),
                        duration=duration
                    ))
                    break
                
                # 使用UnifiedToolLibrary执行工具
                if tool_id and action: # 确保tool_id和action存在
                    logger.debug(f"Attempt {attempt + 1}: Executing action '{action}' with tool_id '{tool_id}'")
                    
                    # 检查并清理browser_navigate工具的URL参数
                    cleaned_params = params.copy()
                    if tool_id == "browser_navigator_server" and action == "browser_navigate":
                        url = cleaned_params.get("url", "")
                        if url.startswith("url: "):
                            cleaned_params["url"] = url[len("url: "):].strip()
                            logger.info(f"Cleaned URL for browser_navigate: {url} -> {cleaned_params['url']}")
                    
                    # 调用UnifiedToolLibrary的execute_tool方法
                    result = await self.tool_library.execute_tool(tool_id, action, cleaned_params)
                    tool_success = result.success # UnifiedToolLibrary返回的是ExecutionResult对象
                    observation = json.dumps(result.to_dict()) # 将ExecutionResult转换为字典再序列化
                    
                    # 现在所有工具都是MCP Server，统一设置为TOOL_CALL
                    action_type = ActionType.TOOL_CALL
                    
                    # 浏览器状态和Python执行输出现在由各自的MCP Server管理，并通过ExecutionResult返回
                    # ReasoningRuntime 不再直接处理这些状态
                else:
                    tool_success = False
                    current_attempt_err_type = ErrorType.SYSTEM_ERROR
                    if not tool_id:
                        current_attempt_err_msg = f"LLM did not specify a tool_id. Action attempted: '{action}'."
                    elif not action:
                        current_attempt_err_msg = f"LLM did not specify an action for tool '{tool_id}'."
                    elif action == "error":
                        current_attempt_err_msg = f"LLM explicitly returned an 'error' action for tool '{tool_id}'."
                    else:
                        current_attempt_err_msg = f"LLM attempted to call tool '{tool_id}' with action '{action}', but it is currently unsupported or invalid."
                    observation = current_attempt_err_msg
                    action_type = ActionType.TOOL_CALL

                # 错误处理
                if not tool_success:
                    # 直接从ExecutionResult获取错误信息
                    # 确保current_attempt_err_type是ErrorType枚举或None
                    if isinstance(result.error_type, str):
                        try:
                            current_attempt_err_type = ErrorType(result.error_type)
                        except ValueError:
                            current_attempt_err_type = ErrorType.TOOL_ERROR
                    else:
                        current_attempt_err_type = result.error_type if result.error_type else ErrorType.TOOL_ERROR
                    
                    current_attempt_err_msg = result.error_message if result.error_message else "Unknown tool error"
                
                if tool_success:
                    break
                else:
                    logger.warning(
                        f"Step {step_id}, Action {action}, Attempt {attempt + 1}/{max_retries + 1} failed. "
                        f"ErrorType: {current_attempt_err_type}, ErrorMsg: {current_attempt_err_msg}"
                    )
                    
                    # 重试逻辑
                    is_retryable = False
                    # 确保current_attempt_err_type是ErrorType枚举或字符串
                    if isinstance(current_attempt_err_type, ErrorType):
                        is_navigation_error = (current_attempt_err_type == ErrorType.NETWORK_ERROR or
                                             current_attempt_err_type.value == "NavigationError")
                    elif isinstance(current_attempt_err_type, str):
                        is_navigation_error = current_attempt_err_type == "NavigationError"
                    else:
                        is_navigation_error = False
                    
                    if is_navigation_error and current_attempt_err_msg and "timeout" in current_attempt_err_msg.lower():
                        is_retryable = True

                    if is_retryable and attempt < max_retries:
                        logger.info(f"Retrying action {action} after {retry_delay_seconds}s delay...")
                        await asyncio.sleep(retry_delay_seconds)
                    else:
                        break
            
            # 完成任务检查
            # 解析execution_code来检查action
            exec_code_dict = {}
            if execution_code is not None: # 检查execution_code是否为None
                try:
                    exec_code_dict = json.loads(execution_code)
                except json.JSONDecodeError:
                    pass # 如果不是有效的JSON，则跳过此检查
            
            if exec_code_dict.get('action') == 'complete_task' and success:
                break

            duration = time.time() - tool_start

            steps.append(ExecutionStep(
                step_id=step_id,
                action_type=action_type,
                action_params=params,
                observation=observation,
                success=tool_success,
                error_type=current_attempt_err_type,
                error_message=current_attempt_err_msg,
                thinking=thinking,
                execution_code=execution_code,
                timestamp=time.time(),
                duration=duration
            ))

            # 结构化日志
            logger.debug(json.dumps({
                "step_id": step_id,
                "action_type": action_type.name if hasattr(action_type, 'name') else action_type,
                "tool_input": params,
                "tool_output": observation,
                "timestamp": time.time(),
                "duration": duration,
                "thinking": thinking
            }, ensure_ascii=False))

            # 检查是否完成
            completion = await self.client.check_task_completion(
                task.description,
                [s.__dict__ for s in steps],
                current_outputs
            )
            if completion.get('completed'):
                success = True
                break

        total_duration = time.time() - start_time
        
        # 生成最终结果
        if success and steps:
            # 再次解析execution_code来检查action
            last_step_exec_code = {}
            if steps[-1].execution_code is not None: # 检查execution_code是否为None
                try:
                    last_step_exec_code = json.loads(steps[-1].execution_code)
                except json.JSONDecodeError:
                    pass

            if last_step_exec_code.get('action') == 'complete_task':
                final_result = steps[-1].observation
            else:
                final_result = f"Task completed successfully after {len(steps)} steps."
        elif steps:
            final_result = f"Task failed after {len(steps)} steps. Last error: {steps[-1].error_message or 'Unknown error'}"
        else:
            final_result = "Task did not execute any steps."

        trajectory = TrajectoryResult(
            task_name=task.task_id,
            task_id=trajectory_id,
            task_description=task.description,
            runtime_id=self.runtime_id,
            success=success,
            steps=steps,
            final_result=final_result,
            error_type=final_trajectory_error_type if not success and steps else None,
            error_message=final_trajectory_error_message if not success and steps else None,
            total_duration=total_duration,
            metadata={
                'confidence': confidence,
                'original_task_id': task.task_id,
                'available_tools': available_tools_for_llm_client, # 更新为传递给LLM的工具ID列表
                'tool_library_stats': await self.tool_library.get_library_stats() # 获取工具库统计信息
            }
        )
        
        # 保存轨迹
        await self._save_trajectory(trajectory)
        return trajectory
    
    async def _save_trajectory(self, trajectory: TrajectoryResult):
        """保存轨迹到文件"""
        out_dir = os.getenv('OUTPUT_DIR', '/app/output/trajectories')
        os.makedirs(out_dir, exist_ok=True)
        
        collection_file = os.path.join(out_dir, "trajectories_collection.json")
        
        trajectories = []
        if os.path.exists(collection_file):
            try:
                with open(collection_file, 'r', encoding='utf-8') as f:
                    trajectories = json.load(f)
                    if not isinstance(trajectories, list):
                        trajectories = []
            except (json.JSONDecodeError, Exception) as e:
                logging.error(f"Error reading trajectories collection: {e}")
                trajectories = []
        
        trajectories.append(trajectory.__dict__)
        
        with open(collection_file, 'w', encoding='utf-8') as f:
            json.dump(trajectories, f, ensure_ascii=False, indent=2, default=str)
        
        logger.info(f"Saved trajectory {trajectory.task_id} to collection")

    async def cleanup(self):
        """清理资源"""
        logger.info("Cleaning up EnhancedReasoningRuntime resources")
        
        # 清理UnifiedToolLibrary管理的资源
        await self.tool_library.cleanup()