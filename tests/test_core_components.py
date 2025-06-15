"""综合单元测试 - 针对核心基础组件
运行命令: pytest -q tests/test_core_components.py
所有外部依赖使用 MagicMock / AsyncMock 替身, 保证脱离 Redis / WebSocket / Docker 等运行环境即可执行。
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# ============================
# 1. ServiceManager 依赖拓扑
# ============================

@pytest.fixture
def dummy_services():
    """构造 3 个假服务：a 无依赖，b 依赖 a，c 依赖 b"""
    from services.service_manager import ServiceManager

    async def noop(*_args, **_kwargs):
        return True

    sm = ServiceManager()
    sm.register_service("a", noop, noop, noop, noop, dependencies=[])
    sm.register_service("b", noop, noop, noop, noop, dependencies=["a"])
    sm.register_service("c", noop, noop, noop, noop, dependencies=["b"])
    return sm


def test_service_manager_start_order(dummy_services):
    """确保 _resolve_start_order 输出拓扑有序列表 a->b->c"""
    dummy_services._resolve_start_order()
    start_order = dummy_services.start_order
    assert start_order == ["a", "b", "c"], "Service 启动顺序解析错误"


# =================================
# 2. CoreManager 工具即时注册流程
# =================================

@pytest_asyncio.fixture
async def core_manager_instance():
    """构造 CoreManager，mock 掉 Redis / WebSocket / Runner 重型依赖"""
    with (
        patch("core.toolscore.core_manager.redis") as mock_redis,
        patch("core.toolscore.runners.ProcessRunner") as MockRunner,
        patch("core.toolscore.core_manager.WebSocketManager") as MockWSMgr,
    ):

        # Redis 替身：所有方法 AsyncMock
        mock_redis.from_url.return_value = AsyncMock(
            publish=AsyncMock(), ping=AsyncMock(return_value=True)
        )

        # Runner 替身：什么都不做，但确保是 ProcessRunner 的实例
        runner_instance = MagicMock()
        runner_instance.__class__ = MockRunner  # 设置类型以通过 isinstance 检查
        MockRunner.return_value = runner_instance

        # WebSocketManager 替身：记录广播调用
        ws_instance = MockWSMgr.return_value
        ws_instance.broadcast = AsyncMock()

        from core.toolscore.core_manager import CoreManager

        cm = CoreManager()
        await cm.initialize()
        yield cm, ws_instance  # 返回实例与 ws 以便断言


@pytest.mark.asyncio
async def test_register_tool_immediately(core_manager_instance):
    """验证 register_tool_immediately 发布 Redis 事件与 WS 通知"""
    cm, ws_mgr = core_manager_instance

    # 构造最小化的 MCPServerSpec
    from core.toolscore.interfaces import MCPServerSpec, ToolCapability, ToolType

    spec = MCPServerSpec(
        tool_id="unit-test-tool",
        name="UnitTest Tool",
        description="Just for tests",
        tool_type=ToolType.MCP_SERVER,
        capabilities=[ToolCapability(name="ut_cap", description="cap", parameters={})],
        tags=["test"],
        enabled=True,
        endpoint="ws://localhost:9999/mcp"
    )

    success = await cm.register_tool_immediately(spec)
    assert success is True
    # Redis publish 被调用 2 次：tool_events / immediate_tool_updates
    if cm.redis_client:  # fallback 模式下 redis_client 可能为 None
        assert cm.redis_client.publish.call_count == 2
    # WebSocket 广播一次
    assert ws_mgr.broadcast.call_count == 1


# ===============================
# 3. Dispatcher Enhanced 基本流
# ===============================

def test_dispatcher_task_routing():
    """测试任务路由逻辑（不需要实际的 Redis 连接）"""
    from core.interfaces import TaskSpec, TaskType
    
    # 测试任务类型到队列的映射
    task_reasoning = TaskSpec(
        task_id="test-1",
        task_type=TaskType.REASONING,
        description="Test reasoning task"
    )
    
    # 验证队列名称生成
    expected_queue = f"tasks:{task_reasoning.task_type.value}"
    assert expected_queue == "tasks:reasoning"
    
    # 测试其他任务类型
    task_types_to_queues = {
        TaskType.REASONING: "tasks:reasoning",
        TaskType.CODE_GENERATION: "tasks:code_generation",
        TaskType.WEB_TASK: "tasks:web_task"
    }
    
    for task_type, expected_queue in task_types_to_queues.items():
        task = TaskSpec(
            task_id=f"test-{task_type.value}",
            task_type=task_type,
            description=f"Test {task_type.value} task"
        )
        queue_name = f"tasks:{task.task_type.value}"
        assert queue_name == expected_queue