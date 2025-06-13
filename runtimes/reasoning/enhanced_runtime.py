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
        self.toolscore_endpoint = os.getenv('TOOLSCORE_HTTP_URL', 'http://localhost:8082')
        self.toolscore_websocket_endpoint = os.getenv('TOOLSCORE_WS_URL', 'ws://localhost:8082')
        
        # 轻量级客户端
        self.toolscore_client = ToolScoreClient(self.toolscore_endpoint)
        self.real_time_client = RealTimeToolClient(self.toolscore_websocket_endpoint)
        
        # 保留MCP客户端用于直接工具调用
        toolscore_url = os.getenv('TOOLSCORE_URL', 'ws://toolscore:8080/websocket')
        self.mcp_client = MCPToolClient(toolscore_url)
        
        # 等待工具安装的任务
        self.pending_tool_requests = {}
        # 📌 缓存实时工具事件，便于写入轨迹
        self._tool_event_buffer = []
        
    async def initialize(self):
        """初始化运行时 - 简化为纯工具消费者"""
        logger.info("🚀 初始化Enhanced Reasoning Runtime - 简化版本")
        
        # 等待ToolScore服务就绪
        logger.info("⏳ 等待ToolScore服务就绪...")
        toolscore_ready = await self.toolscore_client.wait_for_ready()
        if not toolscore_ready:
            logger.error("❌ ToolScore服务未就绪，将使用降级模式")
        else:
            logger.info("✅ ToolScore HTTP服务已就绪")
        
        # 连接实时更新
        logger.info(f"🔌 正在连接WebSocket端点: {self.toolscore_websocket_endpoint}")
        try:
            await self.real_time_client.connect_real_time_updates()
            logger.info("✅ WebSocket实时更新连接成功")
        except Exception as e:
            logger.error(f"❌ WebSocket连接失败，将继续运行但不会接收实时更新: {e}")
            # 不阻止初始化继续进行
        
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
        
        # 写入事件缓冲区，供当前执行中的任务记录
        self._tool_event_buffer.append({
            "tool_id": tool_id,
            "name": tool_name,
            "event": tool_event,
            "timestamp": time.time()
        })
        
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
        """执行任务"""
        logger.info(f"🧠 开始执行任务: {task.description}")
        start_time = time.time()
        trajectory_id = task.task_id
        success = False
        final_trajectory_error_type = None
        final_trajectory_error_message = None
        
        steps: List[ExecutionStep] = []
        max_steps = 10
        max_retries = 1
        retry_delay_seconds = 2
        current_outputs = []  # 用于存储每步的输出
        
        # 🔍 新增：收集LLM交互信息
        current_step_llm_interactions = []
        
        # 获取可用工具描述
        logger.info("📋 从ToolScore获取可用工具...")
        available_tools_description = await self.real_time_client.get_fresh_tools_for_llm(
            fallback_client=self.toolscore_client
        )
        logger.info(f"📋 获取到工具描述长度: {len(available_tools_description)} 字符")

        # === 记录首次暴露给 LLM 的工具集合 ===
        expose_step = ExecutionStep(
            step_id=len(steps)+1,
            action_type=ActionType.TOOL_CALL,
            action_params={"tools_snapshot": available_tools_description},
            observation="Tools exposed to LLM for planning",
            success=True
        )
        steps.append(expose_step)

        # 智能任务需求分析
        logger.info("🧠 开始智能任务需求分析...")
                
        # 🔍 新增：记录任务需求分析的LLM交互
        task_analysis_interactions = []
        original_call_api = self.client._call_api
        async def wrapped_call_api_for_analysis(prompt: str) -> str:
            interaction_start = time.time()
            response = await original_call_api(prompt)
            
            from core.interfaces import LLMInteraction
            interaction = LLMInteraction(
                provider=self.client.provider.value if hasattr(self.client.provider, 'value') else str(self.client.provider),
                model=getattr(self.client, 'model', 'unknown'),
                context="task_requirements_analysis",
                prompt=prompt,
                prompt_length=len(prompt),
                prompt_type="task_analysis",
                response=response,
                response_length=len(response),
                response_time=time.time() - interaction_start
            )
            task_analysis_interactions.append(interaction)
            return response
        
        # 临时替换方法进行任务分析
        self.client._call_api = wrapped_call_api_for_analysis
        try:
            task_requirements = await self.client.analyze_task_requirements(task.description)
        finally:
            self.client._call_api = original_call_api
        
        logger.info("✅ 任务需求分析完成:")
        logger.info(f"   任务类型: {task_requirements.get('task_type')}")
        logger.info(f"   所需能力: {task_requirements.get('required_capabilities', [])}")
        logger.info(f"   推荐工具类型: {task_requirements.get('tools_needed', [])}")
        logger.info(f"   置信度: {task_requirements.get('confidence')}")
        
        # 保存任务分析的LLM交互到第一步的预备阶段
        current_step_llm_interactions.extend(task_analysis_interactions)

        """### 自动缺口检测 & 修复 ###"""
        try:
            # 拉取当前已注册工具（字典列表形式）
            tools_resp = await self.toolscore_client.get_available_tools()
            current_tools_meta = tools_resp.get("available_tools", [])

            gap_result = await self.toolscore_client.analyze_tool_gap(
                task_description=task.description,
                current_tools=current_tools_meta
            )

            if gap_result and not gap_result.get("has_sufficient_tools", True):
                missing_caps = gap_result.get("gap_analysis", {}).get("missing_capabilities", [])

                logger.info(
                    f"⚠ 检测到能力缺口，缺少: {missing_caps or '未知'}. 正在请求 ToolScore 自动安装…")

                cap_req_res = await self.toolscore_client.request_tool_capability(
                    task_description=task.description,
                    required_capabilities=missing_caps,
                    auto_install=True
                )

                if cap_req_res.get("success") and cap_req_res.get("installed_tools"):
                    logger.info(
                        f"🛠 已触发安装 {len(cap_req_res['installed_tools'])} 个工具，注册等待事件…")

                    # 通过 RealTimeToolClient 等待新工具；注册回调但同时轮询，最多 60s
                    await self.real_time_client.register_pending_request(
                        request_id=f"{task.task_id}-auto-gap-fix", 
                        required_capabilities=missing_caps
                    )

                    wait_start = time.time()
                    WAIT_TIMEOUT = 60
                    while time.time() - wait_start < WAIT_TIMEOUT:
                        # 判断是否已满足能力
                        fresh_tools = await self.toolscore_client.get_available_tools()
                        fresh_caps_ok = False
                        for tool in fresh_tools.get("available_tools", []):
                            caps = [c.get("name") if isinstance(c, dict) else c for c in tool.get("capabilities", [])]
                            if any(any(mc.lower() in (cap or "").lower() for cap in caps) for mc in missing_caps):
                                fresh_caps_ok = True
                                break
                        if fresh_caps_ok:
                            logger.info("✅ 缺口工具已就位，继续任务执行")
                            break
                        await asyncio.sleep(2)
                else:
                    logger.warning("ToolScore 未能自动安装所需工具，后续可能依赖 LLM 自行检索。")
        except Exception as auto_gap_err:
            logger.error(f"自动缺口检测/修复过程异常: {auto_gap_err}")

        for step_id in range(1, max_steps + 1):
            # 🔍 重置当前步骤的LLM交互记录
            current_step_llm_interactions = []
            
            logger.info(f"🔄 执行步骤 {step_id}/{max_steps}")
            
            tool_start = time.time()
            observation = ""
            current_attempt_err_type = None
            current_attempt_err_msg = None
            tool_success = False
            action_type = ActionType.TOOL_CALL
            thinking = ""
            execution_code = ""
            
            # 🔍 新增：包装LLM客户端以收集交互信息
            original_call_api = self.client._call_api
            async def wrapped_call_api(prompt: str) -> str:
                # 记录LLM交互开始
                interaction_start = time.time()
                
                # 调用原始方法
                response = await original_call_api(prompt)
                
                # 记录LLM交互
                from core.interfaces import LLMInteraction
                interaction = LLMInteraction(
                    provider=self.client.provider.value if hasattr(self.client.provider, 'value') else str(self.client.provider),
                    model=getattr(self.client, 'model', 'unknown'),
                    context=f"step_{step_id}_reasoning",
                    prompt=prompt,
                    prompt_length=len(prompt),
                    prompt_type="task_execution",
                    response=response,
                    response_length=len(response),
                    response_time=time.time() - interaction_start
                )
                current_step_llm_interactions.append(interaction)
                return response
            
            # 临时替换方法
            self.client._call_api = wrapped_call_api
            
            try:
                # 获取下一个动作
                serializable_steps = [s.to_dict() if hasattr(s, 'to_dict') else s.__dict__ for s in steps]
                
                # 获取已注册工具ID列表和描述
                registered_tools = await self.toolscore_client.get_available_tools()
                available_tool_ids = [tool.get('tool_id') for tool in registered_tools.get('available_tools', [])]
                available_tools_description = await self.real_time_client.get_fresh_tools_for_llm(
                    fallback_client=self.toolscore_client
                )
                
                action_result = await self.client.generate_enhanced_reasoning(
                    task_description=task.description,
                    available_tools=available_tool_ids,  # 添加已注册工具ID列表
                    tool_descriptions=available_tools_description,  # 详细工具描述
                    previous_steps=serializable_steps,
                    execution_context={}
                )
                
                thinking = action_result.get('thinking', f"Step {step_id}: Analyzing task and deciding next action")
                action = action_result.get('action')
                tool_id = action_result.get('tool_id') or action_result.get('tool')
                params = action_result.get('parameters', {})
                
                # 添加action和tool_id到params中以保持兼容性
                if action:
                    params['action'] = action
                if tool_id:
                    params['tool_id'] = tool_id

                execution_code = json.dumps({
                    'action': action,
                    'tool_id': tool_id,
                    'parameters': params
                }, ensure_ascii=False)
            finally:
                # 恢复原始方法
                self.client._call_api = original_call_api

            # 尝试执行工具调用，包含重试机制
            for attempt in range(max_retries + 1):
                
                # 特殊处理：检查是否完成任务
                if action == 'complete_task':
                    logger.info("🎯 LLM认为任务已完成")
                    
                    # 🔍 新增：记录完成任务的总结生成LLM交互
                    complete_summary_interactions = []
                    original_call_api_complete = self.client._call_api
                    async def wrapped_call_api_for_complete_summary(prompt: str) -> str:
                        interaction_start = time.time()
                        response = await original_call_api_complete(prompt)
                        
                        from core.interfaces import LLMInteraction
                        interaction = LLMInteraction(
                            provider=self.client.provider.value if hasattr(self.client.provider, 'value') else str(self.client.provider),
                            model=getattr(self.client, 'model', 'unknown'),
                            context=f"step_{step_id}_complete_task_summary",
                            prompt=prompt,
                            prompt_length=len(prompt),
                            prompt_type="complete_task_summary",
                            response=response,
                            response_length=len(response),
                            response_time=time.time() - interaction_start
                        )
                        complete_summary_interactions.append(interaction)
                        return response
                    
                    self.client._call_api = wrapped_call_api_for_complete_summary
                    try:
                        summary = await self.client.generate_task_summary(
                            task.description, [s.__dict__ for s in steps], current_outputs
                        )
                    finally:
                        self.client._call_api = original_call_api_complete
                    
                    # 将完成任务的总结LLM交互添加到当前步骤
                    current_step_llm_interactions.extend(complete_summary_interactions)
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
                        duration=duration,
                        llm_interactions=current_step_llm_interactions  # 🔍 新增
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
                            registered_tools = await self.toolscore_client.get_available_tools()
                            available_tool_ids = [tool.get('tool_id') for tool in registered_tools.get('available_tools', [])]
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
                
                # 🔍 新增：处理mcp-search-tool的调用
                elif tool_id == 'mcp-search-tool' or action in ['search_and_install_tools', 'analyze_tool_needs']:
                    logger.info(f"🛠️ 检测到mcp-search-tool调用: action={action}")
                    
                    try:
                        # 🔍 通过ToolScore API调用mcp-search-tool
                        if action == 'analyze_tool_needs':
                            # 分析工具需求
                            task_desc = params.get('task_description', task.description)
                            
                            # 调用ToolScore的工具分析API
                            analysis_result = await self.toolscore_client.analyze_tool_needs(
                                task_description=task_desc
                            )
                            
                            if analysis_result.get("success"):
                                analysis = analysis_result.get("analysis", {})
                                needed_tools = analysis.get("needed_tools", [])
                                recommendations = analysis.get("recommendations", "")
                                
                                observation = f"工具需求分析完成。需要的工具类型: {', '.join(needed_tools)}。建议: {recommendations}"
                                tool_success = True
                            else:
                                error_msg = analysis_result.get("message", "分析失败")
                                observation = f"工具需求分析失败: {error_msg}"
                                tool_success = False
                                
                        elif action == 'search_and_install_tools':
                            # 搜索并安装工具
                            task_desc = params.get('task_description', task.description)
                            reason = params.get('reason', '')
                            
                            # 调用ToolScore的工具搜索和安装API
                            search_result = await self.toolscore_client.search_and_install_tools(
                                task_description=task_desc,
                                reason=reason
                            )
                            
                            if search_result.get("success"):
                                installed_tools = search_result.get("installed_tools", [])
                                
                                if installed_tools:
                                    tool_names = [tool.get("name", tool.get("tool_id", "unknown")) for tool in installed_tools]
                                    observation = f"成功搜索并安装了 {len(installed_tools)} 个新工具: {', '.join(tool_names)}。"
                                    
                                    # 更新可用工具描述
                                    try:
                                        available_tools_description = await self.real_time_client.get_fresh_tools_for_llm(
                                            fallback_client=self.toolscore_client
                                        )
                                        logger.info("✅ 已更新可用工具列表")
                                    except Exception as e:
                                        logger.warning(f"更新工具列表失败: {e}")
                                else:
                                    observation = "搜索完成，但未找到合适的新工具。"
                                
                                tool_success = True
                            else:
                                error_msg = search_result.get("message", "搜索失败")
                                observation = f"工具搜索失败: {error_msg}"
                                tool_success = False
                        else:
                            # 未知的mcp-search-tool动作
                            observation = f"不支持的mcp-search-tool动作: {action}"
                            tool_success = False
                            
                    except Exception as e:
                        logger.error(f"mcp-search-tool调用异常: {e}")
                        observation = f"mcp-search-tool调用失败: {str(e)}"
                        tool_success = False
                        current_attempt_err_type = ErrorType.TOOL_ERROR
                        current_attempt_err_msg = str(e)

                # 常规工具调用
                elif tool_id and action:
                    logger.info(f"🔧 执行工具调用: tool_id={tool_id}, action={action}")
                    logger.debug(f"Attempt {attempt + 1}: Executing action '{action}' with tool_id '{tool_id}'")
                    
                    # 🔍 首先尝试通过ToolScore API执行工具
                    try:
                        # 清理参数
                        cleaned_params = {k: v for k, v in params.items() 
                                        if k not in ['action', 'tool_id', 'tool']}
                        
                        logger.info(f"🌐 通过ToolScore API执行工具: {tool_id}/{action}")
                        
                        # 调用ToolScore的工具执行API
                        execution_result = await self.toolscore_client.execute_tool(
                            tool_id=tool_id,
                            action=action,
                            parameters=cleaned_params
                        )
                        
                        if execution_result.get("success"):
                            tool_success = True
                            result_data = execution_result.get("result", {})
                            
                            # 处理执行结果
                            if isinstance(result_data, dict):
                                if result_data.get("stdout"):
                                    output = result_data["stdout"].strip()
                                    observation = f"工具 '{tool_id}/{action}' 执行成功。输出: {output[:300]}{'...' if len(output) > 300 else ''}"
                                    current_outputs.append(output)
                                else:
                                    observation = f"工具 '{tool_id}/{action}' 执行成功。"
                            else:
                                output_str = str(result_data)
                                observation = f"工具 '{tool_id}/{action}' 执行成功。结果: {output_str[:300]}{'...' if len(output_str) > 300 else ''}"
                                current_outputs.append(output_str)
                                
                            logger.info(f"✅ 工具执行成功: {tool_id}")
                            
                        else:
                            # ToolScore执行失败，尝试直接MCP调用
                            error_msg = execution_result.get("message", "执行失败")
                            logger.warning(f"ToolScore执行失败: {error_msg}，尝试直接MCP调用")
                            
                            # 映射工具ID到实际的MCP服务器ID
                            actual_server_id = self._map_tool_id_to_server(tool_id)
                            
                            logger.info(f"🔧 直接调用MCP服务器: {actual_server_id}, 动作: {action}")
                            
                            # 调用MCP客户端
                            result = await self.mcp_client.execute_tool(actual_server_id, action, cleaned_params)
                            tool_success = result.success
                            
                            # 处理结果 - 修复数据截断问题
                            if tool_success and result.data:
                                # 安全处理响应数据，避免截断
                                try:
                                    if isinstance(result.data, dict):
                                        # 对于字典类型，生成简化但完整的观察结果
                                        data_summary = {}
                                        for key, value in result.data.items():
                                            if isinstance(value, (str, int, float, bool)):
                                                data_summary[key] = value
                                            elif isinstance(value, dict):
                                                # 嵌套字典，只保留关键字段
                                                data_summary[key] = {k: v for k, v in list(value.items())[:3]}
                                            elif isinstance(value, list):
                                                # 列表，只保留长度信息
                                                data_summary[key] = f"List[{len(value)} items]"
                                            else:
                                                data_summary[key] = str(type(value).__name__)
                                        
                                        observation = f"Tool '{tool_id}/{action}' executed successfully. Summary: {json.dumps(data_summary, ensure_ascii=False)}"
                                    else:
                                        # 对于非字典类型，转换为字符串并限制长度
                                        data_str = str(result.data)
                                        if len(data_str) > 500:
                                            data_str = data_str[:500] + "...[truncated]"
                                        observation = f"Tool '{tool_id}/{action}' executed successfully. Data: {data_str}"
                                    
                                except Exception as e:
                                    logger.warning(f"Error processing tool result: {e}")
                                    observation = f"Tool '{tool_id}/{action}' executed successfully, but response processing failed: {str(e)}"
                                
                                # 根据工具类型生成特定的观察结果
                                if 'python' in actual_server_id.lower():
                                    if isinstance(result.data, dict):
                                        stdout = result.data.get('stdout', '').strip()
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
                                if tool_success:
                                    observation = f"Tool '{tool_id}/{action}' executed successfully."
                                else:
                                    observation = f"Tool '{tool_id}/{action}' execution failed: {result.error_message or 'Unknown error'}"

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
                duration=duration,
                llm_interactions=current_step_llm_interactions  # 🔍 新增
            ))

            # 检查是否完成 - 也需要记录LLM交互
            completion_interactions = []
            original_call_api = self.client._call_api
            async def wrapped_call_api_for_completion(prompt: str) -> str:
                interaction_start = time.time()
                response = await original_call_api(prompt)
                
                from core.interfaces import LLMInteraction
                interaction = LLMInteraction(
                    provider=self.client.provider.value if hasattr(self.client.provider, 'value') else str(self.client.provider),
                    model=getattr(self.client, 'model', 'unknown'),
                    context=f"step_{step_id}_completion_check",
                    prompt=prompt,
                    prompt_length=len(prompt),
                    prompt_type="completion_check",
                    response=response,
                    response_length=len(response),
                    response_time=time.time() - interaction_start
                )
                completion_interactions.append(interaction)
                return response
            
            self.client._call_api = wrapped_call_api_for_completion
            try:
                completion = await self.client.check_task_completion(
                    task.description,
                    [s.__dict__ for s in steps],
                    current_outputs
                )
            finally:
                self.client._call_api = original_call_api
            
            # 将完成检查的LLM交互添加到当前步骤
            if completion_interactions:
                steps[-1].llm_interactions.extend(completion_interactions)
            
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
                    # 🔍 新增：记录任务总结生成的LLM交互
                    summary_interactions = []
                    original_call_api = self.client._call_api
                    async def wrapped_call_api_for_summary(prompt: str) -> str:
                        interaction_start = time.time()
                        response = await original_call_api(prompt)
                        
                        from core.interfaces import LLMInteraction
                        interaction = LLMInteraction(
                            provider=self.client.provider.value if hasattr(self.client.provider, 'value') else str(self.client.provider),
                            model=getattr(self.client, 'model', 'unknown'),
                            context="final_task_summary",
                            prompt=prompt,
                            prompt_length=len(prompt),
                            prompt_type="task_summary",
                            response=response,
                            response_length=len(response),
                            response_time=time.time() - interaction_start
                        )
                        summary_interactions.append(interaction)
                        return response
                    
                    self.client._call_api = wrapped_call_api_for_summary
                    try:
                        final_result = await self.client.generate_task_summary(
                            task.description, [s.__dict__ for s in steps], current_outputs
                        )
                    finally:
                        self.client._call_api = original_call_api
                    
                    # 将总结生成的LLM交互添加到最后一步
                    if summary_interactions and steps:
                        steps[-1].llm_interactions.extend(summary_interactions)
        else:
            final_result = final_trajectory_error_message or "Task execution failed"

        # 创建轨迹结果
        trajectory = TrajectoryResult(
            task_name=task.task_id,  # 使用task_id作为task_name
            task_id=task.task_id,
            task_description=task.description,
            runtime_id=self.runtime_id,
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
        
        # === 将运行期间捕获的新工具事件追加到轨迹 ===
        if self._tool_event_buffer:
            for ev in self._tool_event_buffer:
                steps.append(ExecutionStep(
                    step_id=len(steps)+1,
                    action_type=ActionType.TOOL_CALL,
                    action_params=ev,
                    observation=f"New tool available during execution: {ev.get('name')}",
                    success=True
                ))
            self._tool_event_buffer.clear()
        
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