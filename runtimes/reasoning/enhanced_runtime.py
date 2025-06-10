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
from core.toolscore.dynamic_mcp_manager import DynamicMCPManager
from core.toolscore.tool_gap_detector import ToolGapDetector
from core.toolscore.mcp_search_tool import MCPSearchTool

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
        
        # 初始化动态MCP管理器和工具缺口检测器
        self.dynamic_mcp_manager = None  # 延迟初始化，需要在tool_library初始化后
        self.tool_gap_detector = ToolGapDetector(self.client)  # 传递LLM客户端
        self.mcp_search_tool = None  # MCP搜索工具，延迟初始化
        
    async def initialize(self):
        """初始化运行时和工具库"""
        await self.tool_library.initialize()
        
        # 初始化动态MCP管理器
        self.dynamic_mcp_manager = DynamicMCPManager(self.tool_library)
        await self.dynamic_mcp_manager.initialize()  # 确保正确初始化
        
        # 初始化MCP搜索工具 - 修正参数顺序
        self.mcp_search_tool = MCPSearchTool(self.tool_gap_detector, self.dynamic_mcp_manager)
        
        # 注册MCP搜索工具到工具库
        await self._register_mcp_search_tool()
        
        logger.info("Enhanced Reasoning Runtime initialized with dynamic MCP capabilities")
        
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
        
        # 统一的上下文，用于存储跨步骤的状态
        current_context: Dict[str, Any] = {
            "browser_state": None  # 存储浏览器的当前状态 (URL, Title, etc.)
        }
        
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
            # current_browser_context_for_llm = None # 注释掉此行

            # 生成推理决策 - 使用丰富的工具描述
            serializable_steps = [s.to_dict() if hasattr(s, 'to_dict') else s.__dict__ for s in steps]
            
            decision = await self.client.generate_enhanced_reasoning(
                task_description=task.description,
                available_tools=available_tools_for_llm_client, # 传递工具ID列表
                tool_descriptions=all_tools_description_for_llm, # 传递详细描述
                previous_steps=serializable_steps,
                # browser_context=current_browser_context_for_llm # 旧参数
                execution_context=current_context # 传递统一的上下文
            )
            
            thinking = decision.get('thinking', f"Step {step_id}: Analyzing task and deciding next action")
            action = decision.get('action')
            tool_id = decision.get('tool_id') or decision.get('tool')  # 优先使用tool_id，回退到tool
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
                result = None  # 初始化result变量

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
                    observation = summary # 这里的observation已经是简洁的
                    tool_success = True
                    action_type = ActionType.TOOL_CALL
                    
                    duration = time.time() - tool_start
                    steps.append(ExecutionStep(
                        step_id=step_id,
                        action_type=action_type,
                        action_params=params,
                        observation=observation, # 使用简洁的observation
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
                    
                    # 映射能力名称到MCP服务器ID
                    capability_to_server_map = {
                        # 旧的能力名称映射
                        'python_execute': 'python-executor-mcp-server',
                        'python_analyze': 'python-executor-mcp-server', 
                        'python_visualize': 'python-executor-mcp-server',
                        'python_install_package': 'python-executor-mcp-server',
                        'browser_navigate': 'browser-navigator-mcp-server',
                        'browser_click': 'browser-navigator-mcp-server',
                        'browser_type': 'browser-navigator-mcp-server',
                        'browser_scroll': 'browser-navigator-mcp-server',
                        'browser_screenshot': 'browser-navigator-mcp-server',
                        'browser_get_text': 'browser-navigator-mcp-server',
                        # 添加可能的工具名称变体
                        'python_executor': 'python-executor-mcp-server',
                        'python_executor_server': 'python-executor-mcp-server',
                        'python_interpreter': 'python-executor-mcp-server',
                        'browser_navigator': 'browser-navigator-mcp-server',
                        'browser_navigator_server': 'browser-navigator-mcp-server'
                    }
                    
                    # 如果tool_id是能力名称，映射到正确的MCP服务器ID
                    actual_server_id = capability_to_server_map.get(tool_id, tool_id)
                    if actual_server_id != tool_id:
                        logger.info(f"Mapping capability '{tool_id}' to MCP server '{actual_server_id}'")
                    
                    # 检查并清理browser_navigate工具的URL参数
                    cleaned_params = params.copy()
                    if actual_server_id == "browser-navigator-mcp-server" and action == "browser_navigate":
                        url = cleaned_params.get("url", "")
                        if url.startswith("url: "):
                            cleaned_params["url"] = url[len("url: "):].strip()
                            logger.info(f"Cleaned URL for browser_navigate: {url} -> {cleaned_params['url']}")
                    
                    # 调用UnifiedToolLibrary的execute_tool方法
                    result = await self.tool_library.execute_tool(actual_server_id, action, cleaned_params)
                    tool_success = result.success # UnifiedToolLibrary返回的是ExecutionResult对象
                    
                    # 更新浏览器上下文状态
                    if tool_success and actual_server_id == 'browser-navigator-mcp-server' and result.data and isinstance(result.data, dict):
                        # 只在导航相关操作时更新浏览器上下文
                        if action in ['browser_navigate', 'browser_click', 'browser_scroll', 'browser_screenshot']:
                            current_context['browser_state'] = {
                                "url": result.data.get("url"),
                                "title": result.data.get("title"),
                                "content_summary": result.data.get("content_summary")
                            }
                            logger.info(f"Updated browser context: {current_context['browser_state']}")
                        # 对于browser_get_text等不会改变页面状态的操作，保持当前上下文不变
                    
                    # 如果是Python执行成功，并且有标准输出，添加到current_outputs
                    if tool_success and actual_server_id == 'python-executor-mcp-server' and result.data:
                        # 尝试从result.data中提取stdout信息
                        if isinstance(result.data, dict) and 'stdout' in result.data:
                            current_outputs.append(result.data['stdout'])
                        elif isinstance(result.data, str):
                            current_outputs.append(result.data)
                    
                    # 现在所有工具都是MCP Server，统一设置为TOOL_CALL
                    action_type = ActionType.TOOL_CALL
                    
                    # 浏览器状态和Python执行输出现在由各自的MCP Server管理，并通过ExecutionResult返回
                    # ReasoningRuntime 不再直接处理这些状态
                # 移除旧的被动触发逻辑，现在AI可以主动选择MCP搜索工具
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
                    # 直接从ExecutionResult获取错误信息（如果result不为None）
                    if result is not None:
                        # 确保current_attempt_err_type是ErrorType枚举或None
                        if isinstance(result.error_type, str):
                            try:
                                current_attempt_err_type = ErrorType(result.error_type)
                            except ValueError:
                                current_attempt_err_type = ErrorType.TOOL_ERROR
                        else:
                            current_attempt_err_type = result.error_type if result.error_type else ErrorType.TOOL_ERROR
                        
                        # 处理不同类型的result对象
                        if hasattr(result, 'error_message') and result.error_message:
                            current_attempt_err_msg = result.error_message
                        elif hasattr(result, 'message') and result.message:
                            current_attempt_err_msg = result.message
                        else:
                            current_attempt_err_msg = "Unknown tool error"
                    # 如果result为None，使用已设置的错误信息（current_attempt_err_type和current_attempt_err_msg）
                
                if tool_success:
                    # 对 observation 进行净化和简化
                    simplified_observation = f"Tool '{tool_id}/{action}' executed successfully."
                    if result and result.data:
                        if actual_server_id == 'browser-navigator-mcp-server' and isinstance(result.data, dict):
                            # 为浏览器操作创建更具信息量的摘要
                            if action == 'browser_get_text':
                                # 特殊处理browser_get_text
                                text = result.data.get('text', '')
                                text_length = result.data.get('length', 0)
                                if text:
                                    # 截取前500个字符作为预览
                                    preview = text[:500] + ('...' if len(text) > 500 else '')
                                    simplified_observation = f"Successfully retrieved page text ({text_length} characters). Preview:\n---\n{preview}\n---"
                                else:
                                    simplified_observation = "Successfully executed 'browser_get_text' but no text content was found."
                            else:
                                # 其他浏览器操作
                                url = result.data.get('url', 'N/A')
                                title = result.data.get('title', 'N/A')
                                simplified_observation = f"Successfully executed '{action}' on '{url}'. Page title is '{title}'."
                        elif actual_server_id == 'python-executor-mcp-server' and isinstance(result.data, dict):
                            # 为Python执行创建摘要
                            stdout = result.data.get('stdout', '').strip()
                            if stdout:
                                simplified_observation = f"Python code executed. Output (stdout):\n---\n{stdout[:200]}\n---" # 限制长度
                            else:
                                simplified_observation = "Python code executed with no output (stdout)."
                        else:
                            # 通用数据格式
                            simplified_observation = f"Tool '{tool_id}/{action}' executed successfully. Data received: {str(result.data)[:200]}" # 限制长度

                    observation = simplified_observation
                    break
                else:
                    logger.warning(
                        f"Step {step_id}, Action {action}, Attempt {attempt + 1}/{max_retries + 1} failed. "
                        f"ErrorType: {current_attempt_err_type}, ErrorMsg: {current_attempt_err_msg}"
                    )
                    
                    # 使用净化后的错误信息作为 observation
                    observation = f"Tool '{tool_id}/{action}' failed. Error: {current_attempt_err_msg}"

                    # 重试逻辑
                    is_retryable = False
                    if current_attempt_err_type in [ErrorType.NETWORK_ERROR, ErrorType.TIMEOUT, ErrorType.RATE_LIMIT]:
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
        
        # 如果循环结束但任务没有成功完成，设置错误状态
        if not success and steps:
            final_trajectory_error_type = steps[-1].error_type or ErrorType.EXECUTION_FAILED
            final_trajectory_error_message = steps[-1].error_message or f"Task failed after {len(steps)} steps"
            logger.warning(f"Task execution completed without success: {final_trajectory_error_message}")

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
                # 智能生成包含实际结果的最终结果
                # 首先检查是否有浏览器获取的内容
                browser_content = None
                python_output = None
                
                for step in reversed(steps[-3:]):  # 检查最近3个步骤
                    if not browser_content and 'Successfully retrieved page text' in step.observation:
                        if 'Preview:' in step.observation:
                            preview_start = step.observation.find('Preview:') + len('Preview:')
                            preview_end = step.observation.find('---', preview_start + 10)
                            if preview_end > preview_start:
                                browser_content = step.observation[preview_start:preview_end].strip()
                    
                    if not python_output and 'Python code executed' in step.observation and 'Output' in step.observation:
                        python_output = step.observation
                
                # 基于获取的内容生成智能摘要
                if browser_content:
                    final_result = f"任务完成。成功访问了网站并获取了页面内容：\n\n{browser_content[:800]}{'...' if len(browser_content) > 800 else ''}"
                elif python_output:
                    final_result = f"任务完成。{python_output}"
                elif current_outputs:
                    final_result = f"任务完成。生成结果：\n{chr(10).join(current_outputs[-2:])}"
                else:
                    # 回退到使用LLM生成摘要
                    final_result = await self.client.generate_task_summary(
                        task.description, [s.__dict__ for s in steps], current_outputs
                    )
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

    async def _should_install_new_mcp_server(self, task_description: str, current_steps: List[ExecutionStep], 
                                             failed_tool_id: str, failed_action: str) -> bool:
        """判断是否应该安装新的MCP服务器"""
        if not self.dynamic_mcp_manager:
            return False
        
        # 获取当前可用工具列表
        available_tools = []
        try:
            tool_specs = await self.tool_library.get_all_tools()
            for tool_spec in tool_specs:
                available_tools.append({
                    'name': tool_spec.name,
                    'description': tool_spec.description,
                    'capabilities': [{'name': cap.name} for cap in tool_spec.capabilities]
                })
        except Exception as e:
            logger.error(f"Failed to get available tools: {e}")
            return False
        
        # 准备之前的尝试信息
        previous_attempts = []
        for step in current_steps:
            if not step.success:
                previous_attempts.append({
                    'error_message': step.error_message or '',
                    'observation': step.observation or '',
                    'action': step.action_params.get('action', ''),
                    'tool_id': step.action_params.get('tool_id', '')
                })
        
        # 使用工具缺口检测器判断
        should_search, detection_result = await self.tool_gap_detector.should_trigger_mcp_search(
            task_description, available_tools, previous_attempts
        )
        
        if should_search:
            logger.info(f"MCP search triggered: {detection_result.overall_assessment}")
            return True
        
        return False
    
    async def _attempt_dynamic_mcp_installation(self, task_description: str, current_steps: List[ExecutionStep]) -> bool:
        """尝试动态安装MCP服务器"""
        if not self.dynamic_mcp_manager:
            logger.error("Dynamic MCP Manager not initialized")
            return False
        
        try:
            # 获取当前可用工具
            available_tools = []
            tool_specs = await self.tool_library.get_all_tools()
            for tool_spec in tool_specs:
                available_tools.append({
                    'name': tool_spec.name,
                    'description': tool_spec.description,
                    'capabilities': [{'name': cap.name} for cap in tool_spec.capabilities]
                })
            
            # 检测工具缺口
            detection_result = await self.tool_gap_detector.analyze_tool_sufficiency(task_description, available_tools)
            
            if detection_result.has_sufficient_tools:
                logger.info("No tool gaps detected")
                return False
            
            # 选择置信度最高的工具需求
            primary_requirement = max(detection_result.tool_requirements, key=lambda x: x.confidence_score)
            logger.info(f"Attempting to install MCP server for requirement: {primary_requirement.description}")
            
            # 搜索相关的MCP服务器
            search_strategy = await self.tool_gap_detector.get_search_strategy(detection_result)
            if not search_strategy:
                logger.warning("No valid search strategy generated")
                return False
            
            candidates = await self.dynamic_mcp_manager.search_mcp_servers(
                query=search_strategy["query"],
                capability_tags=search_strategy["keywords"]
            )
            
            if not candidates:
                logger.warning(f"No MCP server candidates found for query: {search_strategy['query']}")
                return False
            
            # 尝试安装最佳候选者
            best_candidate = candidates[0]
            logger.info(f"Installing best candidate: {best_candidate.name}")
            
            install_result = await self.dynamic_mcp_manager.install_mcp_server(best_candidate)
            
            if install_result.success:
                # 注册到工具库
                registration_result = await self.dynamic_mcp_manager.register_installed_server(
                    best_candidate, install_result
                )
                
                if registration_result.success:
                    logger.info(f"Successfully installed and registered MCP server: {best_candidate.name}")
                    return True
                else:
                    logger.error(f"Failed to register installed MCP server: {registration_result.error}")
                    return False
            else:
                logger.error(f"Failed to install MCP server: {install_result.error_message}")
                return False
        
        except Exception as e:
            logger.error(f"Error during dynamic MCP installation: {e}")
            return False

    async def _register_mcp_search_tool(self):
        """注册MCP搜索工具为一个可用工具"""
        from core.toolscore.interfaces import FunctionToolSpec, ToolCapability, ToolType
        
        try:
            # 定义MCP搜索工具的能力
            search_capability = ToolCapability(
                name="search_and_install_tools",
                description="**主要功能**：立即搜索并安装新的MCP服务器工具来完成当前任务。当发现缺少关键工具时，应优先使用此功能！",
                parameters={
                    "task_description": {
                        "type": "string",
                        "description": "当前任务的描述",
                        "required": True
                    },
                    "reason": {
                        "type": "string", 
                        "description": "为什么需要搜索新工具的原因",
                        "required": False
                    }
                },
                examples=[{
                    "task_description": "生成一张图片",
                    "reason": "当前没有图像生成工具"
                }]
            )
            
            analyze_capability = ToolCapability(
                name="analyze_tool_needs",
                description="仅分析工具需求，不执行安装。通常情况下应直接使用search_and_install_tools",
                parameters={
                    "task_description": {
                        "type": "string",
                        "description": "当前任务的描述",
                        "required": True
                    }
                },
                examples=[{
                    "task_description": "处理PDF文件"
                }]
            )
            
            # 创建工具规范
            mcp_search_spec = FunctionToolSpec(
                tool_id="mcp-search-tool",
                name="🔧 智能工具安装器",
                description="⚡ 当缺少工具时，立即搜索并安装新的MCP服务器工具。图像生成、文档处理、数据分析等新能力一键安装！",
                tool_type=ToolType.FUNCTION,
                capabilities=[search_capability, analyze_capability],
                tags=["essential", "tool-installer", "dynamic"],
                function_handler=self._handle_mcp_search_tool_call
            )
            
            # 注册到工具库
            result = await self.tool_library.register_function_tool(mcp_search_spec)
            
            if result.success:
                logger.info("MCP搜索工具已注册为系统工具")
            else:
                logger.error(f"MCP搜索工具注册失败: {result.error}")
                
        except Exception as e:
            logger.error(f"注册MCP搜索工具时发生错误: {e}")

    async def _handle_mcp_search_tool_call(self, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """处理MCP搜索工具调用"""
        try:
            if action == "search_and_install_tools":
                logger.info("MCP搜索工具被调用: search_and_install_tools")
                
                # 获取当前可用工具
                all_tools = await self.tool_library.get_all_tools()
                current_tools = [{"name": tool.tool_id, "description": tool.description} for tool in all_tools]
                
                # 调用MCP搜索工具
                result = await self.mcp_search_tool.search_and_install_tools(
                    task_description=parameters.get("task_description", ""),
                    current_available_tools=current_tools,
                    reason=parameters.get("reason", "")
                )
                
                # 如果安装成功，刷新工具库连接以获取新安装的工具
                if result.success and result.installed_tools:
                    logger.info(f"成功安装了 {len(result.installed_tools)} 个工具，正在刷新工具库连接...")
                    try:
                        # 对于Docker Hub安装的工具，需要特殊处理连接
                        for installed_tool in result.installed_tools:
                            if installed_tool.get("install_method") == "docker_hub":
                                await self._connect_docker_hub_tool(installed_tool)
                        
                        # 重新初始化工具库以发现新工具
                        await self.tool_library.initialize()
                        
                        # 获取更新后的工具列表
                        updated_tools = await self.tool_library.get_all_tools()
                        logger.info(f"工具库刷新完成，当前工具数量: {len(updated_tools)}")
                        
                    except Exception as e:
                        logger.warning(f"工具库刷新失败: {e}")
                
                return {
                    "success": result.success,
                    "message": result.message,
                    "installed_tools": result.installed_tools,
                    "error": result.message if not result.success else None
                }
                
            elif action == "analyze_tool_needs":
                logger.info("MCP搜索工具被调用: analyze_tool_needs")
                
                # 获取当前可用工具
                all_tools = await self.tool_library.get_all_tools()
                current_tools = [{"name": tool.tool_id, "description": tool.description} for tool in all_tools]
                
                # 调用工具需求分析
                result = await self.mcp_search_tool.analyze_tool_needs(
                    task_description=parameters.get("task_description", ""),
                    current_available_tools=current_tools
                )
                
                return result
                
            else:
                return {
                    "success": False,
                    "error": f"Unknown action: {action}"
                }
                
        except Exception as e:
            logger.error(f"MCP搜索工具调用失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def _connect_docker_hub_tool(self, installed_tool: Dict[str, Any]) -> None:
        """连接Docker Hub安装的MCP工具"""
        try:
            server_id = installed_tool.get("server_id")
            container_id = installed_tool.get("container_id") 
            
            if not server_id or not container_id:
                logger.warning(f"缺少连接信息: server_id={server_id}, container_id={container_id}")
                return
            
            # 检查容器是否正在运行
            import docker
            docker_client = docker.from_env()
            
            try:
                container = docker_client.containers.get(container_id)
                if container.status == 'running':
                    logger.info(f"Docker容器 {container_id} 正在运行，工具 {server_id} 可用")
                    
                    # 这里可以添加额外的连接逻辑，例如：
                    # - 验证MCP端点是否响应
                    # - 注册容器化工具到工具库
                    # - 设置工具库与容器的通信连接
                    
                else:
                    logger.warning(f"Docker容器 {container_id} 状态异常: {container.status}")
                    
            except docker.errors.NotFound:
                logger.error(f"Docker容器 {container_id} 未找到")
            except Exception as e:
                logger.error(f"检查Docker容器状态失败: {e}")
                
        except Exception as e:
            logger.error(f"连接Docker Hub工具失败: {e}")

    async def cleanup(self):
        """清理资源"""
        logger.info("Cleaning up EnhancedReasoningRuntime resources")
        
        # 清理动态MCP管理器
        if self.dynamic_mcp_manager:
            await self.dynamic_mcp_manager.cleanup()
        
        # 清理UnifiedToolLibrary管理的资源
        await self.tool_library.cleanup()

# 运行服务
if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        runtime = EnhancedReasoningRuntime()
        await runtime.initialize()
        
        from core.task_manager import start_runtime_service
        # 启动服务
        await start_runtime_service(runtime)
    
    asyncio.run(main())