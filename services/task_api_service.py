import asyncio
import logging
import uvicorn
from core.task_management.task_api import app as task_api_app
from config import TASK_API_PORT

logger = logging.getLogger(__name__)

async def start_task_api_server():
    """
    启动 Task API 服务器。
    """
    logger.info("🚀 正在启动 Task API...")
    task_api_config = uvicorn.Config(
        task_api_app,
        host="0.0.0.0",
        port=TASK_API_PORT,
        log_level="info",
        access_log=True
    )
    task_api_server = uvicorn.Server(task_api_config)
    asyncio.create_task(task_api_server.serve())
    logger.info(f"✅ Task API 已启动在端口 {TASK_API_PORT}")
    return task_api_server

async def stop_task_api_server(task_api_server: uvicorn.Server):
    """
    停止 Task API 服务器。
    """
    if task_api_server:
        # Uvicorn Server 没有直接的 stop 方法，serve() 是阻塞的
        # 停止 Uvicorn 通常需要发送信号或通过其内部机制
        # 这里暂时不实现复杂的停止逻辑，因为其作为子任务运行
        logger.info("Task API Server 停止逻辑（如果需要）")