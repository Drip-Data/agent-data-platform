# 新增 ReasoningRuntime 类
import asyncio
import json
import logging
import os
import time
import uuid
# import json # json is already imported at line 3
from typing import Dict, Any, Optional, List
from core.interfaces import RuntimeInterface, TaskSpec, TrajectoryResult, ExecutionStep, ErrorType, ActionType
from core.llm_client import LLMClient
from core.metrics import EnhancedMetrics
from core.browser_state_manager import BrowserStateManager
from .tools import get_python_executor_tool, deep_research_tool # Import deep_research_tool

logger = logging.getLogger(__name__)
metrics = EnhancedMetrics(port=8003)

class ReasoningRuntime(RuntimeInterface):
    """推理运行时服务实现"""
    
    def __init__(self):
        self._runtime_id = f"reasoning-{uuid.uuid4()}"
        self.config = {
            'vllm_url': os.getenv('VLLM_URL', 'http://vllm:8000'),
            'gemini_api_key': os.getenv('GEMINI_API_KEY', ''),
            'gemini_api_url': os.getenv('GEMINI_API_URL', ''),
            'provider': 'gemini',  # 显式指定使用Gemini API
            # 是否同时保存单独的轨迹文件
            'save_individual_trajectories': os.getenv("SAVE_INDIVIDUAL_TRAJECTORIES", "").lower() in ("1", "true", "yes")
        }
        self.client = LLMClient(self.config)
        self.redis_url = os.getenv('REDIS_URL', 'redis://redis:6379')
        self.metrics = metrics

    @property
    def runtime_id(self) -> str:
        return self._runtime_id

    @property
    def capabilities(self) -> list:
        return ['deep_research', 'python_executor'] # Updated capabilities

    async def health_check(self) -> bool:
        # 简单检查 LLM 服务可用性
        try:
            await self.client.generate_reasoning("health check", [], [])
            return True
        except:
            return False

    async def execute(self, task: TaskSpec) -> TrajectoryResult:
        """执行推理任务"""
        start_time = time.time()
        trajectory_id = str(uuid.uuid4())
        steps: List[ExecutionStep] = []
        current_outputs: List[str] = []
        success = False
        # error_type and error_message for the overall trajectory, will be set if task fails fundamentally
        # Step-specific errors are in ExecutionStep
        final_trajectory_error_type: Optional[ErrorType] = None
        final_trajectory_error_message: Optional[str] = None
        
        # browser_state = BrowserStateManager() # No longer needed directly here if browser tool is removed

        for step_id in range(1, task.max_steps + 1):
            # current_browser_context_for_llm = browser_state.get_context_for_llm() # Not needed if browser tool removed

            # 生成推理决策
            # Assuming ExecutionStep has a to_dict() method or is a dataclass
            # For dataclasses, [s.__dict__ for s in steps] is fine.
            # If not, ensure proper serialization.
            serializable_steps = [s.to_dict() if hasattr(s, 'to_dict') else s.__dict__ for s in steps]

            decision = await self.client.generate_reasoning(
                task_description=task.description,
                available_tools=self.capabilities,
                previous_steps=serializable_steps
                # browser_context=current_browser_context_for_llm # Removed browser context
            )
            thinking = decision.get('thinking', f"Step {step_id}: Analyzing task and deciding next action")
            action = decision.get('action')
            tool_name = decision.get('tool')
            params = decision.get('parameters', {})
            confidence = decision.get('confidence', 0.0)

            # 执行工具调用
            max_retries = 1  # Max 1 retry (total 2 attempts)
            retry_delay_seconds = 3
            action_type = ActionType.TOOL_CALL # Default, will be overridden by specific actions

            for attempt in range(max_retries + 1):
                tool_start = time.time()
                observation = ''
                tool_success = False
                # Reset err_type and err_msg for each attempt to ensure they reflect the current attempt's outcome
                current_attempt_err_type = None
                current_attempt_err_msg = None

                execution_code = json.dumps({
                    'action': action,
                    'tool': tool_name,
                    'parameters': params
                }, ensure_ascii=False)

                if action == 'deep_research' and tool_name == 'deep_research':
                    query = params.get('query', '')
                    # Config for deep research can be passed via params or have defaults
                    research_config = params.get('config', {})
                    logger.debug(f"Attempt {attempt + 1}: Deep research execute - Query: {query}")
                    # Assuming deep_research_tool is a singleton or obtained similarly to other tools
                    res = await deep_research_tool.execute(query, research_config)
                    # The 'res' from deep_research_tool is expected to be a dict.
                    # We need to decide how to determine 'success' from this dict.
                    # For now, let's assume if 'final_answer' is present, it's a success.
                    tool_success = res.get('success', False) # 使用deep_research_tool返回的success状态
                    # 确保结果是JSON可序列化的，deep_research_tool._process_result已处理
                    observation = json.dumps(res)
                    action_type = ActionType.TOOL_CALL
                elif action == 'python_execute' and tool_name == 'python_executor':
                    code = params.get('code', '')
                    logger.debug(f"Attempt {attempt + 1}: Python execute")
                    python_executor_tool = get_python_executor_tool()
                    res = await python_executor_tool.execute_code(code, task.timeout)
                    tool_success = res.get('success', False)
                    observation = json.dumps(res)
                    action_type = ActionType.CODE_EXECUTION
                    if tool_success and 'stdout' in res: # only append if successful
                        current_outputs.append(res['stdout'])
                elif action == 'python_analyze' and tool_name == 'python_executor':
                    # ... (similar logging for other actions if needed)
                    data = params.get('data')
                    op = params.get('operation', 'describe')
                    python_executor_tool = get_python_executor_tool()
                    res = await python_executor_tool.analyze_data(data, op)
                    tool_success = res.get('success', False)
                    observation = json.dumps(res)
                    action_type = ActionType.TOOL_CALL
                elif action == 'python_visualize' and tool_name == 'python_executor':
                    data = params.get('data')
                    pt = params.get('plot_type', 'line')
                    title = params.get('title', '')
                    python_executor_tool = get_python_executor_tool()
                    res = await python_executor_tool.create_visualization(data, pt, title)
                    tool_success = res.get('success', False)
                    observation = json.dumps(res)
                    action_type = ActionType.TOOL_CALL
                elif action == 'complete_task':
                    summary = await self.client.generate_task_summary(
                        task.description, [s.__dict__ for s in steps], current_outputs
                    )
                    success = True # Overall task success
                    observation = summary
                    tool_success = True # This "tool call" is considered successful
                    action_type = ActionType.TOOL_CALL
                    # No need to parse error for complete_task if it's considered a success path
                    current_attempt_err_type = None
                    current_attempt_err_msg = None
                    # Append step for complete_task and break from step_id loop
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
                    # 结构化日志：StepLog
                    logger.debug(json.dumps({
                        "step_id": step_id,
                        "action_type": action_type.name if hasattr(action_type, 'name') else action_type,
                        "tool_input": params,
                        "tool_output": observation,
                        "timestamp": time.time(),
                        "duration": duration,
                        "thinking": thinking
                    }, ensure_ascii=False))
                    # Break from the outer for step_id loop
                    # This break should be outside the retry loop, after appending the step.
                    # The current logic will break the retry loop first, then the outer loop.
                    # This is correct for complete_task.
                    break # Break from retry loop
                else:
                    tool_success = False
                    current_attempt_err_type = ErrorType.SYSTEM_ERROR
                    current_attempt_err_msg = f"Unsupported action/tool: {action}/{tool_name}"
                    observation = current_attempt_err_msg
                    action_type = ActionType.TOOL_CALL

                # Populate error details from the current attempt if it failed
                if not tool_success:
                    try:
                        tool_response_data = json.loads(observation)
                        if isinstance(tool_response_data, dict):
                            # 安全处理error_type，确保是ErrorType枚举
                            error_type_raw = tool_response_data.get("error_type", current_attempt_err_type)
                            if error_type_raw:
                                if isinstance(error_type_raw, str):
                                    # 尝试转换字符串为ErrorType枚举
                                    try:
                                        current_attempt_err_type = ErrorType(error_type_raw)
                                    except ValueError:
                                        # 如果无法转换，使用默认的TOOL_ERROR
                                        current_attempt_err_type = ErrorType.TOOL_ERROR
                                elif isinstance(error_type_raw, ErrorType):
                                    current_attempt_err_type = error_type_raw
                                else:
                                    current_attempt_err_type = ErrorType.TOOL_ERROR
                            else:
                                current_attempt_err_type = ErrorType.TOOL_ERROR
                            
                            current_attempt_err_msg = tool_response_data.get("error",
                                                                tool_response_data.get("message",
                                                                                        str(tool_response_data)))
                    except json.JSONDecodeError:
                        current_attempt_err_msg = observation if isinstance(observation, str) else "Unknown tool error"
                        if not current_attempt_err_type: 
                            current_attempt_err_type = ErrorType.TOOL_ERROR
                    except Exception as e_parse:
                        logger.error(f"Error parsing tool's error response on attempt {attempt + 1}: {e_parse}")
                        current_attempt_err_msg = f"Could not parse tool error: {observation[:200]}"
                        if not current_attempt_err_type: 
                            current_attempt_err_type = ErrorType.TOOL_ERROR
                
                if tool_success:
                    break # Successful attempt, exit retry loop
                else:
                    logger.warning(
                        f"Step {step_id}, Action {action}, Attempt {attempt + 1}/{max_retries + 1} failed. "
                        f"ErrorType: {current_attempt_err_type}, ErrorMsg: {current_attempt_err_msg}"
                    )
                    is_retryable = False
                    # 安全的错误类型检查，支持ErrorType枚举和字符串
                    is_navigation_error = False
                    if isinstance(current_attempt_err_type, ErrorType):
                        is_navigation_error = (current_attempt_err_type == ErrorType.NETWORK_ERROR or 
                                             current_attempt_err_type.value == "NavigationError")
                    elif isinstance(current_attempt_err_type, str):
                        is_navigation_error = current_attempt_err_type == "NavigationError"
                    
                    if is_navigation_error and current_attempt_err_msg and "timeout" in current_attempt_err_msg.lower():
                        is_retryable = True

                    if is_retryable and attempt < max_retries:
                        logger.info(f"Retrying action {action} after {retry_delay_seconds}s delay...")
                        await asyncio.sleep(retry_delay_seconds)
                    else:
                        # Not retryable or max retries reached, break from retry loop
                        # The current_attempt_err_type and _msg will be used for the ExecutionStep
                        break
            
            # After retry loop, current_attempt_err_type and _msg hold the final error state for this step
            # If complete_task was action, it breaks out of step_id loop, so this won't be an issue.
            if action == 'complete_task' and success: # 'success' is overall task success
                 break # Break from the main step_id loop

            duration = time.time() - tool_start # Recalculate duration for the whole step including retries

            steps.append(ExecutionStep(
                step_id=step_id,
                action_type=action_type,
                action_params=params,
                observation=observation, # Observation from the last attempt
                success=tool_success,    # Success status from the last attempt
                error_type=current_attempt_err_type,
                error_message=current_attempt_err_msg,
                thinking=thinking,
                execution_code=execution_code,
                timestamp=time.time(),
                duration=duration
            ))
            # 结构化日志：StepLog
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
        
        # 生成更好的final_result
        if success and steps:
            if steps[-1].action_type == ActionType.TOOL_CALL and "complete_task" in steps[-1].execution_code:
                final_result = steps[-1].observation
            else:
                final_result = f"Task completed successfully after {len(steps)} steps."
        elif steps:
            final_result = f"Task failed after {len(steps)} steps. Last error: {steps[-1].error_message or 'Unknown error'}"
        else:
            final_result = "Task did not execute any steps."

        trajectory = TrajectoryResult(
            task_name=task.task_id,  # 保持原始task_id作为task_name
            task_id=trajectory_id,   # 使用新的UUID作为轨迹ID
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
                'original_task_id': task.task_id
            }
        )
          # 保存轨迹到集合文件
        logger.info(f"Attempting to save trajectory. Overall task success status: {success}")
        out_dir = os.getenv('OUTPUT_DIR', '/app/output/trajectories')
        os.makedirs(out_dir, exist_ok=True)
        logger.info(f"Trajectory output directory: {out_dir}")
        
        # 集合文件路径
        collection_file = os.path.join(out_dir, "trajectories_collection.json")
        logger.info(f"Trajectory collection file path: {collection_file}")
        
        # 读取现有集合或创建新集合
        trajectories_list = [] # Renamed to avoid conflict with the trajectory object
        if os.path.exists(collection_file):
            try:
                with open(collection_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content.strip(): # Check if file is not empty
                        trajectories_list = json.loads(content)
                        if not isinstance(trajectories_list, list):
                            logger.warning(f"Trajectories collection file {collection_file} did not contain a list. Reinitializing.")
                            trajectories_list = []
                    else: # File is empty
                        trajectories_list = []
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON from trajectories collection {collection_file}: {e}. Reinitializing trajectories list.")
                trajectories_list = []
            except Exception as e:
                logger.error(f"Error reading trajectories collection {collection_file}: {e}. Reinitializing trajectories list.")
                trajectories_list = []
        
        try:
            trajectory_dict = trajectory.to_dict()
            logger.debug(f"Trajectory data to be appended (type: {type(trajectory_dict)}):")
            # Log a summary of the trajectory_dict to avoid excessively long logs
            # For example, log keys and types of complex objects
            summary_trajectory_dict = {k: type(v).__name__ for k, v in trajectory_dict.items()}
            logger.debug(f"Summary of trajectory_dict: {json.dumps(summary_trajectory_dict, indent=2, ensure_ascii=False)}")
            # If you need to see full content for debugging, uncomment the next line carefully:
            # logger.debug(f"Full trajectory_dict: {json.dumps(trajectory_dict, indent=2, ensure_ascii=False)}")

        except Exception as e:
            logger.error(f"Error converting trajectory to dict: {e}", exc_info=True)
            # If conversion fails, we cannot proceed to save this trajectory
            return trajectory # Return original trajectory, though saving failed

        logger.debug(f"Appending new trajectory; total before append: {len(trajectories_list)} to {collection_file}")
        trajectories_list.append(trajectory_dict)
        
        # 将更新后的集合写入文件
        logger.debug(f"Writing {len(trajectories_list)} trajectories to {collection_file}")
        try:
            with open(collection_file, 'w', encoding='utf-8') as f:
                json.dump(trajectories_list, f, indent=2, ensure_ascii=False)
            logging.info(f"Trajectory successfully added and collection saved to: {collection_file}")
        except Exception as e:
            logger.error(f"Failed to write trajectories to {collection_file}: {e}", exc_info=True)
            # Optionally, re-raise or handle this critical error
            # For now, we log and the trajectory object is still returned
            
        # 同时也保存单独的文件（可选）
        if self.config.get("save_individual_trajectories", False):
            individual_file = os.path.join(out_dir, f"{trajectory.task_id}.json")
            with open(individual_file, 'w', encoding='utf-8') as f:
                f.write(trajectory.json())
            logging.info(f"Individual trajectory saved: {individual_file}")

        return trajectory

    async def cleanup(self):
        """清理资源"""
        # browser_tool = get_browser_tool() # Browser tool removed
        # await browser_tool.cleanup()
        python_executor_tool = get_python_executor_tool()
        python_executor_tool.cleanup()
        if hasattr(self.client, 'close'):
            await self.client.close()

# 运行服务
if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    runtime = ReasoningRuntime()
    from core.task_manager import start_runtime_service
    # 直接调用启动服务
    start_runtime_service(runtime)
