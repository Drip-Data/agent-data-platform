"""
增强推理运行时 - 简化版本，专注LLM推理和执行
使用ToolScore API进行工具管理，移除复杂的本地工具管理逻辑
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
from core.toolscore.mcp_client import MCPToolClient
from runtimes.reasoning.toolscore_client import ToolScoreClient
from runtimes.reasoning.real_time_tool_client import RealTimeToolClient

logger = logging.getLogger(__name__)

class EnhancedReasoningRuntime(RuntimeInterface):
    """增强推理运行时 - 简化版本，专注LLM推理和执行"""
    
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
        self.metrics = EnhancedMetrics(port=8003)
        
        # 简化的工具管理架构
        self.toolscore_endpoint = os.getenv('TOOLSCORE_HTTP_URL', 'http://toolscore:8090')
        
        # 轻量级客户端
        self.toolscore_client = ToolScoreClient(self.toolscore_endpoint)
        self.real_time_client = RealTimeToolClient(self.toolscore_endpoint)
        
        # 保留MCP客户端用于直接工具调用
        toolscore_url = os.getenv('TOOLSCORE_URL', 'ws://toolscore:8080/websocket')
        self.mcp_client = MCPToolClient(toolscore_url)
        
        # 等待工具安装的任务
        self.pending_tool_requests = {}
        
    async def initialize(self):
        """初始化运行时 - 简化为纯工具消费者"""
        logger.info("🚀 初始化Enhanced Reasoning Runtime - 简化版本")
        
        # 等待ToolScore服务就绪
        logger.info("⏳ 等待ToolScore服务就绪...")
        if not await self.toolscore_client.wait_for_ready():
            logger.error("❌ ToolScore服务未就绪，将使用降级模式")
        
        # 连接实时更新
        await self.real_time_client.connect_real_time_updates()
        
        # 注册工具更新回调
        await self.real_time_client.register_tool_update_callback(
            self._on_new_tool_available
        )
        
        # 启动定期清理任务
        asyncio.create_task(self._periodic_cleanup())
        
        logger.info("✅ Enhanced Reasoning Runtime 已成功初始化为纯推理引擎")
        
    async def _on_new_tool_available(self, tool_event: Dict[str, Any]):
        """新工具可用时的回调"""
        tool_id = tool_event.get("tool_id")
        tool_name = tool_event.get("name", tool_id)
        
        logger.info(f"🎉 检测到新工具: {tool_name} ({tool_id})")
        
        # 检查是否有等待这个工具的任务
        completed_requests = []
        for task_id, request_info in list(self.pending_tool_requests.items()):
            if self._tool_matches_requirement(tool_event, request_info.get("required_capabilities", [])):
                logger.info(f"🚀 恢复等待任务: {task_id} (新工具: {tool_id})")
                
                # 执行恢复回调
                callback = request_info.get("resume_callback")
                if callback:
                    try:
                        await callback(tool_event)
                    except Exception as e:
                        logger.error(f"任务恢复回调执行失败: {e}")
                
                completed_requests.append(task_id)
        
        # 清理已完成的请求
        for task_id in completed_requests:
            self.pending_tool_requests.pop(task_id, None)
    
    def _tool_matches_requirement(self, tool_event: Dict[str, Any], 
                                required_capabilities: List[str]) -> bool:
        """检查工具是否满足需求"""
        if not required_capabilities:
            return True
        
        tool_capabilities = tool_event.get("capabilities", [])
        tool_capability_names = []
        
        # 提取能力名称
        for cap in tool_capabilities:
            if isinstance(cap, dict):
                tool_capability_names.append(cap.get("name", ""))
            elif isinstance(cap, str):
                tool_capability_names.append(cap)
        
        # 检查是否有匹配的能力
        for required_cap in required_capabilities:
            for tool_cap in tool_capability_names:
                if required_cap.lower() in tool_cap.lower() or tool_cap.lower() in required_cap.lower():
                    return True
        
            return False
            
    async def _periodic_cleanup(self):
        """定期清理过期请求"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟清理一次
                await self.real_time_client.cleanup_expired_requests()

                # 清理本地的过期请求
                current_time = time.time()
                expired_requests = []
                for task_id, request_info in self.pending_tool_requests.items():
                    if current_time - request_info.get("timestamp", 0) > 300:  # 5分钟过期
                        expired_requests.append(task_id)

                for task_id in expired_requests:
                    self.pending_tool_requests.pop(task_id, None)
                    logger.info(f"清理过期任务请求: {task_id}")
                
        except Exception as e:
                logger.error(f"定期清理任务异常: {e}")

    @property
    def runtime_id(self) -> str:
        return self._runtime_id

    async def capabilities(self) -> list:
        """获取运行时能力"""
        return ['llm_reasoning', 'tool_execution', 'dynamic_tool_request']

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 检查LLM客户端
            await self.client.generate_reasoning("health check", [], [])
            
            # 检查ToolScore连接
            toolscore_healthy = await self.toolscore_client.health_check()
            
            return toolscore_healthy
        except:
            return False

    async def execute(self, task: TaskSpec) -> TrajectoryResult:
        """执行推理任务 - 简化版本，使用ToolScore API"""
        start_time = time.time()
        trajectory_id = str(uuid.uuid4())
        steps: List[ExecutionStep] = []
        current_outputs: List[str] = []
        success = False
        final_trajectory_error_type: Optional[ErrorType] = None
        final_trajectory_error_message: Optional[str] = None
        
        # 统一的上下文，用于存储跨步骤的状态
        current_context: Dict[str, Any] = {
            "browser_state": None
        }
        
        # 从ToolScore获取可用工具
        logger.info("📋 从ToolScore获取可用工具...")
        available_tools_description = await self.real_time_client.get_fresh_tools_for_llm(
            fallback_client=self.toolscore_client
        )
        
        if not available_tools_description:
            logger.warning("⚠️ 未获取到可用工具，将尝试直接执行")
            available_tools_description = "暂无可用工具"
        
        logger.info(f"📋 获取到工具描述长度: {len(available_tools_description)} 字符")

        # 💡 新增: 智能任务需求分析
        logger.info("🧠 开始智能任务需求分析...")
        try:
            task_requirements = await self.client.analyze_task_requirements(task.description)
            
            logger.info("✅ 任务需求分析完成:")
            logger.info(f"   任务类型: {task_requirements.get('task_type', 'unknown')}")
            logger.info(f"   所需能力: {task_requirements.get('required_capabilities', [])}")
            logger.info(f"   推荐工具类型: {task_requirements.get('tools_needed', [])}")
            logger.info(f"   置信度: {task_requirements.get('confidence', 0.0)}")
            
            # 将需求分析结果添加到执行上下文
            current_context["task_requirements"] = task_requirements
            
        except Exception as e:
            logger.warning(f"⚠️ 任务需求分析失败: {e}，继续正常执行")
            current_context["task_requirements"] = None

        for step_id in range(1, task.max_steps + 1):
            # 生成推理决策
            serializable_steps = [s.to_dict() if hasattr(s, 'to_dict') else s.__dict__ for s in steps]
            
            decision = await self.client.generate_enhanced_reasoning(
                task_description=task.description,
                available_tools=[],  # 工具ID列表（如果需要）
                tool_descriptions=available_tools_description,  # 详细工具描述
                previous_steps=serializable_steps,
                execution_context=current_context
            )
            
            thinking = decision.get('thinking', f"Step {step_id}: Analyzing task and deciding next action")
            action = decision.get('action')
            tool_id = decision.get('tool_id') or decision.get('tool')
            params = decision.get('parameters', {})
            confidence = decision.get('confidence', 0.0)

            max_retries = 1
            retry_delay_seconds = 3
            action_type = ActionType.TOOL_CALL

            for attempt in range(max_retries + 1):
                tool_start = time.time()
                observation = ''
                tool_success = False
                current_attempt_err_type: Optional[ErrorType] = None
                current_attempt_err_msg: Optional[str] = None
                result = None

                execution_code = json.dumps({
                    'action': action,
                    'tool_id': tool_id,
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
                
                # 检查是否是工具能力请求
                elif action == 'request_tool_capability' or (tool_id and 'search' in tool_id.lower()):
                    logger.info("🔍 检测到工具能力请求，发起ToolScore API调用")
                    
                    # 从参数中提取任务描述和能力需求
                    task_desc = params.get('task_description', task.description)
                    required_caps = params.get('required_capabilities', [])
                    reason = params.get('reason', '')
                    
                    # 如果有理由，提取可能的能力需求
                    if reason and not required_caps:
                        # 简单的关键词提取
                        if 'image' in reason.lower() or 'picture' in reason.lower():
                            required_caps = ['image_generation']
                        elif 'file' in reason.lower() or 'document' in reason.lower():
                            required_caps = ['file_processing']
                        elif 'web' in reason.lower() or 'scraping' in reason.lower():
                            required_caps = ['web_scraping']
                    
                    # 调用ToolScore API
                    capability_result = await self.toolscore_client.request_tool_capability(
                        task_description=task_desc,
                        required_capabilities=required_caps,
                        auto_install=True
                    )
                    
                    if capability_result.get("success"):
                        # 工具安装成功
                        installed_tools = capability_result.get("installed_tools", [])
                        processing_time = capability_result.get("processing_time_ms", 0)
                        
                        if installed_tools:
                            tool_names = [tool.get("name", tool.get("tool_id", "unknown")) for tool in installed_tools]
                            observation = f"成功安装了 {len(installed_tools)} 个新工具: {', '.join(tool_names)}。处理时间: {processing_time}ms。新工具现在可以使用。"
                            
                            # 注册等待新工具的回调
                            await self.real_time_client.register_pending_request(
                                request_id=f"{trajectory_id}-step-{step_id}",
                                required_capabilities=required_caps,
                                callback=self._create_tool_available_callback(trajectory_id, step_id)
                            )
                            
                            # 更新工具列表
                            available_tools_description = await self.real_time_client.get_fresh_tools_for_llm(
                                fallback_client=self.toolscore_client
                            )
                        else:
                            observation = "工具安装请求已处理，但未安装新工具。现有工具可能已满足需求。"
                        
                        tool_success = True
                else:
                        # 工具安装失败
                        error_msg = capability_result.get("message", "未知错误")
                        observation = f"工具能力请求失败: {error_msg}"
                    tool_success = False
                        current_attempt_err_type = ErrorType.TOOL_ERROR
                        current_attempt_err_msg = error_msg

                # 常规工具调用
                elif tool_id and action:
                    logger.debug(f"Attempt {attempt + 1}: Executing action '{action}' with tool_id '{tool_id}'")
                    
                    # 直接通过MCP客户端执行工具
                    try:
                        # 清理参数
                        cleaned_params = {k: v for k, v in params.items() 
                                        if k not in ['action', 'tool_id', 'tool']}
                        
                        # 映射工具ID到实际的MCP服务器ID
                        actual_server_id = self._map_tool_id_to_server(tool_id)
                        
                        logger.info(f"🔧 调用MCP服务器: {actual_server_id}, 动作: {action}")
                        
                        # 调用MCP客户端
                        result = await self.mcp_client.execute_tool(actual_server_id, action, cleaned_params)
                        tool_success = result.success
                        
                        # 处理结果
                        if tool_success and result.data:
                            # 根据工具类型生成简化的观察结果
                            if 'python' in actual_server_id.lower():
                                stdout = result.data.get('stdout', '').strip() if isinstance(result.data, dict) else str(result.data)
                                if stdout:
                                    observation = f"Python代码执行成功。输出:\n{stdout[:200]}{'...' if len(stdout) > 200 else ''}"
                                    current_outputs.append(stdout)
                        else:
                                    observation = "Python代码执行成功，无输出。"
                            elif 'browser' in actual_server_id.lower():
                                if isinstance(result.data, dict):
                                    url = result.data.get('url', 'N/A')
                                    title = result.data.get('title', 'N/A')
                                    observation = f"浏览器操作成功。当前页面: {url}, 标题: {title}"
                                    
                            if action == 'browser_get_text':
                                text = result.data.get('text', '')
                                if text:
                                            preview = text[:300] + ('...' if len(text) > 300 else '')
                                            observation += f"\n页面内容预览:\n{preview}"
                                else:
                                    observation = f"浏览器操作 '{action}' 执行成功。"
                            else:
                                observation = f"工具 '{tool_id}' 执行成功。"
                            else:
                            observation = f"工具 '{tool_id}' 执行成功。"
                        
                    except Exception as e:
                        logger.error(f"工具执行异常: {e}")
                        tool_success = False
                        current_attempt_err_type = ErrorType.TOOL_ERROR
                        current_attempt_err_msg = str(e)
                        observation = f"工具 '{tool_id}' 执行失败: {str(e)}"

                else:
                    # 无效的工具调用
                    tool_success = False
                    current_attempt_err_type = ErrorType.SYSTEM_ERROR
                    if not tool_id:
                        current_attempt_err_msg = f"LLM未指定tool_id。尝试的动作: '{action}'"
                    elif not action:
                        current_attempt_err_msg = f"LLM未指定动作。工具: '{tool_id}'"
                    else:
                        current_attempt_err_msg = f"LLM尝试调用工具 '{tool_id}' 执行动作 '{action}'，但当前不支持或无效。"
                    observation = current_attempt_err_msg
                    action_type = ActionType.TOOL_CALL

                # 错误处理和重试逻辑
                if not tool_success:
                    logger.warning(
                        f"Step {step_id}, Action {action}, Attempt {attempt + 1}/{max_retries + 1} failed. "
                        f"ErrorType: {current_attempt_err_type}, ErrorMsg: {current_attempt_err_msg}"
                    )

                    # 重试逻辑
                    is_retryable = False
                    if current_attempt_err_type in [ErrorType.NETWORK_ERROR, ErrorType.TIMEOUT, ErrorType.RATE_LIMIT]:
                        is_retryable = True

                    if is_retryable and attempt < max_retries:
                        logger.info(f"Retrying action {action} after {retry_delay_seconds}s delay...")
                        await asyncio.sleep(retry_delay_seconds)
                    else:
                        break
                    else:
                        break
            
            # 完成任务检查
            exec_code_dict = {}
            if execution_code:
                try:
                    exec_code_dict = json.loads(execution_code)
                except json.JSONDecodeError:
                    pass
            
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
            last_step_exec_code = {}
            if steps[-1].execution_code:
                try:
                    last_step_exec_code = json.loads(steps[-1].execution_code)
                except json.JSONDecodeError:
                    pass

            if last_step_exec_code.get('action') == 'complete_task':
                final_result = steps[-1].observation
            else:
                # 智能生成最终结果
                browser_content = None
                python_output = None
                
                for step in reversed(steps[-3:]):
                    if not browser_content and 'Successfully retrieved page text' in step.observation:
                        if 'Preview:' in step.observation:
                            preview_start = step.observation.find('Preview:') + len('Preview:')
                            preview_end = step.observation.find('---', preview_start + 10)
                            if preview_end > preview_start:
                                browser_content = step.observation[preview_start:preview_end].strip()
                    
                    if not python_output and 'Python code executed' in step.observation and 'Output' in step.observation:
                        python_output = step.observation
                
                if browser_content:
                    final_result = f"任务完成。成功访问了网站并获取了页面内容：\n\n{browser_content[:800]}{'...' if len(browser_content) > 800 else ''}"
                elif python_output:
                    final_result = f"任务完成。{python_output}"
                elif current_outputs:
                    final_result = f"任务完成。生成结果：\n{chr(10).join(current_outputs[-2:])}"
                else:
                    final_result = await self.client.generate_task_summary(
                        task.description, [s.__dict__ for s in steps], current_outputs
                    )
        else:
            final_result = final_trajectory_error_message or "Task execution failed"

        # 创建轨迹结果
        trajectory = TrajectoryResult(
            task_id=task.task_id,
            steps=steps,
            success=success,
            final_result=final_result,
            total_duration=total_duration,
            error_type=final_trajectory_error_type,
            error_message=final_trajectory_error_message,
            metadata={
                'runtime_id': self.runtime_id,
                'original_task_id': task.task_id
            }
        )
        
        # 保存轨迹
        await self._save_trajectory(trajectory)
        
        return trajectory
    
    def _create_tool_available_callback(self, trajectory_id: str, step_id: int):
        """创建工具可用时的回调函数"""
        async def callback(tool_event: Dict[str, Any]):
            tool_name = tool_event.get("name", tool_event.get("tool_id", "unknown"))
            logger.info(f"🎉 任务 {trajectory_id} 步骤 {step_id}: 新工具 {tool_name} 现已可用")
        return callback
    
    def _map_tool_id_to_server(self, tool_id: str) -> str:
        """映射工具ID到实际的MCP服务器ID"""
        # 简单的映射逻辑，可以根据需要扩展
        mapping = {
            'python': 'python-executor-mcp-server',
            'python-executor': 'python-executor-mcp-server',
            'browser': 'browser-navigator-mcp-server',
            'browser-navigator': 'browser-navigator-mcp-server',
        }
        
        # 精确匹配
        if tool_id in mapping:
            return mapping[tool_id]
        
        # 部分匹配
        for key, value in mapping.items():
            if key in tool_id.lower():
                return value
        
        # 默认返回原始ID
        return tool_id
    
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
        logger.info("🧹 清理Enhanced Reasoning Runtime资源")
        
        # 关闭ToolScore客户端
        if self.toolscore_client:
            await self.toolscore_client.close()
        
        # 关闭实时客户端
        if self.real_time_client:
            await self.real_time_client.close()
        
        # 清理MCP客户端
        if self.mcp_client:
            await self.mcp_client.cleanup()

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