#!/usr/bin/env python3
"""
Agent Data Platform - Main Entry Point (无Docker版本)
"""

import asyncio
import logging
import sys
import argparse # 新增导入
from pathlib import Path

from typing import Optional # 修复 Bug 1
from config import setup_logging, get_available_api_keys_info, logging_config
from utils.port_manager import PortManager # 修复 Bug 8
from config import settings

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 设置日志
logging_config.setup_logging()
logger = logging.getLogger(__name__)

# from services import start_toolscore_services, stop_toolscore_services, start_redis_manager, stop_redis_manager
from services import start_toolscore_services
from services.mcp_server_launcher import MCPServerLauncher
from core.toolscore.api.monitoring_api import ToolScoreMonitoringAPI
from config import TOOLSCORE_MONITORING_PORT
from core.toolscore.mcp.mcp_client import MCPToolClient
# from core.toolscore.managers.unified_tool_library import UnifiedToolLibrary
from services import start_task_api_server # 移动导入位置
from services import start_enhanced_reasoning_runtime # 移动导入位置

async def _display_startup_messages():
    """显示最终的启动成功消息和CLI提示。"""
    # 给予其他异步任务一些时间来完成日志输出
    await asyncio.sleep(0.1) # 减少等待时间，确保所有后台日志都已输出

    print("\n" + "="*80)
    print("✨ Agent Data Platform 已完全启动！ ✨")
    print(f"🚀 ToolScore MCP Server: {settings.TOOLSCORE_MCP_WS_URL}")
    print(f"📊 ToolScore Monitoring API: http://localhost:{settings.TOOLSCORE_MONITORING_PORT}")
    print(f"✅ Task API: http://localhost:{settings.TASK_API_PORT}")
    print("您现在可以在当前终端提交任务，或通过 Task API 提交。")
    print("✨ 按 Ctrl+C 停止服务。")
    print("="*80 + "\n")
    sys.stdout.flush() # 强制刷新输出

async def main():
    """主启动函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Agent Data Platform (无Docker版本)")
    parser.add_argument(
        "--clear-queue",
        action="store_true",
        help="在启动前清空所有任务队列 (tasks:reasoning, tasks:code, tasks:web)"
    )
    args = parser.parse_args()

    logger.info("启动 Agent Data Platform (无Docker版本)...")
    
    # 初始化变量，避免cleanup时的作用域错误
    core_manager = None
    toolscore_server = None
    enhanced_runtime = None
    redis_manager = None
    tool_library = None
    monitoring_api_server = None
    mcp_launcher: Optional[MCPServerLauncher] = None # 新增 mcp_launcher 变量初始化，并指定类型
    
    # 用于存储所有后台任务的列表
    background_tasks = []

    try:
        # === Redis管理器初始化 ===
        from services import start_redis_manager, stop_redis_manager
        redis_manager = await start_redis_manager()

        # === 根据命令行参数清空任务队列 ===
        if args.clear_queue:
            logger.info("检测到 --clear-queue 参数，正在清空任务队列...")
            # 导入 redis.asyncio
            import redis.asyncio as redis_client_lib
            
            # 获取 Redis URL 并创建客户端实例
            redis_url = redis_manager.get_redis_url()
            # 如果是内存模式，则无法清空真实的Redis队列，直接跳过
            if redis_manager.is_fallback_mode():
                logger.warning("Redis 处于内存模式，无法清空真实的 Redis 队列。")
            else:
                redis_client = redis_client_lib.from_url(redis_url)
                task_queues = ["tasks:reasoning", "tasks:code", "tasks:web"]
                for queue_name in task_queues:
                    try:
                        # 删除 Stream
                        await redis_client.delete(queue_name)
                        logger.info(f"已删除 Redis Stream: {queue_name}")
                        # 删除所有相关的消费者组
                        try:
                            await redis_client.xgroup_destroy(queue_name, "workers")
                            logger.info(f"已删除 Redis Stream 消费者组 '{queue_name}:workers'")
                        except Exception as e:
                            logger.warning(f"删除 Redis Stream 消费者组 '{queue_name}:workers' 失败或不存在: {e}")
                    except Exception as e:
                        logger.error(f"清空 Redis 队列 {queue_name} 时出错: {e}")
                await redis_client.close() # 关闭客户端连接
                logger.info("任务队列清空完成。")
        
        # ==== 端口冲突检测与自动清理 ====
        # 仅清理核心服务端口，MCP Server端口由 launcher 动态管理
        # 修复 Bug 8: 实例化 PortManager 并调用其方法
        port_manager_instance = PortManager()
        port_manager_instance.cleanup_ports([
            settings.TOOLSCORE_MCP_PORT,
            settings.TOOLSCORE_MONITORING_PORT,
            settings.TASK_API_PORT
        ])
        
        # === ToolScore 服务初始化 ===
        core_manager, toolscore_server, tool_library = await start_toolscore_services(redis_manager)

        # === 启动 ToolScore Monitoring API (8082端口) ===
        monitoring_api_server = ToolScoreMonitoringAPI(tool_library=tool_library, port=TOOLSCORE_MONITORING_PORT)
        # 将任务添加到列表中，以便在finally块中等待其完成
        background_tasks.append(asyncio.create_task(monitoring_api_server.start()))
        logger.info(f"✅ ToolScore Monitoring API 已启动在端口 {TOOLSCORE_MONITORING_PORT}")
        
        # === MCP Server 统一启动 ===
        mcp_client = MCPToolClient(toolscore_endpoint=settings.TOOLSCORE_MCP_WS_URL)
        mcp_launcher = MCPServerLauncher(unified_tool_library=tool_library, mcp_client=mcp_client)
        await mcp_launcher.launch_all_configured_servers()
        logger.info("✅ 所有 MCP Server 已通过统一启动器启动")

        # 启动 Task API (8000端口)
        task_api_server = await start_task_api_server() # start_task_api_server 内部已启动 Uvicorn Task

        # 显示启动成功消息和CLI提示
        await _display_startup_messages()
        
        # ================= 启动 Enhanced Reasoning Runtime =================
        enhanced_runtime = await start_enhanced_reasoning_runtime(redis_manager)

        # 显示启动成功消息和CLI提示

        # 保持服务运行，直到收到中断信号
        try:
            while True:
                await asyncio.sleep(1) # 每秒检查一次，保持主任务活跃，避免长时间无响应
        except asyncio.CancelledError:
            logger.info("主服务任务已取消。")
        except KeyboardInterrupt:
            logger.info("收到 Ctrl+C 停止信号，正在关闭服务...")
    
    except Exception as e:
        logger.error(f"启动失败: {e}")
        sys.exit(1)
    
    finally:
        # 清理资源
        try:
            # 取消并等待所有后台任务完成
            for task in background_tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        logger.info(f"后台任务 {task.get_name()} 已取消。")
                    except Exception as e:
                        logger.error(f"等待后台任务 {task.get_name()} 失败: {e}")

            if core_manager:
                await core_manager.stop()
            if toolscore_server:
                await toolscore_server.stop()
            if redis_manager:
                await stop_redis_manager(redis_manager)
            if mcp_launcher: # 停止所有由 launcher 启动的 MCP Server 进程
                await mcp_launcher.stop_all_servers()
            if task_api_server:
                logger.info("正在停止 Task API Server...")
                await task_api_server.shutdown() # Uvicorn Server 的停止逻辑
                logger.info("Task API Server 已停止。")
            if monitoring_api_server:
                await monitoring_api_server.stop()
            logger.info("Agent Data Platform 已停止")

            # 额外清理增强运行时
            if enhanced_runtime:
                from services import stop_enhanced_reasoning_runtime
                await stop_enhanced_reasoning_runtime()
            
            # 给予异步任务和连接一些时间来优雅地关闭
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"停止服务时出错: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("服务已停止")
    except Exception as e:
        logger.error(f"运行时错误: {e}")
        sys.exit(1)