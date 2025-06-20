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
from core.utils.path_utils import get_trajectories_dir
from runtimes.reasoning.toolscore_client import ToolScoreClient
from runtimes.reasoning.real_time_tool_client import RealTimeToolClient
from core.local_python_executor import LocalPythonExecutor
from core.tool_usage_tracker import ToolUsageTracker
from core.memory_manager import MemoryManager
from core.step_planner import StepPlanner
from core.trajectory_enhancer import TrajectoryEnhancer

logger = logging.getLogger(__name__)

class EnhancedReasoningRuntime(RuntimeInterface):
    """增强推理运行时 - 简化版本，专注LLM推理和执行"""
    def __init__(self, config_manager, llm_client, toolscore_client, redis_manager=None, toolscore_websocket_endpoint: Optional[str] = None):
        self._runtime_id = f"enhanced-reasoning-{uuid.uuid4()}"
        self.config_manager = config_manager
        self.client = llm_client
        self.toolscore_client = toolscore_client
        self.metrics = EnhancedMetrics(port=8003)
        
        # 初始化记忆管理器和步骤规划器
        self.memory_manager = MemoryManager(redis_manager=redis_manager)
        self.step_planner = StepPlanner(llm_client=llm_client, memory_manager=self.memory_manager)
        
        # 🔍 初始化轨迹增强器
        self.trajectory_enhancer = TrajectoryEnhancer()
        
        # 使用配置管理器获取服务端点
        try:
            ports_config = self.config_manager.get_ports_config()
            toolscore_http_port = ports_config['mcp_servers']['toolscore_http']['port']
            toolscore_mcp_port = ports_config['mcp_servers']['toolscore_mcp']['port']
            logger.info(f"DEBUG: Loaded toolscore_http_port: {toolscore_http_port}, toolscore_mcp_port: {toolscore_mcp_port}")
            
            self.toolscore_endpoint = os.getenv('TOOLSCORE_HTTP_URL', f'http://localhost:{toolscore_http_port}')
            # 使用 toolscore_mcp_port (例如8000) 而不是 toolscore_http_port (8091)
            self.toolscore_websocket_endpoint = toolscore_websocket_endpoint or os.getenv('TOOLSCORE_WS_URL', f'ws://localhost:{toolscore_mcp_port}')
            logger.info(f"DEBUG: Configured toolscore_websocket_endpoint (using mcp_port): {self.toolscore_websocket_endpoint}")
        except Exception as e:
            logger.warning(f"配置加载失败，使用默认端口: {e}")
            self.toolscore_endpoint = os.getenv('TOOLSCORE_HTTP_URL', 'http://localhost:8091')
            # 如果配置加载失败，使用默认端口
            self.toolscore_websocket_endpoint = toolscore_websocket_endpoint or os.getenv('TOOLSCORE_WS_URL', 'ws://localhost:8000')
        
        # 轻量级客户端
        self.real_time_client = RealTimeToolClient(self.toolscore_websocket_endpoint)
        
        # 保留MCP客户端用于直接工具调用
        toolscore_url = os.getenv('TOOLSCORE_URL', f'ws://localhost:{toolscore_mcp_port}/websocket')
        self.mcp_client = MCPToolClient(toolscore_url)
        
        # 等待工具安装的任务
        self.pending_tool_requests = {}
        # 📌 缓存实时工具事件，便于写入轨迹
        self._tool_event_buffer = []
        
        # 📈 失败历史记录，用于避免重复失败的操作
        self.failure_history = {
            'tool_installations': set(),  # 记录失败的工具安装
            'tool_calls': {},  # 记录失败的工具调用
            'search_queries': set()  # 记录失败的搜索查询
        }
        
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
        max_steps = task.max_steps or 10  # 使用动态max_steps，默认为10
        max_retries = 1
        retry_delay_seconds = 2
        current_outputs = []  # 用于存储每步的输出
        
        # 🔍 启动轨迹增强和资源追踪
        tracking_info = self.trajectory_enhancer.start_task_tracking(trajectory_id)
        logger.info(f"🔍 轨迹追踪已启动: {tracking_info}")
        
        # 生成会话ID用于记忆管理
        session_id = f"session_{trajectory_id}_{int(start_time)}"
        
        logger.info(f"📊 任务配置: max_steps={max_steps}, session_id={session_id}")
        
        # 🔍 新增：收集LLM交互信息
        current_step_llm_interactions = []
        
        # 🔧 新增：工具使用跟踪器
        tool_tracker = ToolUsageTracker()
        
        # 获取可用工具描述
        logger.info("📋 从ToolScore获取可用工具...")
        available_tools_description = await self.real_time_client.get_fresh_tools_for_llm(
            fallback_client=self.toolscore_client
        )
        logger.info(f"📋 获取到工具描述长度: {len(available_tools_description)} 字符")
        logger.info(f"📋 工具描述内容预览: {available_tools_description[:500]}...")
        
        # 🔧 记录可用工具信息
        tool_tracker.set_available_tools(available_tools_description)
        
        # 检查是否有可用工具
        if "暂无可用工具" in available_tools_description or len(available_tools_description.strip()) == 0:
            logger.warning("⚠️ 检测到暂无可用工具，可能存在工具注册问题")

        # === 记录首次暴露给 LLM 的工具集合 ===
        step_start_time = time.time()
        expose_step = ExecutionStep(
            step_id=len(steps)+1,
            action_type=ActionType.TOOL_CALL,
            action_params={"tools_snapshot": available_tools_description},
            observation="Tools exposed to LLM for planning",
            success=True,
            event_source="system",
            triggering_event="task_initialization"
        )
        step_end_time = time.time()
        expose_step.duration = step_end_time - step_start_time
        expose_step.resource_usage = self.trajectory_enhancer.calculate_step_resource_usage(step_start_time, step_end_time)
        
        # 添加子事件
        # 从工具描述中估算工具数量
        tools_count = available_tools_description.count('- ') if available_tools_description else 0
        self.trajectory_enhancer.add_sub_event_to_step(
            expose_step, 
            "tools_exposed", 
            f"Exposed {tools_count} tools to LLM",
            {"tools_count": tools_count}
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
            interaction = LLMInteraction()
            interaction.provider = self.client.provider.value if hasattr(self.client.provider, 'value') else str(self.client.provider)
            interaction.model = getattr(self.client, 'model', 'unknown')
            interaction.context = "task_requirements_analysis"
            interaction.prompt = prompt
            interaction.prompt_length = len(prompt)
            interaction.prompt_type = "task_analysis"
            interaction.response = response
            interaction.response_length = len(response)
            interaction.response_time = time.time() - interaction_start
            task_analysis_interactions.append(interaction)
            return response
        
        # 临时替换方法进行任务分析
        self.client._call_api = wrapped_call_api_for_analysis
        try:
            # === 上下文注入：为任务分析添加记忆上下文 ===
            enhanced_task_description = task.description
            try:
                # 获取跨会话洞察用于任务分析
                cross_session_insights = await self.memory_manager.get_cross_session_insights(limit=2)
                if cross_session_insights:
                    insights_context = "历史经验参考: " + "; ".join(cross_session_insights)
                    enhanced_task_description = f"{task.description}\n\n{insights_context}"
                    logger.debug(f"🧠 任务分析已增强历史洞察上下文")
            except Exception as ctx_err:
                logger.warning(f"获取任务分析上下文失败: {ctx_err}")
            
            task_requirements = await self.client.analyze_task_requirements(enhanced_task_description)
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
            # 拉取当前已注册工具（列表形式）
            current_tools_meta = await self.toolscore_client.get_available_tools()

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
                        # fresh_tools 现在是一个工具名称列表
                        for tool_id in fresh_tools:
                            # 简单检查工具名称是否包含所需能力
                            if any(mc.lower() in tool_id.lower() for mc in missing_caps):
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

        # === 生成初始执行计划 ===
        try:
            logger.info("🧠 生成多步执行计划...")
            available_tool_ids = await self.toolscore_client.get_available_tools()
            initial_plan = await self.step_planner.generate_initial_plan(
                task, available_tool_ids, session_id
            )
            logger.info(f"📋 生成执行计划: {len(initial_plan.planned_steps)} 步骤, 置信度: {initial_plan.confidence:.3f}")
            max_steps = min(max_steps, initial_plan.max_steps)  # 使用计划中的max_steps
        except Exception as plan_err:
            logger.error(f"生成执行计划失败: {plan_err}, 使用传统执行模式")
            initial_plan = None

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
                interaction = LLMInteraction()
                interaction.provider = self.client.provider.value if hasattr(self.client.provider, 'value') else str(self.client.provider)
                interaction.model = getattr(self.client, 'model', 'unknown')
                interaction.context = f"step_{step_id}_reasoning"
                interaction.prompt = prompt
                interaction.prompt_length = len(prompt)
                interaction.prompt_type = "task_execution"
                interaction.response = response
                interaction.response_length = len(response)
                interaction.response_time = time.time() - interaction_start
                current_step_llm_interactions.append(interaction)
                return response
            
            # 临时替换方法
            self.client._call_api = wrapped_call_api
            
            try:
                # === 智能步骤规划：优先使用StepPlanner ===
                planned_step = None
                if initial_plan:
                    # 使用步骤规划器获取下一步
                    try:
                        available_tool_ids = await self.toolscore_client.get_available_tools()
                        planned_step = await self.step_planner.plan_next_step(
                            task, steps, available_tool_ids, session_id
                        )
                        if planned_step:
                            logger.info(f"📋 使用规划步骤: {planned_step.action} -> {planned_step.tool_id}")
                            thinking = f"Step {step_id}: 执行计划步骤 - {planned_step.action}"
                            action = planned_step.action
                            tool_id = planned_step.tool_id
                            params = planned_step.parameters.copy()
                        else:
                            logger.info("📋 步骤规划器认为任务可能已完成，检查完成状态")
                    except Exception as plan_step_err:
                        logger.warning(f"步骤规划失败，回退到传统方式: {plan_step_err}")
                
                # === 传统方式：当没有规划步骤时 ===
                if not planned_step:
                    # 获取下一个动作
                    serializable_steps = [s.to_dict() if hasattr(s, 'to_dict') else s.__dict__ for s in steps]
                    
                    # 获取已注册工具ID列表和描述
                    available_tool_ids = await self.toolscore_client.get_available_tools()
                    # available_tool_ids现在是一个工具ID列表
                    available_tools_description = await self.real_time_client.get_fresh_tools_for_llm(
                        fallback_client=self.toolscore_client
                    )
                    
                    # === 上下文注入：获取记忆上下文并注入到执行上下文中 ===
                    memory_context = ""
                    cross_session_insights = []
                    try:
                        # 获取当前会话的上下文摘要
                        memory_context = await self.memory_manager.generate_context_summary(
                            session_id, max_steps=5
                        )
                        # 获取跨会话洞察
                        cross_session_insights = await self.memory_manager.get_cross_session_insights(limit=3)
                        logger.debug(f"🧠 获取记忆上下文: {len(memory_context)} 字符, {len(cross_session_insights)} 洞察")
                    except Exception as memory_ctx_err:
                        logger.warning(f"获取记忆上下文失败: {memory_ctx_err}")
                    
                    # 构建增强的执行上下文
                    enhanced_execution_context = {
                        "step_number": step_id,
                        "max_steps": max_steps,
                        "session_id": session_id,
                        "memory_context": memory_context,
                        "cross_session_insights": cross_session_insights,
                        "planning_mode": "traditional" if not initial_plan else "planned"
                    }
                    
                    action_result = await self.client.generate_enhanced_reasoning(
                        task_description=task.description,
                        available_tools=available_tool_ids,  # 添加已注册工具ID列表
                        tool_descriptions=available_tools_description,  # 详细工具描述
                        previous_steps=serializable_steps,
                        execution_context=enhanced_execution_context  # 包含记忆上下文的执行上下文
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
                        interaction = LLMInteraction()
                        interaction.provider = self.client.provider.value if hasattr(self.client.provider, 'value') else str(self.client.provider)
                        interaction.model = getattr(self.client, 'model', 'unknown')
                        interaction.context = f"step_{step_id}_complete_task_summary"
                        interaction.prompt = prompt
                        interaction.prompt_length = len(prompt)
                        interaction.prompt_type = "complete_task_summary"
                        interaction.response = response
                        interaction.response_length = len(response)
                        interaction.response_time = time.time() - interaction_start
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
                elif action == 'request_tool_capability' or (tool_id and tool_id in ['mcp-search-tool'] and action in ['analyze_tool_needs', 'search_and_install_tools']):
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
                    execution_start_time = time.time()
                    capability_result = await self.toolscore_client.request_tool_capability(
                        task_description=task_desc,
                        required_capabilities=required_caps,
                        auto_install=True
                    )
                    execution_duration = time.time() - execution_start_time
                    
                    if capability_result.get("success"):
                        # 工具安装成功
                        installed_tools = capability_result.get("installed_tools", [])
                        processing_time = capability_result.get("processing_time_ms", 0)
                        
                        if installed_tools:
                            tool_names = [tool.get("name", tool.get("tool_id", "unknown")) for tool in installed_tools]
                            observation = f"成功安装了 {len(installed_tools)} 个新工具: {', '.join(tool_names)}。处理时间: {processing_time}ms。新工具现在可以使用。"
                            result_summary = f"安装了工具: {', '.join(tool_names)}"
                            
                            # 注册等待新工具的回调
                            await self.real_time_client.register_pending_request(
                                request_id=f"{trajectory_id}-step-{step_id}",
                                required_capabilities=required_caps,
                                callback=self._create_tool_available_callback(trajectory_id, step_id)
                            )
                            
                            # 更新工具列表
                            available_tool_ids = await self.toolscore_client.get_available_tools()
                            available_tools_description = await self.real_time_client.get_fresh_tools_for_llm(
                                fallback_client=self.toolscore_client
                            )
                        else:
                            observation = "工具安装请求已处理，但未安装新工具。现有工具可能已满足需求。"
                            result_summary = "未安装新工具"
                        
                        tool_success = True
                    else:
                        # 工具安装失败
                        error_msg = capability_result.get("message", "未知错误")
                        observation = f"工具能力请求失败: {error_msg}"
                        tool_success = False
                        current_attempt_err_type = ErrorType.TOOL_ERROR
                        current_attempt_err_msg = error_msg
                        result_summary = f"失败: {error_msg}"
                    
                    # 🔧 记录工具使用 - mcp-search-tool via capability request
                    tool_tracker.record_tool_usage(
                        tool_server_id='mcp-search-tool',
                        action=action if action != 'request_tool_capability' else 'analyze_tool_needs',
                        parameters={
                            "task_description": task_desc,
                            "required_capabilities": required_caps,
                            "reason": reason
                        },
                        result=result_summary,
                        success=tool_success,
                        duration=execution_duration
                    )
                
                # 🔍 新增：处理mcp-search-tool的调用
                elif tool_id == 'mcp-search-tool' or action in ['search_and_install_tools', 'analyze_tool_needs']:
                    logger.info(f"🛠️ 检测到mcp-search-tool调用: action={action}")
                    
                    try:
                        execution_start_time = time.time()
                        # 🔍 通过ToolScore API调用mcp-search-tool
                        if action == 'analyze_tool_needs':
                            # 分析工具需求
                            task_desc = params.get('task_description', task.description)
                            
                            # 调用ToolScore的工具分析API
                            analysis_result = await self.toolscore_client.analyze_tool_needs(
                                task_description=task_desc
                            )
                            execution_duration = time.time() - execution_start_time
                            
                            if analysis_result.get("success"):
                                analysis = analysis_result.get("analysis", {})
                                needed_tools = analysis.get("needed_tools", [])
                                recommendations = analysis.get("recommendations", "")
                                
                                observation = f"工具需求分析完成。需要的工具类型: {', '.join(needed_tools)}。建议: {recommendations}"
                                tool_success = True
                                result_summary = f"需要工具: {', '.join(needed_tools)}"
                            else:
                                error_msg = analysis_result.get("message", "分析失败")
                                observation = f"工具需求分析失败: {error_msg}"
                                tool_success = False
                                result_summary = f"分析失败: {error_msg}"
                            
                            # 🔧 记录工具使用
                            tool_tracker.record_tool_usage(
                                tool_server_id='mcp-search-tool',
                                action=action,
                                parameters={"task_description": task_desc},
                                result=result_summary,
                                success=tool_success,
                                duration=execution_duration
                            )
                                
                        elif action == 'search_and_install_tools':
                            # 搜索并安装工具
                            task_desc = params.get('task_description', task.description)
                            reason = params.get('reason', '')
                            
                            # 调用ToolScore的工具搜索和安装API
                            search_result = await self.toolscore_client.search_and_install_tools(
                                task_description=task_desc,
                                reason=reason
                            )
                            execution_duration = time.time() - execution_start_time
                            
                            if search_result.get("success"):
                                installed_tools = search_result.get("installed_tools", [])
                                
                                if installed_tools:
                                    tool_names = [tool.get("name", tool.get("tool_id", "unknown")) for tool in installed_tools]
                                    observation = f"成功搜索并安装了 {len(installed_tools)} 个新工具: {', '.join(tool_names)}。"
                                    result_summary = f"安装了工具: {', '.join(tool_names)}"
                                    
                                    # 更新可用工具描述
                                    try:
                                        available_tools_description = await self.real_time_client.get_fresh_tools_for_llm(
                                            fallback_client=self.toolscore_client
                                        )
                                        # 🔧 更新工具跟踪器的可用工具信息
                                        tool_tracker.set_available_tools(available_tools_description)
                                        logger.info("✅ 已更新可用工具列表")
                                    except Exception as e:
                                        logger.warning(f"更新工具列表失败: {e}")
                                else:
                                    observation = "搜索完成，但未找到合适的新工具。"
                                    result_summary = "未找到合适的新工具"
                                
                                tool_success = True
                            else:
                                error_msg = search_result.get("message", "搜索失败")
                                observation = f"工具搜索失败: {error_msg}"
                                tool_success = False
                                result_summary = f"搜索失败: {error_msg}"
                            
                            # 🔧 记录工具使用
                            tool_tracker.record_tool_usage(
                                tool_server_id='mcp-search-tool',
                                action=action,
                                parameters={"task_description": task_desc, "reason": reason},
                                result=result_summary,
                                success=tool_success,
                                duration=execution_duration
                            )
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
                        
                        # 🔧 即使异常也要记录工具使用
                        execution_duration = time.time() - execution_start_time if 'execution_start_time' in locals() else 0.0
                        tool_tracker.record_tool_usage(
                            tool_server_id='mcp-search-tool',
                            action=action if 'action' in locals() else 'unknown',
                            parameters=params if 'params' in locals() else {},
                            result=f"异常: {str(e)}",
                            success=False,
                            duration=execution_duration
                        )

                # 常规工具调用
                elif tool_id and action:
                    logger.info(f"🔧 执行工具调用: tool_id={tool_id}, action={action}")
                    logger.debug(f"Attempt {attempt + 1}: Executing action '{action}' with tool_id '{tool_id}'")
                    
                    # 清理参数
                    cleaned_params = {k: v for k, v in params.items()
                                    if k not in ['action', 'tool_id', 'tool']}

                    # 优先尝试直接通过MCP客户端调用 python-executor-mcp-server
                    # 🔍 统一通过ToolScore HTTP API执行所有工具
                    try:
                        logger.info(f"🌐 通过ToolScore HTTP API执行工具: {tool_id}/{action}")
                        
                        execution_start_time = time.time()
                        execution_result = await self.toolscore_client.execute_tool(
                            tool_id=tool_id,
                            action=action,
                            parameters=cleaned_params
                        )
                        execution_duration = time.time() - execution_start_time
                        
                        tool_success = execution_result.get('success', False)
                        
                        if tool_success:
                            result_data = execution_result.get('result', {})
                            if tool_id == 'python-executor-mcp-server' and isinstance(result_data, dict):
                                stdout = result_data.get('stdout', '').strip()
                                if stdout:
                                    observation = f"Python代码执行成功。输出:\n{stdout[:200]}{'...' if len(stdout) > 200 else ''}"
                                    current_outputs.append(stdout)
                                    result_summary = stdout
                                else:
                                    observation = "Python代码执行成功，无输出。"
                                    result_summary = "无输出"
                            else:
                                observation = f"工具执行成功: {str(result_data)[:200]}{'...' if len(str(result_data)) > 200 else ''}"
                                current_outputs.append(str(result_data))
                                result_summary = str(result_data)
                        else:
                            error_msg = execution_result.get('error', 'Unknown error')
                            observation = f"工具执行失败: {error_msg}"
                            current_attempt_err_type = ErrorType.TOOL_ERROR
                            current_attempt_err_msg = error_msg
                            result_summary = f"错误: {error_msg}"
                        
                        # 🔧 记录工具使用
                        tool_tracker.record_tool_usage(
                            tool_server_id=tool_id,
                            action=action,
                            parameters=cleaned_params,
                            result=result_summary,
                            success=tool_success,
                            duration=execution_duration
                        )
                        
                        logger.info(f"✅ 工具执行完成: {tool_id}, 成功: {tool_success}")
                    
                    except Exception as e:
                        logger.error(f"工具执行异常: {e}")
                        tool_success = False
                        current_attempt_err_type = ErrorType.TOOL_ERROR
                        current_attempt_err_msg = str(e)
                        observation = f"工具执行失败: {str(e)}"

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

            step = ExecutionStep(
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
            )
            steps.append(step)
            
            # === 记忆存储：将执行步骤存储到记忆管理器 ===
            try:
                await self.memory_manager.store_conversation_step(
                    task_id=trajectory_id,
                    session_id=session_id,
                    user_input=f"步骤{step_id}: {action} ({tool_id})",
                    agent_output=observation,
                    thinking_summary=thinking,
                    tools_used=[tool_id] if tool_id else [],
                    success=tool_success,
                    error_message=current_attempt_err_msg,
                    metadata={
                        "step_id": step_id,
                        "action": action,
                        "tool_id": tool_id,
                        "duration": duration,
                        "execution_code": execution_code
                    }
                )
                logger.debug(f"💾 步骤 {step_id} 已存储到记忆管理器")
            except Exception as memory_err:
                logger.warning(f"记忆存储失败: {memory_err}")

            # 检查是否完成 - 也需要记录LLM交互
            completion_interactions = []
            original_call_api = self.client._call_api
            async def wrapped_call_api_for_completion(prompt: str) -> str:
                interaction_start = time.time()
                response = await original_call_api(prompt)
                
                from core.interfaces import LLMInteraction
                interaction = LLMInteraction()
                interaction.provider = self.client.provider.value if hasattr(self.client.provider, 'value') else str(self.client.provider)
                interaction.model = getattr(self.client, 'model', 'unknown')
                interaction.context = f"step_{step_id}_completion_check"
                interaction.prompt = prompt
                interaction.prompt_length = len(prompt)
                interaction.prompt_type = "completion_check"
                interaction.response = response
                interaction.response_length = len(response)
                interaction.response_time = time.time() - interaction_start
                completion_interactions.append(interaction)
                return response
            
            self.client._call_api = wrapped_call_api_for_completion
            try:
                # === 智能完成检查：优先使用StepPlanner ===
                completion_result = {"completed": False, "reason": ""}
                
                if initial_plan:
                    # 使用步骤规划器检查完成状态
                    try:
                        planner_completed, planner_reason = await self.step_planner.check_completion(
                            task, steps, current_outputs
                        )
                        completion_result = {"completed": planner_completed, "reason": planner_reason}
                        logger.debug(f"🎯 步骤规划器完成检查: {planner_completed}, 原因: {planner_reason}")
                    except Exception as planner_err:
                        logger.warning(f"步骤规划器完成检查失败: {planner_err}")
                
                # === 后备完成检查：使用传统LLM方式 ===
                if not completion_result["completed"]:
                    completion = await self.client.check_task_completion(
                        task.description,
                        [s.__dict__ for s in steps],
                        current_outputs
                    )
                    completion_result = completion
                    
            finally:
                self.client._call_api = original_call_api
            
            # 将完成检查的LLM交互添加到当前步骤
            if completion_interactions:
                steps[-1].llm_interactions.extend(completion_interactions)
            
            if completion_result.get('completed'):
                success = True
                logger.info(f"✅ 任务完成: {completion_result.get('reason', '检查通过')}")
                break
        
        # 改进的任务完成判断逻辑
        if not success and steps:
            # 检查是否所有步骤都成功，特别是工具执行步骤
            successful_steps = [s for s in steps if s.success]
            tool_execution_steps = [s for s in steps if s.action_type == ActionType.TOOL_CALL and s.step_id > 1]  # 排除第一步的工具暴露
            successful_tool_steps = [s for s in tool_execution_steps if s.success]
            
            # 检查是否有工具成功执行并产生了输出
            has_successful_computation = False
            has_completion_confirmation = False
            
            for step in steps:
                # 检查是否有成功的数学计算
                if (step.success and step.observation and 
                    ('128255625' in step.observation or '计算正确' in step.observation or '执行成功' in step.observation)):
                    has_successful_computation = True
                
                # 检查LLM是否确认任务完成
                if hasattr(step, 'llm_interactions') and step.llm_interactions:
                    for interaction in step.llm_interactions:
                        if (interaction.response and 
                            ('任务已完成' in interaction.response or '任务完成' in interaction.response or 
                             'completed' in interaction.response.lower() or '成功完成' in interaction.response)):
                            has_completion_confirmation = True
            
            # 改进的成功判断条件
            success_criteria_met = (
                # 条件1：大部分步骤成功
                len(successful_steps) >= len(steps) * 0.7 and
                # 条件2：有成功的工具执行 OR 有成功的计算结果
                (len(successful_tool_steps) > 0 or has_successful_computation) and
                # 条件3：没有严重错误
                all(step.error_type != ErrorType.SYSTEM_ERROR for step in steps)
            )
            
            if success_criteria_met:
                logger.info(f"任务被重新评估为成功：{len(successful_steps)}/{len(steps)}步成功，{len(successful_tool_steps)}个工具步骤成功，计算成功={has_successful_computation}")
                success = True
            else:
                # 只有在真正失败时才设置错误
                final_trajectory_error_type = steps[-1].error_type or ErrorType.EXECUTION_FAILED
                final_trajectory_error_message = steps[-1].error_message or f"Task failed after {len(steps)} steps"
                logger.warning(f"Task execution completed without success: {final_trajectory_error_message}")
                logger.info(f"失败原因分析：成功步骤{len(successful_steps)}/{len(steps)}，工具步骤{len(successful_tool_steps)}/{len(tool_execution_steps)}，计算成功={has_successful_computation}")

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
                        interaction = LLMInteraction()
                        interaction.provider = self.client.provider.value if hasattr(self.client.provider, 'value') else str(self.client.provider)
                        interaction.model = getattr(self.client, 'model', 'unknown')
                        interaction.context = "final_task_summary"
                        interaction.prompt = prompt
                        interaction.prompt_length = len(prompt)
                        interaction.prompt_type = "task_summary"
                        interaction.response = response
                        interaction.response_length = len(response)
                        interaction.response_time = time.time() - interaction_start
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
                'original_task_id': task.task_id,
                # 🔧 添加工具使用统计
                'tool_usage_stats': tool_tracker.get_usage_statistics()
            },
            # 🔧 新增：工具使用跟踪信息
            available_tools=tool_tracker.get_available_tools_summary(),
            used_tools=tool_tracker.get_used_tools_summary()
        )
        
        # 🔍 应用轨迹增强 - 添加详细元数据
        enhanced_trajectory = self.trajectory_enhancer.enhance_trajectory(trajectory)
        
        # 保存轨迹
        await self._save_trajectory(enhanced_trajectory)
        
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
        
        # === 会话总结：保存会话摘要到记忆管理器 ===
        try:
            # 提取主要话题和洞察
            main_topics = [task.description]
            key_insights = []
            
            if success:
                key_insights.append(f"任务成功完成，共执行{len(steps)}步，耗时{total_duration:.2f}秒")
                if tool_tracker:
                    used_tools = tool_tracker.get_used_tools_summary()
                    if used_tools:
                        key_insights.append(f"主要使用工具: {', '.join(used_tools[:3])}")
            else:
                key_insights.append(f"任务执行失败: {final_trajectory_error_message}")
            
            await self.memory_manager.store_session_summary(
                session_id=session_id,
                main_topics=main_topics,
                key_insights=key_insights
            )
            logger.debug(f"💾 会话摘要已保存: {session_id}")
        except Exception as session_err:
            logger.warning(f"保存会话摘要失败: {session_err}")
        
        return trajectory
    
    def _should_skip_failed_operation(self, operation_key: str, tool_id: str, action: str, params: Dict[str, Any]) -> bool:
        """检查是否应该跳过重复失败的操作"""
        # 检查工具调用失败历史
        if operation_key in self.failure_history.get('tool_calls', {}):
            failure_count = self.failure_history['tool_calls'][operation_key].get('count', 0)
            if failure_count >= 2:  # 连续失败2次就跳过
                return True
        
        # 检查特定的工具安装失败
        if action in ['search_and_install_tools', 'request_tool_capability']:
            task_desc = params.get('task_description', '')
            search_key = f"{action}:{hash(task_desc)}"
            if search_key in self.failure_history.get('search_queries', set()):
                return True
                
        return False
    
    def _record_failed_operation(self, category: str, operation_key: str, error_msg: str):
        """记录失败的操作"""
        if category == 'tool_calls':
            if operation_key not in self.failure_history['tool_calls']:
                self.failure_history['tool_calls'][operation_key] = {'count': 0, 'errors': []}
            
            self.failure_history['tool_calls'][operation_key]['count'] += 1
            self.failure_history['tool_calls'][operation_key]['errors'].append(error_msg)
            
        elif category == 'search_queries':
            self.failure_history['search_queries'].add(operation_key)
            
        elif category == 'tool_installations':
            self.failure_history['tool_installations'].add(operation_key)
            
        logger.debug(f"📈 记录失败操作: {category}/{operation_key}")
    
    def _create_tool_available_callback(self, trajectory_id: str, step_id: int):
        """创建工具可用时的回调函数（不接受参数）"""
        async def callback(): # 不接受任何参数
            # 这个回调只是一个触发器，实际的工具事件处理在 _on_new_tool_available 中进行
            logger.info(f"🎉 任务 {trajectory_id} 步骤 {step_id}: 检测到新工具可用，正在检查...")
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
    def _format_trajectory_for_readable_output(self, trajectory: TrajectoryResult) -> Dict[str, Any]:
        """格式化轨迹数据以提高可读性"""
        trajectory_dict = trajectory.to_dict()
        
        # 格式化steps，添加换行以提高可读性
        formatted_steps = []
        for step in trajectory_dict['steps']:
            formatted_step = {
                'step_id': step['step_id'],
                'action_type': step['action_type'],
                'success': step['success']
            }
            
            # 格式化tool_input - 添加换行使其更易读
            if step.get('tool_input'):
                formatted_step['tool_input'] = step['tool_input']
            
            # 格式化tool_output - 添加换行使其更易读
            if step.get('tool_output'):
                output = step['tool_output']
                if len(output) > 100:
                    # 长输出添加换行
                    formatted_step['tool_output'] = output
                else:
                    formatted_step['tool_output'] = output
            
            # 添加其他重要字段
            if step.get('thinking'):
                formatted_step['thinking'] = step['thinking']
            if step.get('execution_code'):
                formatted_step['execution_code'] = step['execution_code']
            if step.get('error_type'):
                formatted_step['error_type'] = step['error_type']
            if step.get('error_message'):
                formatted_step['error_message'] = step['error_message']
            if step.get('duration'):
                formatted_step['duration'] = round(step['duration'], 3)
                
            formatted_steps.append(formatted_step)
        
        # 创建格式化的轨迹字典
        formatted_trajectory = {
            'task_id': trajectory_dict['task_id'],
            'task_name': trajectory_dict['task_name'],
            'task_description': trajectory_dict['task_description'],
            'runtime_id': trajectory_dict['runtime_id'],
            'success': trajectory_dict['success'],
            'steps': formatted_steps,
            'final_result': trajectory_dict['final_result'],
            'error_type': trajectory_dict['error_type'],
            'error_message': trajectory_dict['error_message'],
            'total_duration': round(trajectory_dict['total_duration'], 3),
            'metadata': trajectory_dict['metadata'],
            'created_at': trajectory_dict['created_at'],
            'available_tools': trajectory_dict['available_tools'],
            'used_tools': trajectory_dict['used_tools']
        }
        
        return formatted_trajectory

    async def _save_trajectory(self, trajectory: TrajectoryResult):
        """保存轨迹到文件"""
        out_dir = get_trajectories_dir()
        
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
        
        # 使用格式化的轨迹数据
        formatted_trajectory = self._format_trajectory_for_readable_output(trajectory)
        trajectories.append(formatted_trajectory)
        
        with open(collection_file, 'w', encoding='utf-8') as f:
            json.dump(trajectories, f, ensure_ascii=False, indent=2)
        
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

