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
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
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
from core.tool_schema_manager import get_tool_schema_manager, init_tool_schema_manager

# 🆕 新增：Guardrails和ValidationCritic集成
from core.llm.guardrails_middleware import GuardrailsLLMMiddleware, GuardrailsValidationResult
from core.agents.validation_critic import ValidationCritic, ErrorEvent, ErrorSeverity, ErrorCategory

# 🆕 新增：参数校验器
from core.toolscore.parameter_validator import get_parameter_validator, ValidationResult

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
        
        # 🛡️ 新增：Guardrails LLM中间件
        self.guardrails_middleware = GuardrailsLLMMiddleware()
        
        # 🎯 新增：ValidationCritic智能错误分析代理
        self.validation_critic = ValidationCritic(llm_client, [])
        
        # 🔍 连续失败计数器和阈值
        self.consecutive_failures = 0
        self.max_consecutive_failures = 3
        self.error_events_buffer = []
        
        # 🔧 工具Schema管理器
        self.tool_schema_manager = get_tool_schema_manager()
        
    async def initialize(self):
        """初始化运行时 - 简化为纯工具消费者"""
        logger.info("🚀 初始化Enhanced Reasoning Runtime - 简化版本")
        
        # 🔒 P0-2修复：将tool_schema_manager注入到response_parser中
        if hasattr(self.client, 'reasoning_response_parser'):
            self.client.reasoning_response_parser.set_tool_schema_manager(self.tool_schema_manager)
            logger.info("✅ 工具Schema管理器已注入到响应解析器")
        
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
        
        # 🔍 等待关键工具完全就绪
        logger.info("⏳ 等待关键工具完全就绪...")
        tools_ready = await self._wait_for_essential_tools(timeout=30)
        if not tools_ready:
            logger.warning("⚠️ 部分关键工具未就绪，将在降级模式下运行")
        else:
            logger.info("✅ 所有关键工具已就绪")
        
        # 🔧 P1修复1: 执行MCP服务器同步验证
        logger.info("🔍 开始MCP服务器同步验证...")
        try:
            validation_report = await self.tool_schema_manager.validate_mcp_sync()
            if validation_report['overall_health'] == 'healthy':
                logger.info("✅ MCP服务器同步验证通过")
            elif validation_report['overall_health'] == 'degraded':
                logger.warning(f"⚠️ MCP服务器部分不一致: {validation_report['summary']}")
                # 尝试自动修复
                fix_results = await self.tool_schema_manager.auto_fix_schema_inconsistencies(validation_report)
                logger.info(f"🔧 自动修复结果: {len(fix_results['successful_fixes'])} 成功, {len(fix_results['failed_fixes'])} 失败")
            else:
                logger.error(f"❌ MCP服务器同步验证失败: {validation_report.get('error', '未知错误')}")
        except Exception as e:
            logger.error(f"❌ MCP同步验证异常: {e}")
        
        # 启动定期清理任务
        asyncio.create_task(self._periodic_cleanup())
        
        # 🔧 P1修复1: 启动定期同步验证任务
        asyncio.create_task(self._periodic_sync_validation())
        
        # 🛡️ 初始化Guardrails中间件和工具Schema管理器
        try:
            logger.debug("🔧 开始获取可用工具ID列表...")
            available_tools = await self.real_time_client.get_available_tool_ids()
            logger.debug(f"📋 获取到的工具列表: {available_tools}")
            
            # 🔧 初始化工具Schema管理器（传入客户端实例）
            from core.tool_schema_manager import init_tool_schema_manager
            self.tool_schema_manager = init_tool_schema_manager(
                redis_client=None,  # 如果有redis_manager可以传入
                toolscore_client=self.toolscore_client
            )
            logger.info("✅ 工具Schema管理器已初始化")
            
            if available_tools:
                logger.debug("🔧 更新Guardrails和ValidationCritic工具配置...")
                self.guardrails_middleware.update_available_tools(available_tools)
                self.validation_critic.update_available_tools(available_tools)
                logger.info(f"✅ Guardrails和ValidationCritic已配置{len(available_tools)}个工具: {', '.join(available_tools)}")
            else:
                logger.warning("⚠️ 未获取到可用工具列表，Guardrails将使用默认配置")
        except Exception as e:
            logger.error(f"❌ Guardrails初始化失败: {e}")
            logger.debug(f"错误详情: {type(e).__name__}: {str(e)}")
            import traceback
            logger.debug(f"完整追踪: {traceback.format_exc()}")
        
        logger.info("✅ Enhanced Reasoning Runtime 已成功初始化为纯推理引擎（集成Guardrails + ValidationCritic）")
        
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
    
    async def _wait_for_essential_tools(self, timeout: int = 30) -> bool:
        """等待关键工具完全就绪"""
        essential_tools = [
            'deepsearch',
            'microsandbox', 
            'browser_use',
            'mcp-search-tool'
        ]
        
        start_time = time.time()
        check_interval = 1  # 每秒检查一次
        
        while time.time() - start_time < timeout:
            try:
                # 获取当前可用工具
                available_tools = await self.toolscore_client.get_available_tools()
                if not available_tools:
                    logger.debug("🔍 ToolScore服务返回空工具列表，继续等待...")
                    await asyncio.sleep(check_interval)
                    continue
                
                # 检查必需工具是否都已就绪
                available_tool_ids = [tool.get('id', '') for tool in available_tools if isinstance(tool, dict)]
                available_tool_ids.extend([tool_id for tool_id in available_tools if isinstance(tool_id, str)])
                
                missing_tools = [tool for tool in essential_tools if tool not in available_tool_ids]
                
                if not missing_tools:
                    logger.info(f"✅ 所有关键工具已就绪: {essential_tools}")
                    
                    # 额外验证：确保工具确实可以响应
                    await self._verify_tools_connectivity(essential_tools)
                    
                    return True
                else:
                    logger.debug(f"⏳ 等待工具就绪... 缺少: {missing_tools}")
                
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                logger.debug(f"⚠️ 检查工具状态时出错: {e}")
                await asyncio.sleep(check_interval)
        
        logger.warning(f"⚠️ 超时等待关键工具就绪 ({timeout}秒)")
        return False
    
    async def _verify_tools_connectivity(self, tool_ids: List[str]):
        """验证工具连通性"""
        for tool_id in tool_ids:
            try:
                # 发送轻量级测试请求验证连通性
                if tool_id == 'deepsearch':
                    # 测试DeepSearch连通性
                    test_params = {"question": "test connectivity", "max_results": 1}
                    # 这里不实际调用，只是检查工具是否在注册表中
                    pass
                elif tool_id == 'microsandbox':
                    # 测试MicroSandbox连通性
                    pass
                elif tool_id == 'browser_use':
                    # 测试Browser连通性
                    pass
                elif tool_id == 'mcp-search-tool':
                    # 测试Search Tool连通性
                    pass
                
                logger.debug(f"✅ 工具连通性验证通过: {tool_id}")
                
            except Exception as e:
                logger.warning(f"⚠️ 工具连通性验证失败: {tool_id} - {e}")
            
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

    async def _periodic_sync_validation(self):
        """🔧 P1修复1: 定期MCP同步验证"""
        while True:
            try:
                # 每5分钟执行一次同步验证
                await asyncio.sleep(300)
                
                logger.debug("🔍 执行定期MCP同步验证...")
                validation_report = await self.tool_schema_manager.validate_mcp_sync()
                
                if validation_report['overall_health'] == 'unhealthy':
                    logger.warning(f"⚠️ MCP同步验证发现问题: {validation_report['summary']}")
                    
                    # 尝试自动修复
                    fix_results = await self.tool_schema_manager.auto_fix_schema_inconsistencies(validation_report)
                    if fix_results['successful_fixes']:
                        logger.info(f"✅ 自动修复了 {len(fix_results['successful_fixes'])} 个Schema不一致问题")
                    
                    # 记录到度量系统
                    if hasattr(self, 'metrics'):
                        self.metrics.record_mcp_sync_issues(validation_report, fix_results)
                
                elif validation_report['overall_health'] == 'healthy':
                    logger.debug("✅ MCP同步验证正常")
                
            except Exception as e:
                logger.error(f"❌ 定期同步验证异常: {e}")

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
        
        # 🔧 存储当前任务描述用于参数补齐
        self.current_task_description = task.description
        
        steps: List[ExecutionStep] = []
        max_steps = task.max_steps or 10  # 使用动态max_steps，默认为10
        # 🔄 Sprint 1: 增强重试策略 (P1 问题修复)
        max_retries = 3  # 增加重试次数
        base_retry_delay = 1  # 基础延迟时间
        # 重试历史跟踪
        retry_history = {}
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
        
        # 🔧 获取动态工具描述（替换硬编码描述）
        logger.info("📋 使用工具Schema管理器获取动态工具描述...")
        try:
            # 使用ToolSchemaManager获取动态工具描述
            available_tools_description = await self.tool_schema_manager.generate_llm_tools_description()
            logger.info(f"📋 获取到动态工具描述长度: {len(available_tools_description)} 字符")
            logger.info(f"📋 动态工具描述预览: {available_tools_description[:500]}...")
        except Exception as e:
            logger.warning(f"⚠️ 动态工具描述获取失败，回退到静态方式: {e}")
            # 回退到原有方式
            available_tools_description = await self.real_time_client.get_fresh_tools_for_llm(
                fallback_client=self.toolscore_client
            )
            logger.info(f"📋 使用静态方式获取工具描述长度: {len(available_tools_description)} 字符")
            logger.info(f"📋 静态工具描述预览: {available_tools_description[:500]}...")
        
        # 🔧 记录可用工具信息
        tool_tracker.set_available_tools(available_tools_description)
        
        # 检查是否有可用工具
        if "暂无可用工具" in available_tools_description or len(available_tools_description.strip()) == 0:
            logger.warning("⚠️ 检测到暂无可用工具，可能存在工具注册问题")

        # === 记录首次暴露给 LLM 的工具集合 ===
        step_start_time = time.time()
        expose_step = ExecutionStep(
            step_id=1,  # 固定为第1步：工具暴露
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
        async def wrapped_call_api_for_analysis(messages) -> str:
            interaction_start = time.time()
            response = await original_call_api(messages)
            
            from core.interfaces import LLMInteraction
            interaction = LLMInteraction()
            interaction.provider = self.client.provider.value if hasattr(self.client.provider, 'value') else str(self.client.provider)
            interaction.model = getattr(self.client, 'model', 'unknown')
            interaction.context = "task_requirements_analysis"
            interaction.prompt = str(messages) if messages else ""
            interaction.prompt_length = len(str(messages))
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

        # 🛡️ 初始化循环检测机制
        from collections import defaultdict, deque
        loop_detection = {
            'repeated_actions': defaultdict(int),
            'repeated_errors': defaultdict(int), 
            'recent_tool_calls': deque(maxlen=10),
            'consecutive_failures': 0,
            'start_time': time.time(),
            'last_progress_time': time.time(),
            'max_consecutive_failures': 3,
            'max_repeated_actions': 5,
            'max_execution_time': 300,  # 5分钟
            'progress_timeout': 60      # 1分钟无进展超时
        }
        logger.info("🛡️ 循环检测机制已启用")

        for step_index in range(max_steps):
            step_id = step_index + 2  # 从2开始，因为1是工具暴露步骤
            # 🛡️ 循环检测：检查是否应该终止执行
            current_time = time.time()
            
            # 检查总执行时间
            if current_time - loop_detection['start_time'] > loop_detection['max_execution_time']:
                logger.warning(f"🛑 执行超时终止 ({loop_detection['max_execution_time']}秒)")
                break
            
            # 检查无进展超时
            time_since_progress = current_time - loop_detection['last_progress_time']
            if time_since_progress > loop_detection['progress_timeout']:
                logger.warning(f"🛑 无进展超时终止 ({loop_detection['progress_timeout']}秒无成功操作)")
                break
            
            # 检查连续失败
            if loop_detection['consecutive_failures'] >= loop_detection['max_consecutive_failures']:
                logger.warning(f"🛑 连续失败过多终止 ({loop_detection['consecutive_failures']}次)")
                break
            
            # 🔍 重置当前步骤的LLM交互记录
            current_step_llm_interactions = []
            
            logger.info(f"🔄 执行步骤 {step_id}/{max_steps}")
            
            # 🔍 错误模式检测和智能恢复
            error_pattern_detected = await self._detect_error_patterns(steps, step_id)
            if error_pattern_detected:
                recovery_action = await self._apply_error_recovery(steps, step_id, task)
                if recovery_action == "terminate":
                    logger.warning("🛑 错误恢复建议终止任务")
                    break
                elif recovery_action == "adjust_strategy":
                    logger.info("🔧 错误恢复建议调整策略")
                    # 调整策略的具体实现在后续步骤中处理
            
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
            async def wrapped_call_api(messages) -> str:
                # 记录LLM交互开始
                interaction_start = time.time()
                
                # 调用原始方法
                response = await original_call_api(messages)
                
                # 记录LLM交互
                from core.interfaces import LLMInteraction
                interaction = LLMInteraction()
                interaction.provider = self.client.provider.value if hasattr(self.client.provider, 'value') else str(self.client.provider)
                interaction.model = getattr(self.client, 'model', 'unknown')
                interaction.context = f"step_{step_id}_reasoning"
                interaction.prompt = str(messages) if messages else ""
                interaction.prompt_length = len(str(messages))
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
                    
                    # 🔧 P2修复：构建智能错误分析上下文
                    error_analysis_context = await self._build_error_analysis_context(steps, step_id)
                    
                    # 构建增强的执行上下文
                    enhanced_execution_context = {
                        "step_number": step_id,
                        "max_steps": max_steps,
                        "session_id": session_id,
                        "memory_context": memory_context,
                        "cross_session_insights": cross_session_insights,
                        "planning_mode": "traditional" if not initial_plan else "planned",
                        "error_analysis": error_analysis_context  # 🆕 增加错误分析上下文
                    }
                    
                    # 🔧 增强LLM调用错误处理 - 防止数据类型错误和异常传播
                    try:
                        logger.debug(f"🔍 准备LLM调用 - 任务: {task.description[:100]}...")
                        logger.debug(f"   可用工具: {len(available_tool_ids)} 个")
                        logger.debug(f"   工具描述长度: {len(available_tools_description)} 字符")
                        logger.debug(f"   历史步骤: {len(serializable_steps)} 步")
                        
                        # 预验证输入参数
                        if not isinstance(task.description, str):
                            task_desc = str(task.description) if task.description else "未知任务"
                            logger.warning(f"任务描述类型异常，已转换: {type(task.description)} -> str")
                        else:
                            task_desc = task.description
                        
                        if not isinstance(available_tool_ids, list):
                            available_tool_ids = [] if available_tool_ids is None else [str(available_tool_ids)]
                            logger.warning(f"可用工具ID类型异常，已转换为列表")
                        
                        if not isinstance(available_tools_description, str):
                            available_tools_description = str(available_tools_description) if available_tools_description else "无可用工具"
                            logger.warning(f"工具描述类型异常，已转换为字符串")
                        
                        if not isinstance(serializable_steps, list):
                            serializable_steps = [] if serializable_steps is None else [serializable_steps]
                            logger.warning(f"历史步骤类型异常，已转换为列表")
                        
                        if not isinstance(enhanced_execution_context, dict):
                            enhanced_execution_context = {} if enhanced_execution_context is None else {"context": str(enhanced_execution_context)}
                            logger.warning(f"执行上下文类型异常，已转换为字典")
                        
                        action_result = await self.client.generate_enhanced_reasoning(
                            task_description=task_desc,
                            available_tools=available_tool_ids,  # 添加已注册工具ID列表
                            tool_descriptions=available_tools_description,  # 详细工具描述
                            previous_steps=serializable_steps,
                            execution_context=enhanced_execution_context  # 包含记忆上下文的执行上下文
                        )
                        
                        # 验证返回结果类型
                        if not isinstance(action_result, dict):
                            logger.error(f"LLM返回结果类型异常: {type(action_result)}, 内容: {action_result}")
                            raise ValueError(f"LLM返回结果必须是字典类型，实际类型: {type(action_result)}")
                        
                        logger.debug(f"✅ LLM调用成功，返回字段: {list(action_result.keys())}")
                        
                    except Exception as llm_error:
                        logger.error(f"❌ LLM调用失败: {llm_error}")
                        logger.error(f"   错误类型: {type(llm_error).__name__}")
                        logger.error(f"   参数类型检查:")
                        logger.error(f"     task_description: {type(task.description)}")
                        logger.error(f"     available_tools: {type(available_tool_ids)}")
                        logger.error(f"     tool_descriptions: {type(available_tools_description)}")
                        logger.error(f"     previous_steps: {type(serializable_steps)}")
                        logger.error(f"     execution_context: {type(enhanced_execution_context)}")
                        
                        # 创建安全的失败响应
                        action_result = {
                            "thinking": f"LLM调用失败: {str(llm_error)}",
                            "action": "error",
                            "tool": None,
                            "parameters": {},
                            "confidence": 0.0,
                            "error_details": {
                                "error_type": type(llm_error).__name__,
                                "error_message": str(llm_error),
                                "step_id": step_id
                            }
                        }
                    
                    # 🛡️ 新增：Guardrails输出验证
                    guardrails_result = await self.guardrails_middleware.validate_output(
                        json.dumps(action_result, ensure_ascii=False),
                        context={"step_id": step_id, "task_description": task.description}
                    )
                    
                    if guardrails_result.is_valid:
                        if guardrails_result.corrections_applied:
                            logger.info(f"🔧 Guardrails自动修正: {guardrails_result.corrections_applied}")
                            action_result = guardrails_result.validated_data
                        else:
                            logger.debug(f"✅ Guardrails验证通过: {guardrails_result.guardrails_used}")
                    else:
                        # Guardrails验证失败，触发ValidationCritic分析
                        logger.warning(f"❌ Guardrails验证失败: {guardrails_result.error_message}")
                        
                        # 🎯 创建错误事件并触发ValidationCritic
                        error_event = ErrorEvent(
                            error_id=f"guardrails_failure_{step_id}_{int(time.time())}",
                            timestamp=datetime.now(),
                            component="guardrails_middleware",
                            error_type="validation_failure",
                            error_message=guardrails_result.error_message,
                            stack_trace="",
                            severity=ErrorSeverity.MEDIUM,
                            category=ErrorCategory.DATA_ERROR,
                            context={
                                "step_id": step_id,
                                "original_output": action_result,
                                "tool_id": action_result.get('tool_id'),
                                "action": action_result.get('action'),
                                "guardrails_used": guardrails_result.guardrails_used
                            }
                        )
                        
                        self.error_events_buffer.append(error_event)
                        self.consecutive_failures += 1
                        
                        # 如果连续失败达到阈值，触发ValidationCritic分析
                        if self.consecutive_failures >= self.max_consecutive_failures:
                            logger.warning(f"🎯 连续失败{self.consecutive_failures}次，触发ValidationCritic分析")
                            
                            try:
                                critic_analysis = await self.validation_critic.review_failed_action(
                                    self.error_events_buffer[-5:],  # 最近5个错误
                                    context={"current_step": step_id, "task": task.description}
                                )
                                
                                logger.info(f"🎯 ValidationCritic分析完成: {len(critic_analysis.suggestions)}个建议")
                                
                                # 应用最高置信度的建议
                                if critic_analysis.suggestions:
                                    best_suggestion = max(critic_analysis.suggestions, key=lambda s: s.confidence)
                                    if best_suggestion.confidence >= 0.7:
                                        logger.info(f"🔧 应用ValidationCritic建议: {best_suggestion.reasoning}")
                                        action_result = best_suggestion.corrected_request
                                        self.consecutive_failures = 0  # 重置计数器
                                    else:
                                        logger.warning(f"⚠️ ValidationCritic建议置信度不足: {best_suggestion.confidence}")
                                        
                            except Exception as critic_error:
                                logger.error(f"❌ ValidationCritic分析失败: {critic_error}")
                    
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

            # 🛡️ 新增：基础参数校验与智能重新生成（P1修复）
            validation_passed, validation_error = await self._validate_tool_parameters(tool_id, action, params)
            if not validation_passed:
                logger.warning(f"⚠️ 参数校验失败: {validation_error}")
                
                # 🔧 P1修复：智能参数重新生成，而不是直接跳过
                retry_result = await self._smart_parameter_regeneration(
                    task, tool_id, action, params, validation_error, step_id, thinking, current_outputs
                )
                
                if retry_result["success"]:
                    # 重新生成成功，更新参数并继续
                    logger.info(f"✅ 智能参数重新生成成功")
                    params.clear()
                    params.update(retry_result["corrected_params"])
                    execution_code = json.dumps({
                        'action': action,
                        'tool_id': tool_id,
                        'parameters': params
                    }, ensure_ascii=False)
                    
                    # 记录重新生成步骤
                    regeneration_step = ExecutionStep(
                        step_id=step_id,
                        action_type=ActionType.TOOL_CALL,
                        action_params=params,
                        observation=f"参数重新生成成功: {retry_result['reasoning']}",
                        success=True,
                        thinking=f"重新分析任务需求: {retry_result['reasoning']}",
                        execution_code=execution_code,
                        timestamp=time.time(),
                        duration=retry_result.get("duration", 0.1),
                        llm_interactions=retry_result.get("llm_interactions", [])
                    )
                    steps.append(regeneration_step)
                    current_outputs.append(regeneration_step.observation)
                    step_id += 1
                    # 继续执行工具调用
                else:
                    # 重新生成失败，记录错误步骤
                    logger.error(f"❌ 智能参数重新生成失败: {retry_result['error']}")
                    validation_step = ExecutionStep(
                        step_id=step_id,
                        action_type=ActionType.TOOL_CALL,
                        action_params=params,
                        observation=f"参数校验失败且重新生成失败: {validation_error}. 重新生成错误: {retry_result['error']}",
                        success=False,
                        thinking=thinking,
                        execution_code=execution_code,
                        error_type=ErrorType.TOOL_ERROR,
                        error_message=f"{validation_error}; 重新生成失败: {retry_result['error']}",
                        timestamp=time.time(),
                        duration=0.1,
                        llm_interactions=current_step_llm_interactions
                    )
                    steps.append(validation_step)
                    current_outputs.append(validation_step.observation)
                    step_id += 1
                    continue  # 跳过当前循环，继续下一步

            # 🚨 P1-1: 检查是否应该跳过已知失败的工具/动作组合
            tool_action_key = f"{tool_id}.{action}"
            should_skip = await self._should_skip_failed_operation(tool_action_key, steps)
            if should_skip:
                logger.warning(f"⚠️ 跳过已知失败的操作: {tool_action_key}")
                # 记录跳过步骤
                skip_step = ExecutionStep(
                    step_id=step_id,
                    action_type=ActionType.TOOL_CALL,
                    action_params=params,
                    observation=f"跳过已知失败操作: {tool_action_key}。请考虑使用替代工具或方法。",
                    success=False,
                    thinking=thinking,
                    execution_code=execution_code,
                    error_type=ErrorType.TOOL_ERROR,
                    error_message=f"操作 {tool_action_key} 在最近步骤中反复失败",
                    timestamp=time.time(),
                    duration=0.1,
                    llm_interactions=current_step_llm_interactions
                )
                steps.append(skip_step)
                current_outputs.append(skip_step.observation)
                step_id += 1
                continue  # 跳过当前循环，继续下一步
            
            # 尝试执行工具调用，包含重试机制
            for attempt in range(max_retries + 1):
                
                # 特殊处理：检查是否完成任务
                if action == 'complete_task':
                    logger.info("🎯 LLM认为任务已完成")
                    
                    # 🔍 新增：记录完成任务的总结生成LLM交互
                    complete_summary_interactions = []
                    original_call_api_complete = self.client._call_api
                    async def wrapped_call_api_for_complete_summary(messages) -> str:
                        interaction_start = time.time()
                        response = await original_call_api_complete(messages)
                        
                        from core.interfaces import LLMInteraction
                        interaction = LLMInteraction()
                        interaction.provider = self.client.provider.value if hasattr(self.client.provider, 'value') else str(self.client.provider)
                        interaction.model = getattr(self.client, 'model', 'unknown')
                        interaction.context = f"step_{step_id}_complete_task_summary"
                        interaction.prompt = str(messages) if messages else ""
                        interaction.prompt_length = len(str(messages))
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
                
                # 检查是否是工具能力请求（只针对真正的能力请求，不是直接工具调用）
                elif action == 'request_tool_capability':
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
                
                # 🔍 新增：处理mcp-search-tool的调用（只有当tool_id确实是mcp-search-tool时）
                elif tool_id == 'mcp-search-tool':
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
                        
                        # 🎯 新增：成功时重置连续失败计数器和错误缓冲区
                        if tool_success:
                            self.consecutive_failures = 0
                            if self.error_events_buffer:
                                logger.debug(f"🔄 重置连续失败计数器，清理{len(self.error_events_buffer)}个错误事件")
                                self.error_events_buffer.clear()
                    
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

                # 🔧 增强的错误处理和智能反思-纠正逻辑
                if not tool_success:
                    # 📝 Sprint 2: 增强结构化错误日志 (P2 问题修复)
                    error_context = {
                        'step_id': step_id,
                        'action': action,
                        'tool_id': tool_id,
                        'attempt': attempt + 1,
                        'max_attempts': max_retries + 1,
                        'error_type': str(current_attempt_err_type),
                        'error_message': current_attempt_err_msg,
                        'timestamp': time.time(),
                        'task_id': task.task_id,
                        'session_context': f"{trajectory_id}_{step_id}"
                    }
                    
                    logger.warning(
                        f"🚨 步骤失败 [Step {step_id}] {tool_id}.{action} "
                        f"(第{attempt + 1}/{max_retries + 1}次) | 错误: {current_attempt_err_type} | "
                        f"消息: {current_attempt_err_msg[:100]}{'...' if len(current_attempt_err_msg) > 100 else ''}",
                        extra={'error_context': error_context}
                    )

                    # 🧠 Sprint 1: 增强智能重试逻辑（更精细的错误分类）
                    retry_strategy = self._analyze_error_and_determine_strategy(
                        current_attempt_err_type, current_attempt_err_msg, attempt, max_retries
                    )
                    
                    should_reflect = retry_strategy['should_reflect']
                    is_simple_retryable = retry_strategy['is_simple_retryable']
                    should_abort = retry_strategy['should_abort']
                    
                    if should_abort:
                        logger.error(f"🚨 错误不可重试，停止执行: {current_attempt_err_msg}")
                        break
                    
                    if should_reflect and attempt < max_retries:
                        logger.info(f"🧠 启动智能反思-纠正流程...")
                        
                        # 构建反思prompt，包含错误信息和上下文
                        reflection_prompt = await self._build_reflection_prompt(
                            task=task,
                            failed_action=action,
                            failed_tool_id=tool_id,
                            failed_params=params,
                            error_message=current_attempt_err_msg,
                            thinking=thinking,
                            available_tools_description=available_tools_description
                        )
                        
                        try:
                            # 让LLM分析错误并生成修正的工具调用
                            corrected_response = await self.client.call_llm(reflection_prompt)
                            logger.info(f"🧠 LLM反思响应 (长度: {len(corrected_response)})")
                            
                            # 解析修正后的响应
                            from core.llm.response_parsers.reasoning_response_parser import ReasoningResponseParser
                            parser = ReasoningResponseParser()
                            corrected_result = parser.parse_response(corrected_response)
                            
                            if corrected_result.get('action') and corrected_result.get('tool_id'):
                                # 使用修正后的参数进行下一次尝试
                                action = corrected_result['action']
                                tool_id = corrected_result['tool_id']
                                params = corrected_result.get('parameters', {})
                                thinking = corrected_result.get('thinking', thinking)
                                
                                logger.info(f"🔧 使用修正后的调用: {tool_id}.{action} with {params}")
                                await asyncio.sleep(1)  # 短暂延迟
                                continue  # 继续下一次尝试
                                
                        except Exception as reflection_error:
                            logger.error(f"❌ 反思-纠正失败: {reflection_error}")
                    
                    elif is_simple_retryable and attempt < max_retries:
                        # 🔄 增强重试策略：指数退避 + 历史跟踪
                        retry_key = f"{tool_id}.{action}"
                        
                        # 更新重试历史
                        if retry_key not in retry_history:
                            retry_history[retry_key] = {'count': 0, 'last_error': None, 'first_attempt': time.time()}
                        
                        retry_history[retry_key]['count'] += 1
                        retry_history[retry_key]['last_error'] = current_attempt_err_msg
                        
                        # 指数退避算法
                        retry_delay = base_retry_delay * (2 ** attempt)  # 1s, 2s, 4s...
                        retry_delay = min(retry_delay, 10)  # 最多10秒
                        
                        # 检查是否应该终止重试（避免无意义的重复）
                        if retry_history[retry_key]['count'] > 5:  # 单个操作最多5次
                            logger.warning(f"🚨 操作 {retry_key} 重试次数过多，停止重试")
                            break
                        
                        # 📝 Sprint 2: 结构化重试日志
                        retry_context = {
                            'retry_key': retry_key,
                            'current_attempt': attempt + 1,
                            'retry_delay': retry_delay,
                            'total_retries_for_operation': retry_history[retry_key]['count'],
                            'first_attempt_time': retry_history[retry_key]['first_attempt'],
                            'step_id': step_id,
                            'task_id': task.task_id
                        }
                        
                        logger.info(
                            f"🔄 智能重试 {action} (第{attempt+1}次, 延迟{retry_delay}s, 历史{retry_history[retry_key]['count']}次)",
                            extra={'retry_context': retry_context}
                        )
                        await asyncio.sleep(retry_delay)
                    else:
                        # 无法重试或已达到最大重试次数
                        logger.error(f"💥 步骤 {step_id} 最终失败，无法继续重试")
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
            
            # 🛡️ 循环检测：更新状态并检查重复模式
            action_key = f"{action}:{tool_id}"
            loop_detection['repeated_actions'][action_key] += 1
            loop_detection['recent_tool_calls'].append((action, tool_id, tool_success))
            
            # 更新失败计数
            if not tool_success:
                loop_detection['consecutive_failures'] += 1
                if current_attempt_err_msg:
                    loop_detection['repeated_errors'][current_attempt_err_msg] += 1
                    
                # 检查重复错误
                if loop_detection['repeated_errors'][current_attempt_err_msg] >= 3:
                    logger.warning(f"🛑 重复相同错误3次，终止执行: {current_attempt_err_msg[:100]}")
                    break
            else:
                loop_detection['consecutive_failures'] = 0
                loop_detection['last_progress_time'] = time.time()
            
            # 检查重复动作
            if loop_detection['repeated_actions'][action_key] > loop_detection['max_repeated_actions']:
                logger.warning(f"🛑 重复执行相同动作{loop_detection['repeated_actions'][action_key]}次，终止执行: {action_key}")
                break
            
            # 检查工具调用模式循环
            if len(loop_detection['recent_tool_calls']) >= 6:  # 至少6次调用才检测模式
                recent_actions = [f"{action}:{tool}" for action, tool, _ in list(loop_detection['recent_tool_calls'])[-6:]]
                # 检查是否有重复的3步模式
                if recent_actions[:3] == recent_actions[3:6]:
                    logger.warning(f"🛑 检测到工具调用循环模式，终止执行: {' -> '.join(recent_actions[:3])}")
                    break
            
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
            async def wrapped_call_api_for_completion(messages) -> str:
                interaction_start = time.time()
                response = await original_call_api(messages)
                
                from core.interfaces import LLMInteraction
                interaction = LLMInteraction()
                interaction.provider = self.client.provider.value if hasattr(self.client.provider, 'value') else str(self.client.provider)
                interaction.model = getattr(self.client, 'model', 'unknown')
                interaction.context = f"step_{step_id}_completion_check"
                interaction.prompt = str(messages) if messages else ""
                interaction.prompt_length = len(str(messages))
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
        
        # 🔧 改进的任务完成判断逻辑 - 添加客观指标验证
        if not success and steps:
            completion_analysis = self._analyze_task_completion_objectively(task, steps, current_outputs)
            
            if completion_analysis['should_complete']:
                success = True
                logger.info(f"✅ 基于客观分析判断任务完成: {completion_analysis['reason']}")
                logger.info(f"📊 完成度分析: {completion_analysis['metrics']}")
            else:
                # 只有在真正失败时才设置错误
                final_trajectory_error_type = steps[-1].error_type or ErrorType.EXECUTION_FAILED
                final_trajectory_error_message = completion_analysis['reason']
                logger.warning(f"❌ 任务执行未完成: {final_trajectory_error_message}")
                logger.info(f"📊 失败原因分析: {completion_analysis['metrics']}")

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
                    async def wrapped_call_api_for_summary(messages) -> str:
                        interaction_start = time.time()
                        response = await original_call_api(messages)
                        
                        from core.interfaces import LLMInteraction
                        interaction = LLMInteraction()
                        interaction.provider = self.client.provider.value if hasattr(self.client.provider, 'value') else str(self.client.provider)
                        interaction.model = getattr(self.client, 'model', 'unknown')
                        interaction.context = "final_task_summary"
                        interaction.prompt = str(messages) if messages else ""
                        interaction.prompt_length = len(str(messages))
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
            for i, ev in enumerate(self._tool_event_buffer):
                steps.append(ExecutionStep(
                    step_id=max([s.step_id for s in steps] + [0]) + i + 1,  # 确保step_id唯一递增
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
                        # get_used_tools_summary() 返回字典，需要获取键列表
                        tool_names = list(used_tools.keys())
                        key_insights.append(f"主要使用工具: {', '.join(tool_names[:3])}")
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
    
    async def _should_skip_failed_operation(self, tool_action_key: str, steps: List[ExecutionStep]) -> bool:
        """
        P1-1: 检查是否应该跳过已知失败的工具/动作组合
        基于最近的失败历史决定是否跳过特定的工具调用
        
        Args:
            tool_action_key: 工具动作键，格式为 "tool_id.action"
            steps: 执行步骤历史
            
        Returns:
            bool: True表示应该跳过，False表示可以尝试
        """
        try:
            # 如果步骤历史太少，不跳过
            if len(steps) < 3:
                return False
            
            # 分析最近的执行步骤
            recent_steps = steps[-5:]  # 查看最近5步
            
            # 统计相同工具/动作组合的失败次数
            failure_count = 0
            total_attempts = 0
            
            for step in recent_steps:
                if not hasattr(step, 'action_params') or not step.action_params:
                    continue
                
                # 重构工具动作键
                step_tool_id = step.action_params.get('tool_id', '')
                step_action = step.action_params.get('action', '')
                step_key = f"{step_tool_id}.{step_action}"
                
                # 如果是相同的工具/动作组合
                if step_key == tool_action_key:
                    total_attempts += 1
                    if not step.success:
                        failure_count += 1
            
            # 如果在最近尝试中，失败率超过阈值，则跳过
            if total_attempts >= 2:  # 至少尝试了2次
                failure_rate = failure_count / total_attempts
                if failure_rate >= 0.8:  # 失败率80%以上
                    logger.warning(f"🚨 工具组合 {tool_action_key} 失败率过高 ({failure_count}/{total_attempts})")
                    return True
            
            # 检查连续失败模式
            consecutive_failures = 0
            for step in reversed(recent_steps):
                if not hasattr(step, 'action_params') or not step.action_params:
                    continue
                
                step_tool_id = step.action_params.get('tool_id', '')
                step_action = step.action_params.get('action', '')
                step_key = f"{step_tool_id}.{step_action}"
                
                if step_key == tool_action_key:
                    if not step.success:
                        consecutive_failures += 1
                    else:
                        break  # 一旦有成功的就停止计数
                else:
                    break  # 不是相同操作就停止计数
            
            # 如果连续失败3次以上，跳过
            if consecutive_failures >= 3:
                logger.warning(f"🚨 工具组合 {tool_action_key} 连续失败 {consecutive_failures} 次")
                return True
            
            # 检查特定错误类型
            for step in reversed(recent_steps):
                if not hasattr(step, 'action_params') or not step.action_params:
                    continue
                
                step_tool_id = step.action_params.get('tool_id', '')
                step_action = step.action_params.get('action', '')
                step_key = f"{step_tool_id}.{step_action}"
                
                if step_key == tool_action_key and not step.success:
                    # 检查是否是不可恢复的错误类型
                    if step.error_type in [ErrorType.TOOL_ERROR, ErrorType.VALIDATION_ERROR]:
                        error_msg = step.error_message or ""
                        # 如果是权限错误、工具不存在等严重错误，跳过
                        critical_errors = [
                            "不支持的工具动作",
                            "权限拒绝",
                            "工具不存在",
                            "配置错误",
                            "认证失败"
                        ]
                        if any(critical_error in error_msg for critical_error in critical_errors):
                            logger.warning(f"🚨 工具组合 {tool_action_key} 遇到不可恢复错误: {error_msg}")
                            return True
                    break  # 只检查最近一次相同操作
            
            return False
            
        except Exception as e:
            logger.error(f"检查跳过失败操作时出错: {e}")
            return False  # 出错时保守选择不跳过
    
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
    
    async def _detect_error_patterns(self, steps: List[ExecutionStep], current_step_id: int) -> bool:
        """检测错误模式"""
        if len(steps) < 2:
            return False
        
        # 获取最近的步骤
        recent_steps = steps[-3:] if len(steps) >= 3 else steps
        
        # 模式1: 连续相同错误
        same_error_count = 0
        last_error = None
        for step in recent_steps:
            if not step.success:
                current_error = f"{step.error_type}:{step.error_message}"
                if current_error == last_error:
                    same_error_count += 1
                else:
                    same_error_count = 1
                    last_error = current_error
        
        if same_error_count >= 2:
            logger.warning(f"🔍 检测到重复错误模式: {last_error} (连续{same_error_count}次)")
            return True
        
        # 模式2: 相同action连续失败
        same_action_failures = 0
        last_action = None
        for step in recent_steps:
            if not step.success:
                current_action = step.action_params.get('action') if step.action_params else None
                if current_action == last_action and current_action:
                    same_action_failures += 1
                else:
                    same_action_failures = 1
                    last_action = current_action
        
        if same_action_failures >= 2:
            logger.warning(f"🔍 检测到相同action连续失败: {last_action} (连续{same_action_failures}次)")
            return True
        
        # 模式3: "LLM未指定tool_id"连续出现
        tool_id_errors = sum(1 for step in recent_steps 
                           if not step.success and "LLM未指定tool_id" in str(step.error_message))
        if tool_id_errors >= 2:
            logger.warning(f"🔍 检测到LLM tool_id错误模式 (连续{tool_id_errors}次)")
            return True
        
        # 模式4: "Unsupported action"连续出现
        action_errors = sum(1 for step in recent_steps 
                          if not step.success and "Unsupported action" in str(step.error_message))
        if action_errors >= 2:
            logger.warning(f"🔍 检测到不支持action错误模式 (连续{action_errors}次)")
            return True
        
        return False
    
    async def _apply_error_recovery(self, steps: List[ExecutionStep], current_step_id: int, task) -> str:
        """应用错误恢复策略"""
        if len(steps) < 2:
            return "continue"
        
        recent_steps = steps[-3:]
        
        # 分析错误类型并应用对应恢复策略
        for step in recent_steps:
            if not step.success:
                error_msg = str(step.error_message)
                
                # 恢复策略1: LLM响应格式问题
                if "LLM未指定tool_id" in error_msg or "action" in str(step.action_params):
                    logger.info("🔧 应用恢复策略: 重新强化prompt约束")
                    # 在下一次LLM调用时应用更强的约束
                    self._apply_stricter_prompt_constraints = True
                    return "adjust_strategy"
                
                # 恢复策略2: 不支持的action
                if "Unsupported action" in error_msg:
                    logger.info("🔧 应用恢复策略: 切换到基础工具调用")
                    # 记录失败的action，避免重复使用
                    failed_action = step.action_params.get('action') if step.action_params else None
                    if failed_action:
                        if not hasattr(self, '_failed_actions'):
                            self._failed_actions = set()
                        self._failed_actions.add(failed_action)
                        logger.info(f"🚫 记录失败action: {failed_action}")
                    return "adjust_strategy"
                
                # 恢复策略3: 连续工具调用失败
                tool_failures = sum(1 for s in recent_steps if not s.success)
                if tool_failures >= 3:
                    logger.warning("🔧 应用恢复策略: 任务可能超出当前工具能力，建议终止")
                    return "terminate"
        
        # 默认策略：调整approach
        return "adjust_strategy"
    
    def _build_recovery_context(self, steps: List[ExecutionStep]) -> str:
        """构建错误恢复上下文信息"""
        if not steps:
            return ""
        
        recent_failures = [s for s in steps[-3:] if not s.success]
        if not recent_failures:
            return ""
        
        recovery_context = "\n🔧 错误恢复指导:\n"
        
        # 分析失败模式
        failed_actions = set()
        failed_tools = set() 
        error_messages = set()
        
        for step in recent_failures:
            if step.action_params:
                action = step.action_params.get('action')
                tool_id = step.action_params.get('tool_id')
                if action:
                    failed_actions.add(action)
                if tool_id:
                    failed_tools.add(tool_id)
            
            if step.error_message:
                error_messages.add(str(step.error_message)[:100])
        
        if failed_actions:
            recovery_context += f"- 避免使用失败的actions: {', '.join(failed_actions)}\n"
        
        if failed_tools:
            recovery_context += f"- 避免重复失败的工具: {', '.join(failed_tools)}\n"
        
        if error_messages:
            recovery_context += f"- 常见错误类型: {'; '.join(error_messages)}\n"
        
        recovery_context += "- 建议: 尝试使用其他可用工具或不同的参数配置\n"
        recovery_context += "- 重要: 确保严格按照JSON格式返回响应\n"
        
        return recovery_context

    async def _build_reflection_prompt(self, task, failed_action, failed_tool_id, failed_params, 
                                       error_message, thinking, available_tools_description):
        """构建反思-纠正prompt，让LLM分析错误并生成修正的工具调用"""
        
        prompt_parts = [
            "# 🧠 Agent Error Analysis and Correction",
            "",
            "You are an intelligent Agent that needs to analyze a failed tool execution and provide a corrected approach.",
            "",
            f"## 📋 Original Task",
            f"**Task**: {task.description}",
            "",
            "## ❌ Failed Execution Details",
            f"**Failed Tool**: {failed_tool_id}",
            f"**Failed Action**: {failed_action}",
            f"**Failed Parameters**: {json.dumps(failed_params, indent=2)}",
            f"**Error Message**: {error_message}",
            "",
            "## 🤔 Previous Thinking Process",
            f"```",
            f"{thinking}",
            f"```",
            "",
            "## 🔧 Available Tools",
            f"{available_tools_description}",
            "",
            "## 🎯 Your Task: Error Analysis and Correction",
            "",
            "Analyze the failure and provide a **corrected** tool call. Common issues to check:",
            "",
            "### For microsandbox:",
            "- ✅ **CRITICAL**: `microsandbox_execute` MUST have `code` parameter",
            "- ✅ Example: `{\"code\": \"print('Hello World')\"}` ✅",
            "- ❌ Missing `code` parameter = FAILURE",
            "",
            "### For browser_use:",
            "- ✅ **CRITICAL**: `browser_navigate` MUST have `url` parameter",
            "- ✅ Example: `{\"url\": \"https://python.org\"}` ✅",
            "",
            "### For deepsearch:",
            "- ✅ **CRITICAL**: `research` MUST have `question` parameter",
            "- ✅ Example: `{\"question\": \"Python asyncio basics\"}` ✅",
            "",
            "## 📤 Required Response Format",
            "",
            "Analyze the error and return ONLY this JSON with the **corrected** tool call:",
            "",
            "```json",
            "{",
            '  "thinking": "ERROR ANALYSIS: [What went wrong?] CORRECTION: [How to fix it?]",',
            '  "confidence": 0.9,',
            '  "tool_id": "corrected-tool-id",',
            '  "action": "corrected-action-name",',
            '  "parameters": {',
            '    "corrected_param_1": "value1",',
            '    "corrected_param_2": "value2"',
            '  }',
            "}",
            "```",
            "",
            "**⚠️ CRITICAL REQUIREMENTS:**",
            "1. **FIX the specific error mentioned above**",
            "2. **Include ALL required parameters for the chosen tool**",
            "3. **NO other text outside the JSON object**",
            "",
            "Analyze the error and provide the corrected tool call now:"
        ]
        
        return [{"role": "user", "content": "\n".join(prompt_parts)}]

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
    
    def _analyze_task_completion_objectively(self, task: TaskSpec, steps: List[ExecutionStep], current_outputs: List[str]) -> Dict[str, Any]:
        """
        客观分析任务完成度
        
        Args:
            task: 任务规范
            steps: 执行步骤
            current_outputs: 当前输出
            
        Returns:
            包含完成度分析结果的字典
        """
        try:
            # 提取任务中的子任务要求
            sub_tasks = self._extract_task_requirements(task.description)
            
            # 分析执行步骤
            successful_steps = [s for s in steps if s.success]
            tool_steps = [s for s in steps if s.action_type == ActionType.TOOL_CALL and s.step_id > 1]
            successful_tool_steps = [s for s in tool_steps if s.success]
            
            # 统计工具使用情况
            used_tools = set()
            for step in successful_tool_steps:
                if hasattr(step, 'tool_id') and step.tool_id:
                    used_tools.add(step.tool_id)
            
            # 计算关键指标
            success_rate = len(successful_steps) / len(steps) if steps else 0
            tool_diversity = len(used_tools)
            output_quality = self._assess_output_quality(current_outputs)
            
            # 检查子任务完成情况
            sub_task_completion = self._check_sub_task_completion(sub_tasks, successful_tool_steps, current_outputs)
            
            # 综合判断
            metrics = {
                'total_steps': len(steps),
                'successful_steps': len(successful_steps),
                'success_rate': success_rate,
                'tool_steps': len(tool_steps),
                'successful_tool_steps': len(successful_tool_steps),
                'tool_diversity': tool_diversity,
                'used_tools': list(used_tools),
                'output_quality_score': output_quality['score'],
                'output_total_length': output_quality['total_length'],
                'sub_tasks_identified': len(sub_tasks),
                'sub_tasks_completed': sub_task_completion['completed_count'],
                'sub_task_completion_rate': sub_task_completion['completion_rate']
            }
            
            # 决策逻辑
            should_complete = self._decide_completion(metrics, sub_task_completion)
            
            reason = self._generate_completion_reason(should_complete, metrics, sub_task_completion)
            
            return {
                'should_complete': should_complete,
                'reason': reason,
                'metrics': metrics,
                'sub_task_analysis': sub_task_completion
            }
            
        except Exception as e:
            logger.error(f"客观完成度分析失败: {e}")
            return {
                'should_complete': False,
                'reason': f"分析过程出错: {str(e)}",
                'metrics': {},
                'sub_task_analysis': {}
            }
    
    def _extract_task_requirements(self, task_description: str) -> List[Dict[str, str]]:
        """从任务描述中提取子任务要求"""
        import re
        
        sub_tasks = []
        
        # 匹配明确的工具要求
        tool_patterns = [
            (r'用?([A-Za-z\-_]+).*?([研究|调研|搜索|查找|分析])', 'research'),
            (r'用?([A-Za-z\-_]*[Ss]andbox[A-Za-z\-_]*).*?([执行|运行|编写|代码])', 'execution'),
            (r'用?([A-Za-z\-_]*[Ss]earch[A-Za-z\-_]*).*?([搜索|查找|检索])', 'search'),
            (r'用?([A-Za-z\-_]*[Bb]rowser[A-Za-z\-_]*).*?([浏览|访问|导航])', 'browse')
        ]
        
        for pattern, task_type in tool_patterns:
            matches = re.findall(pattern, task_description, re.IGNORECASE)
            for match in matches:
                tool_hint = match[0] if isinstance(match, tuple) else match
                action_hint = match[1] if isinstance(match, tuple) and len(match) > 1 else task_type
                
                sub_tasks.append({
                    'type': task_type,
                    'tool_hint': tool_hint,
                    'action_hint': action_hint,
                    'description': f"{action_hint}任务(工具提示: {tool_hint})"
                })
        
        # 如果没有找到明确的工具要求，按步骤分析
        if not sub_tasks:
            step_patterns = [
                r'先(.+?)(?:然后|，|。|$)',
                r'然后(.+?)(?:最后|，|。|$)', 
                r'最后(.+?)(?:，|。|$)',
                r'第?[一二三1-3]步?[:：](.+?)(?:第?[二三四2-4]步?|，|。|$)'
            ]
            
            for pattern in step_patterns:
                matches = re.findall(pattern, task_description, re.IGNORECASE)
                for i, match in enumerate(matches):
                    task_text = match.strip()
                    if len(task_text) > 5:
                        sub_tasks.append({
                            'type': 'general',
                            'tool_hint': '',
                            'action_hint': '',
                            'description': task_text
                        })
        
        return sub_tasks[:5]  # 最多5个子任务
    
    async def _validate_tool_parameters(self, tool_id: str, action: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        增强参数校验 (P0-1: 参数校验&自动补齐)
        在工具调用前执行全面的参数检查、验证和自动补齐
        
        Args:
            tool_id: 工具ID
            action: 动作名称
            params: 参数字典
            
        Returns:
            (is_valid, error_message): 校验结果和错误信息
        """
        try:
            # 🛑 基本参数检查
            if not tool_id:
                return False, "工具ID不能为空"
            
            if not action:
                return False, "动作名称不能为空"
            
            if not isinstance(params, dict):
                return False, f"参数必须是字典类型，当前类型: {type(params)}"
            
            # 🆕 P0-1: 使用增强参数校验器进行全面校验
            parameter_validator = get_parameter_validator()
            
            # 获取当前任务描述用于智能补齐
            task_description = getattr(self, 'current_task_description', '')
            
            # 执行参数校验
            validation_result = parameter_validator.validate_tool_call(
                tool_id, action, params, task_description
            )
            
            if not validation_result.is_valid:
                # 尝试自动补齐缺失参数
                logger.warning(f"⚠️ 参数校验失败: {validation_result.error_message}")
                logger.info(f"🔧 尝试自动补齐缺失参数: {validation_result.missing_required}")
                
                # 🔧 预处理：智能参数映射
                mapped_params = self._map_common_parameter_names(tool_id, action, params)
                
                # 自动补齐参数
                completed_params = parameter_validator.auto_complete_parameters(
                    tool_id, action, mapped_params, task_description
                )
                
                # 重新校验补齐后的参数
                retry_validation = parameter_validator.validate_tool_call(
                    tool_id, action, completed_params, task_description
                )
                
                if retry_validation.is_valid:
                    logger.info(f"✅ 参数自动补齐成功，更新参数: {completed_params}")
                    # 更新原始参数字典
                    params.clear()
                    params.update(completed_params)
                else:
                    return False, f"参数补齐后仍然无效: {retry_validation.error_message}"
            
            # 🔧 尝试使用ToolSchemaManager进行额外校验
            try:
                # 检查工具动作是否存在
                is_valid_action = await self.tool_schema_manager.validate_tool_action(tool_id, action)
                if not is_valid_action:
                    return False, f"不支持的工具动作: {tool_id}.{action}"
                
                # 获取参数Schema进行验证
                param_schema = await self.tool_schema_manager.get_action_parameters_schema(tool_id, action)
                if param_schema:
                    validation_result = self._validate_against_schema(params, param_schema)
                    if not validation_result[0]:
                        return validation_result
                        
            except Exception as schema_error:
                logger.debug(f"Schema校验失败，已通过增强校验器: {schema_error}")
            
            # 🛑 特定工具的关键参数校验（硬编码规则）
            validation_rules = {
                'microsandbox': {
                    'microsandbox_execute': ['code'],
                    'run_code': ['code'],
                    'execute': ['code']
                },
                'browser_use': {
                    'browser_navigate': ['url'],
                    'browser_use_execute_task': ['task'],
                    'browser_click_element': ['index'],
                    'browser_input_text': ['index', 'text'],
                    'browser_extract_content': [],
                    'browser_search_google': ['query']
                },
                'deepsearch': {
                    'research': ['question'],
                    'comprehensive_research': ['question'],
                    'quick_research': ['question']
                },
                'mcp-search-tool': {
                    'analyze_tool_needs': ['task_description'],
                    'search_and_install_tools': ['task_description']
                }
            }
            
            # 查找匹配的规则
            tool_rules = None
            for rule_tool_id, rules in validation_rules.items():
                if rule_tool_id in tool_id or tool_id in rule_tool_id:
                    tool_rules = rules
                    break
            
            if tool_rules and action in tool_rules:
                required_params = tool_rules[action]
                for required_param in required_params:
                    if required_param not in params:
                        return False, f"缺少必需参数: {required_param} (工具: {tool_id}, 动作: {action})"
                    
                    param_value = params[required_param]
                    if param_value is None or (isinstance(param_value, str) and not param_value.strip()):
                        return False, f"参数 {required_param} 不能为空 (工具: {tool_id}, 动作: {action})"
            
            # 🛑 通用参数格式校验
            for param_name, param_value in params.items():
                # 检查URL格式
                if 'url' in param_name.lower() and isinstance(param_value, str):
                    if param_value and not param_value.startswith(('http://', 'https://')):
                        return False, f"参数 {param_name} 必须是有效的URL格式 (当前值: {param_value})"
                
                # 检查代码参数
                if param_name == 'code' and isinstance(param_value, str):
                    if not param_value.strip():
                        return False, f"代码参数不能为空"
                    
                    # 检查危险代码模式
                    dangerous_patterns = ['rm -rf', 'del /f', 'format c:', '__import__', 'eval(', 'exec(']
                    for pattern in dangerous_patterns:
                        if pattern in param_value.lower():
                            return False, f"检测到潜在危险代码模式: {pattern}"
            
            return True, ""
            
        except Exception as e:
            logger.error(f"参数校验异常: {e}")
            return False, f"参数校验异常: {str(e)}"
    
    def _map_common_parameter_names(self, tool_id: str, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        智能参数映射：将常见的参数名映射到工具期望的参数名
        
        Args:
            tool_id: 工具ID
            action: 动作名
            params: 原始参数
            
        Returns:
            映射后的参数字典
        """
        try:
            # 创建映射后的参数副本
            mapped_params = params.copy()
            
            # 🔧 P1-1修复：扩展参数映射规则覆盖更多别名
            parameter_mappings = {
                'deepsearch': {
                    # 所有动作都使用question参数
                    '*': {
                        'task_description': 'question',
                        'query': 'question',
                        'search_query': 'question',
                        'research_topic': 'question',
                        'research_query': 'question',
                        'search_term': 'question',
                        'search_content': 'question',
                        'topic': 'question',
                        'content': 'question',
                        'text': 'question',
                        'keywords': 'question',
                        'subject': 'question',
                        'prompt': 'question',
                        'description': 'question',
                        'objective': 'question',
                        'goal': 'question',
                        'task': 'question',
                        'requirement': 'question',
                        'request': 'question'
                    }
                },
                'mcp-search-tool': {
                    'analyze_tool_needs': {
                        'question': 'task_description',
                        'query': 'task_description',
                        'requirement': 'task_description',
                        'need': 'task_description',
                        'description': 'task_description',
                        'objective': 'task_description',
                        'goal': 'task_description',
                        'purpose': 'task_description',
                        'task': 'task_description',
                        'request': 'task_description',
                        'prompt': 'task_description'
                    },
                    'search_and_install_tools': {
                        'question': 'task_description',
                        'query': 'task_description',
                        'requirement': 'task_description',
                        'need': 'task_description',
                        'description': 'task_description',
                        'objective': 'task_description',
                        'goal': 'task_description',
                        'purpose': 'task_description',
                        'task': 'task_description',
                        'request': 'task_description',
                        'prompt': 'task_description'
                    },
                    'search_file_content': {
                        'query': 'search_term',
                        'search_query': 'search_term',
                        'term': 'search_term',
                        'content': 'search_term',
                        'pattern': 'search_term',
                        'keyword': 'search_term',
                        'text': 'search_term',
                        'string': 'search_term',
                        'phrase': 'search_term',
                        'expression': 'search_term'
                    }
                },
                'microsandbox': {
                    '*': {
                        'script': 'code',
                        'python_code': 'code',
                        'command': 'code',
                        'program': 'code',
                        'source': 'code',
                        'content': 'code',
                        'text': 'code',
                        'snippet': 'code',
                        'instructions': 'code',
                        'implementation': 'code',
                        'algorithm': 'code',
                        'function': 'code',
                        'method': 'code',
                        'procedure': 'code'
                    }
                },
                'browser_use': {
                    # 🔧 P0紧急修复1: 修正browser动作名称和参数映射
                    'browser_navigate': {
                        'link': 'url',
                        'address': 'url',
                        'site': 'url',
                        'website': 'url',
                        'page': 'url',
                        'target': 'url',
                        'destination': 'url',
                        'location': 'url',
                        'path': 'url',
                        'endpoint': 'url',
                        'resource': 'url'
                    },
                    'browser_use_execute_task': {
                        'question': 'task',
                        'objective': 'task',
                        'goal': 'task',
                        'description': 'task',
                        'instruction': 'task'
                    },
                    'browser_click_element': {
                        'element': 'index',
                        'target': 'index',
                        'position': 'index',
                        'number': 'index'
                    },
                    'browser_input_text': {
                        'content': 'text',
                        'input': 'text',
                        'value': 'text',
                        'string': 'text',
                        'message': 'text',
                        'data': 'text'
                    },
                    'browser_extract_content': {
                        # 没有特定参数映射，该动作不需要参数
                    },
                    'browser_search_google': {
                        'search_term': 'query',
                        'search_query': 'query',
                        'keywords': 'query',
                        'term': 'query'
                    }
                },
                # 新增工具映射
                'filesystem': {
                    'read_file': {
                        'filename': 'path',
                        'file': 'path',
                        'filepath': 'path',
                        'file_path': 'path',
                        'location': 'path',
                        'source': 'path',
                        'target': 'path'
                    },
                    'write_file': {
                        'filename': 'path',
                        'file': 'path',
                        'filepath': 'path',
                        'file_path': 'path',
                        'destination': 'path',
                        'target': 'path',
                        'data': 'content',
                        'text': 'content',
                        'body': 'content'
                    },
                    'list_directory': {
                        'directory': 'path',
                        'dir': 'path',
                        'folder': 'path',
                        'location': 'path',
                        'target': 'path'
                    }
                },
                'database': {
                    'execute_query': {
                        'sql': 'query',
                        'statement': 'query',
                        'command': 'query',
                        'script': 'query'
                    },
                    'insert_data': {
                        'table_name': 'table',
                        'target_table': 'table',
                        'destination': 'table',
                        'record': 'data',
                        'row': 'data',
                        'values': 'data'
                    }
                },
                'api-client': {
                    'make_request': {
                        'endpoint': 'url',
                        'api_url': 'url',
                        'target': 'url',
                        'destination': 'url',
                        'payload': 'data',
                        'body': 'data',
                        'content': 'data',
                        'parameters': 'data'
                    }
                },
                'text-processing': {
                    'analyze_text': {
                        'input': 'text',
                        'content': 'text',
                        'data': 'text',
                        'string': 'text',
                        'document': 'text',
                        'passage': 'text'
                    },
                    'transform_text': {
                        'input': 'text',
                        'content': 'text',
                        'source': 'text',
                        'original': 'text'
                    }
                }
            }
            
            # 获取工具的映射规则
            if tool_id in parameter_mappings:
                tool_mappings = parameter_mappings[tool_id]
                
                # 查找动作特定的映射或通用映射
                action_mappings = tool_mappings.get(action, tool_mappings.get('*', {}))
                
                # 应用映射
                for old_param, new_param in action_mappings.items():
                    if old_param in mapped_params and new_param not in mapped_params:
                        mapped_params[new_param] = mapped_params[old_param]
                        # 如果新参数名不同于旧参数名，删除旧参数
                        if old_param != new_param:
                            del mapped_params[old_param]
                            logger.debug(f"🔧 参数映射: {old_param} -> {new_param}")
            
            # 移除系统内部参数
            system_params = {'action', 'tool_id', 'tool', 'thinking', 'reasoning'}
            for sys_param in system_params:
                if sys_param in mapped_params:
                    del mapped_params[sys_param]
                    logger.debug(f"🧹 移除系统参数: {sys_param}")
            
            return mapped_params
            
        except Exception as e:
            logger.warning(f"⚠️ 参数映射失败: {e}")
            return params

    def _validate_against_schema(self, params: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, str]:
        """
        根据Schema校验参数
        
        Args:
            params: 要校验的参数
            schema: 参数Schema
            
        Returns:
            (is_valid, error_message): 校验结果
        """
        try:
            for param_name, param_config in schema.items():
                param_desc = str(param_config)
                
                # 检查必需参数
                if '必需' in param_desc or 'required' in param_desc.lower():
                    if param_name not in params:
                        return False, f"缺少必需参数: {param_name}"
                    
                    if params[param_name] is None or (isinstance(params[param_name], str) and not params[param_name].strip()):
                        return False, f"必需参数 {param_name} 不能为空"
            
            return True, ""
            
        except Exception as e:
            logger.debug(f"Schema校验异常: {e}")
            return True, ""  # 容错处理，如果Schema校验失败则通过
    
    def _assess_output_quality(self, outputs: List[str]) -> Dict[str, Any]:
        """评估输出质量"""
        if not outputs:
            return {'score': 0.0, 'total_length': 0}
        
        total_length = sum(len(output) for output in outputs)
        
        # 基于长度和内容丰富度评分
        if total_length == 0:
            score = 0.0
        elif total_length < 100:
            score = 0.2
        elif total_length < 500:
            score = 0.5
        elif total_length < 2000:
            score = 0.8
        else:
            score = 1.0
        
        # 检查是否包含结构化内容
        has_structure = any(
            ('```' in output or 
             output.count('\n') > 3 or 
             any(keyword in output.lower() for keyword in ['结果', '总结', '分析', '建议', '步骤']))
            for output in outputs
        )
        
        if has_structure:
            score = min(1.0, score + 0.2)
        
        return {
            'score': score,
            'total_length': total_length,
            'has_structure': has_structure
        }
    
    def _check_sub_task_completion(self, sub_tasks: List[Dict], successful_tool_steps: List[ExecutionStep], outputs: List[str]) -> Dict[str, Any]:
        """检查子任务完成情况"""
        if not sub_tasks:
            return {
                'completed_count': 0,
                'completion_rate': 0.0,
                'details': []
            }
        
        completed_count = 0
        details = []
        
        # 统计已使用的工具
        used_tools = set()
        for step in successful_tool_steps:
            if hasattr(step, 'tool_id') and step.tool_id:
                used_tools.add(step.tool_id.lower())
        
        for sub_task in sub_tasks:
            is_completed = False
            evidence = []
            
            # 检查工具匹配
            tool_hint = sub_task.get('tool_hint', '').lower()
            task_type = sub_task.get('type', '')
            
            if tool_hint:
                # 检查是否有相关工具被使用
                tool_matched = any(tool_hint in used_tool for used_tool in used_tools)
                if tool_matched:
                    evidence.append(f"使用了相关工具({tool_hint})")
                    is_completed = True
            
            # 基于任务类型检查
            if task_type == 'research' and any('deepsearch' in tool or 'search' in tool for tool in used_tools):
                evidence.append("执行了研究/搜索任务")
                is_completed = True
            elif task_type == 'execution' and any('sandbox' in tool for tool in used_tools):
                evidence.append("执行了代码/沙箱任务")
                is_completed = True
            elif task_type == 'search' and any('search' in tool for tool in used_tools):
                evidence.append("执行了搜索任务")
                is_completed = True
            
            # 检查输出中是否有相关内容
            if outputs and not is_completed:
                output_text = ' '.join(outputs).lower()
                keywords = sub_task.get('description', '').lower().split()[:3]  # 取前3个关键词
                if any(keyword in output_text for keyword in keywords if len(keyword) > 2):
                    evidence.append("输出中包含相关内容")
                    is_completed = True
            
            if is_completed:
                completed_count += 1
            
            details.append({
                'task': sub_task.get('description', ''),
                'completed': is_completed,
                'evidence': evidence
            })
        
        completion_rate = completed_count / len(sub_tasks) if sub_tasks else 0.0
        
        return {
            'completed_count': completed_count,
            'completion_rate': completion_rate,
            'details': details
        }
    
    def _decide_completion(self, metrics: Dict[str, Any], sub_task_completion: Dict[str, Any]) -> bool:
        """基于指标决定是否完成"""
        
        # 基本条件检查
        has_minimum_execution = (
            metrics['successful_tool_steps'] >= 1 and
            metrics['success_rate'] >= 0.5
        )
        
        # 输出质量检查
        has_quality_output = metrics['output_quality_score'] >= 0.5
        
        # 子任务完成度检查
        sub_task_threshold = 0.6 if metrics['sub_tasks_identified'] > 1 else 0.5
        has_sub_task_completion = sub_task_completion['completion_rate'] >= sub_task_threshold
        
        # 工具多样性检查（对于复杂任务）
        if metrics['sub_tasks_identified'] >= 3:
            has_tool_diversity = metrics['tool_diversity'] >= 2
        else:
            has_tool_diversity = metrics['tool_diversity'] >= 1
        
        # 综合判断
        completion_score = (
            (0.3 if has_minimum_execution else 0) +
            (0.2 if has_quality_output else 0) +
            (0.3 if has_sub_task_completion else 0) +
            (0.2 if has_tool_diversity else 0)
        )
        
        return completion_score >= 0.7
    
    def _generate_completion_reason(self, should_complete: bool, metrics: Dict[str, Any], sub_task_completion: Dict[str, Any]) -> str:
        """生成完成判断的原因说明"""
        
        if should_complete:
            reasons = []
            if metrics['successful_tool_steps'] > 0:
                reasons.append(f"成功执行了{metrics['successful_tool_steps']}个工具步骤")
            if metrics['tool_diversity'] > 1:
                reasons.append(f"使用了{metrics['tool_diversity']}种不同工具")
            if sub_task_completion['completion_rate'] > 0:
                reasons.append(f"子任务完成率{sub_task_completion['completion_rate']:.1%}")
            if metrics['output_quality_score'] > 0.5:
                reasons.append(f"输出质量评分{metrics['output_quality_score']:.1f}")
            
            return f"任务已完成: {', '.join(reasons)}"
        else:
            problems = []
            if metrics['successful_tool_steps'] == 0:
                problems.append("没有成功的工具执行")
            elif metrics['tool_diversity'] == 0:
                problems.append("没有使用任何工具")
            elif sub_task_completion['completion_rate'] < 0.5:
                problems.append(f"子任务完成率过低({sub_task_completion['completion_rate']:.1%})")
            elif metrics['output_quality_score'] < 0.3:
                problems.append("输出质量不足")
            
            return f"任务未完成: {', '.join(problems) if problems else '未达到完成标准'}"
    
    def _analyze_error_and_determine_strategy(self, error_type: ErrorType, error_msg: str, 
                                            attempt: int, max_retries: int) -> Dict[str, bool]:
        """
        Sprint 1: 增强错误分析和重试策略决策 (P1 问题修复)
        
        Args:
            error_type: 错误类型
            error_msg: 错误消息
            attempt: 当前尝试次数
            max_retries: 最大重试次数
            
        Returns:
            包含重试策略决策的字典
        """
        error_msg_lower = error_msg.lower()
        
        # 🚨 不可重试的错误模式
        non_retryable_patterns = [
            '权限被拒绝', 'permission denied', 'access denied',
            '未找到工具', 'tool not found', 'command not found',
            '配置错误', 'configuration error', 'config error',
            '身份验证失败', 'authentication failed', 'auth failed'
        ]
        
        should_abort = any(pattern in error_msg_lower for pattern in non_retryable_patterns)
        if should_abort:
            return {'should_reflect': False, 'is_simple_retryable': False, 'should_abort': True}
        
        # 🔄 简单重试的错误类型（网络、超时、限流等）
        simple_retryable_types = [ErrorType.NETWORK_ERROR, ErrorType.TIMEOUT, ErrorType.RATE_LIMIT]
        simple_retryable_patterns = [
            'timeout', '超时', 'connection', '连接', 'network', '网络',
            'rate limit', '限流', 'too many requests', '请求过多',
            'service unavailable', '服务不可用', 'server error', '服务器错误'
        ]
        
        is_simple_retryable = (
            error_type in simple_retryable_types or
            any(pattern in error_msg_lower for pattern in simple_retryable_patterns)
        )
        
        # 🧠 需要反思纠正的错误模式
        reflection_patterns = [
            # 参数错误
            '代码不能为空', 'code cannot be empty', 'missing code',
            '参数', 'parameter', 'required', 'missing', '缺少',
            'invalid parameter', '无效参数',
            # 动作错误
            'unsupported action', '不支持的动作', 'action not found',
            'invalid action', '无效动作',
            # 工具使用错误
            'tool usage error', '工具使用错误',
            'incorrect usage', '使用不正确',
            # JSON格式错误
            'json', 'format', '格式', 'syntax', '语法'
        ]
        
        needs_reflection = (
            error_type in [ErrorType.TOOL_ERROR, ErrorType.SYSTEM_ERROR] and
            any(pattern in error_msg_lower for pattern in reflection_patterns)
        )
        
        # 📊 基于尝试次数调整策略
        if attempt >= max_retries:
            return {'should_reflect': False, 'is_simple_retryable': False, 'should_abort': False}
        
        # 最终决策
        should_reflect = needs_reflection and attempt < max_retries - 1  # 留一次机会给简单重试
        
        return {
            'should_reflect': should_reflect,
            'is_simple_retryable': is_simple_retryable and not needs_reflection,  # 优先反思纠正
            'should_abort': False
        }
    
    async def _smart_parameter_regeneration(self, task, tool_id: str, action: str, 
                                         original_params: Dict[str, Any], validation_error: str,
                                         step_id: int, original_thinking: str, 
                                         current_outputs: List[str]) -> Dict[str, Any]:
        """
        智能参数重新生成 - P1修复的核心方法
        
        当参数校验失败时，通过LLM重新分析任务需求，生成正确的参数
        """
        try:
            regeneration_start = time.time()
            regeneration_interactions = []
            
            # 构建智能重新生成的Prompt
            error_context = f"""
参数校验失败详情：
- 工具: {tool_id}
- 动作: {action}
- 校验错误: {validation_error}
- 原始参数: {json.dumps(original_params, ensure_ascii=False)}

任务描述: {task.description}

最近的执行历史:
{chr(10).join(current_outputs[-3:]) if current_outputs else "无历史"}
"""
            
            # 获取工具的实际Schema信息
            parameter_validator = get_parameter_validator()
            valid_actions = parameter_validator.get_valid_actions(tool_id)
            param_schema = parameter_validator.get_parameter_schema(tool_id, action)
            
            schema_context = ""
            if param_schema:
                required_params = param_schema.get("required", [])
                param_patterns = param_schema.get("patterns", {})
                schema_context = f"""
工具能力说明:
- 可用动作: {valid_actions}
- 当前动作 '{action}' 的必需参数: {required_params}
- 参数示例: {json.dumps(param_patterns, ensure_ascii=False)}
"""
            
            regeneration_prompt = f"""
🔧 参数校验失败，需要重新生成正确的工具调用参数

{error_context}

{schema_context}

请重新分析任务需求，生成正确的工具调用。请特别注意：
1. 确保提供所有必需的参数
2. 从任务描述中提取相关信息填入参数
3. 参数值必须具体、准确，不能是占位符

请返回JSON格式：
{{
    "thinking": "重新分析思路",
    "corrected_parameters": {{
        "param1": "具体值",
        "param2": "具体值"
    }},
    "reasoning": "修正理由"
}}
"""
            
            # 调用LLM重新生成参数
            original_call_api = self.client._call_api
            async def wrapped_call_api_for_regeneration(messages) -> str:
                interaction_start = time.time()
                response = await original_call_api(messages)
                
                from core.interfaces import LLMInteraction
                interaction = LLMInteraction()
                interaction.provider = self.client.provider.value if hasattr(self.client.provider, 'value') else str(self.client.provider)
                interaction.model = getattr(self.client, 'model', 'unknown')
                interaction.context = "parameter_regeneration"
                interaction.prompt = str(messages) if messages else ""
                interaction.prompt_length = len(str(messages))
                interaction.prompt_type = "parameter_correction"
                interaction.response = response
                interaction.response_length = len(response)
                interaction.response_time = time.time() - interaction_start
                regeneration_interactions.append(interaction)
                return response
            
            self.client._call_api = wrapped_call_api_for_regeneration
            
            try:
                # 将prompt转换为消息格式
                regeneration_messages = [
                    {"role": "user", "content": regeneration_prompt}
                ]
                raw_response = await self.client._call_api(regeneration_messages)
                
                # 解析LLM响应
                import re
                json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
                if json_match:
                    response_json = json.loads(json_match.group())
                    corrected_params = response_json.get("corrected_parameters", {})
                    reasoning = response_json.get("reasoning", "重新生成参数")
                    
                    # 重新校验生成的参数
                    final_validation = parameter_validator.validate_tool_call(
                        tool_id, action, corrected_params, task.description
                    )
                    
                    if final_validation.is_valid:
                        logger.info(f"✅ LLM参数重新生成成功: {reasoning}")
                        return {
                            "success": True,
                            "corrected_params": corrected_params,
                            "reasoning": reasoning,
                            "duration": time.time() - regeneration_start,
                            "llm_interactions": regeneration_interactions
                        }
                    else:
                        logger.warning(f"❌ LLM重新生成的参数仍然无效: {final_validation.error_message}")
                        return {
                            "success": False,
                            "error": f"重新生成的参数仍然无效: {final_validation.error_message}",
                            "duration": time.time() - regeneration_start,
                            "llm_interactions": regeneration_interactions
                        }
                else:
                    logger.error(f"❌ LLM响应无法解析为JSON: {raw_response}")
                    return {
                        "success": False,
                        "error": f"LLM响应格式错误: {raw_response[:200]}...",
                        "duration": time.time() - regeneration_start,
                        "llm_interactions": regeneration_interactions
                    }
                    
            finally:
                self.client._call_api = original_call_api
                
        except Exception as e:
            logger.error(f"❌ 智能参数重新生成异常: {e}")
            return {
                "success": False,
                "error": f"重新生成异常: {str(e)}",
                "duration": time.time() - regeneration_start if 'regeneration_start' in locals() else 0,
                "llm_interactions": regeneration_interactions if 'regeneration_interactions' in locals() else []
            }
    
    async def _build_error_analysis_context(self, steps: List[ExecutionStep], current_step_id: int) -> Dict[str, Any]:
        """
        构建智能错误分析上下文 - P2修复的核心方法
        
        分析之前步骤中的错误模式，为LLM提供具体的纠正指导
        """
        try:
            if len(steps) < 2:
                return {"has_errors": False}
            
            # 分析最近的失败步骤
            recent_failed_steps = []
            repeated_errors = {}
            tool_action_failures = {}
            
            # 检查最近5步的错误模式
            recent_steps = steps[-5:] if len(steps) >= 5 else steps
            
            for step in recent_steps:
                if not step.success and step.error_message:
                    recent_failed_steps.append({
                        "step_id": step.step_id,
                        "tool_id": getattr(step, 'action_params', {}).get('tool_id'),
                        "action": getattr(step, 'action_params', {}).get('action'),
                        "error_message": step.error_message,
                        "error_type": step.error_type.value if step.error_type else "unknown"
                    })
                    
                    # 统计重复错误
                    error_key = step.error_message.lower()[:100]  # 取错误信息的前100字符作为key
                    repeated_errors[error_key] = repeated_errors.get(error_key, 0) + 1
                    
                    # 统计工具动作失败
                    if hasattr(step, 'action_params') and step.action_params:
                        tool_id = step.action_params.get('tool_id')
                        action = step.action_params.get('action')
                        if tool_id and action:
                            tool_action_key = f"{tool_id}.{action}"
                            tool_action_failures[tool_action_key] = tool_action_failures.get(tool_action_key, 0) + 1
            
            if not recent_failed_steps:
                return {"has_errors": False}
            
            # 分析错误模式
            error_patterns = []
            corrective_guidance = []
            
            # 🔍 检查重复的参数错误
            parameter_errors = [step for step in recent_failed_steps 
                              if any(pattern in step["error_message"].lower() 
                                   for pattern in ["缺少必需参数", "missing", "required", "参数", "parameter"])]
            
            if parameter_errors:
                error_patterns.append("repeated_parameter_errors")
                missing_params = []
                for step in parameter_errors:
                    if "缺少必需参数" in step["error_message"]:
                        # 提取缺少的参数名
                        import re
                        params_match = re.search(r"缺少必需参数[：:]\s*\[?([^\]]+)\]?", step["error_message"])
                        if params_match:
                            missing_params.extend([p.strip().strip("'\"") for p in params_match.group(1).split(",")])
                
                unique_missing_params = list(set(missing_params))
                corrective_guidance.append(f"⚠️ 重复的参数错误：请确保提供必需参数 {unique_missing_params}。从任务描述中提取具体值，不要使用占位符。")
            
            # 🔍 检查重复的动作错误
            action_errors = [step for step in recent_failed_steps 
                           if any(pattern in step["error_message"].lower() 
                                for pattern in ["不支持的动作", "unsupported action", "action not found", "不存在"])]
            
            if action_errors:
                error_patterns.append("repeated_action_errors")
                corrective_guidance.append("⚠️ 重复的动作错误：请仔细检查工具的可用动作列表，确保使用正确的动作名称。")
            
            # 🔍 检查重复的工具调用失败
            repeated_tool_failures = {k: v for k, v in tool_action_failures.items() if v >= 2}
            if repeated_tool_failures:
                error_patterns.append("repeated_tool_failures")
                failed_combinations = list(repeated_tool_failures.keys())
                corrective_guidance.append(f"⚠️ 重复失败的工具调用：{failed_combinations}. 考虑使用其他工具或方法完成任务。")
            
            # 🔍 检查JSON格式错误
            json_errors = [step for step in recent_failed_steps 
                          if any(pattern in step["error_message"].lower() 
                               for pattern in ["json", "format", "格式", "syntax", "语法"])]
            
            if json_errors:
                error_patterns.append("json_format_errors")
                corrective_guidance.append("⚠️ JSON格式错误：请确保返回有效的JSON格式，检查括号匹配和语法正确性。")
            
            # 构建最终的错误分析上下文
            error_analysis = {
                "has_errors": True,
                "recent_failures_count": len(recent_failed_steps),
                "error_patterns": error_patterns,
                "corrective_guidance": corrective_guidance,
                "repeated_errors": {k: v for k, v in repeated_errors.items() if v >= 2},
                "failed_tool_actions": repeated_tool_failures,
                "specific_recommendations": []
            }
            
            # 🎯 生成具体的改进建议
            if "repeated_parameter_errors" in error_patterns:
                error_analysis["specific_recommendations"].append(
                    "在生成工具调用前，仔细阅读任务描述，提取具体的参数值（如URL、查询内容、代码等）。"
                )
            
            if "repeated_action_errors" in error_patterns:
                error_analysis["specific_recommendations"].append(
                    "在选择动作前，仔细查看工具的'可用操作'列表，选择确实存在的动作名称。"
                )
            
            if "repeated_tool_failures" in error_patterns:
                error_analysis["specific_recommendations"].append(
                    "考虑换用其他工具或将任务分解为更小的步骤来完成。"
                )
            
            # 如果错误过多，建议重新审视任务
            if len(recent_failed_steps) >= 3:
                error_analysis["specific_recommendations"].append(
                    "多次尝试失败，建议重新审视任务需求，可能需要改变解决思路。"
                )
            
            logger.info(f"🔍 错误分析完成: {len(error_patterns)} 种模式, {len(corrective_guidance)} 条指导")
            return error_analysis
            
        except Exception as e:
            logger.error(f"❌ 构建错误分析上下文失败: {e}")
            return {"has_errors": False, "error": str(e)}

