#!/usr/bin/env python3
"""
Agent Data Platform - Main Entry Point (无Docker版本)
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
import subprocess, signal

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.toolscore.core_manager import CoreManager
from mcp_servers.python_executor_server.main import PythonExecutorMCPServer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/toolscore.log', mode='a')
    ]
)

logger = logging.getLogger(__name__)

async def main():
    """主启动函数"""
    logger.info("启动 Agent Data Platform (无Docker版本)...")
    import os
    logger.info(f"GEMINI_API_KEY: {os.getenv('GEMINI_API_KEY')}")
    
    # ==== 端口冲突检测与自动清理 ====
    def _free_port(port: int):
        """查找占用指定端口的进程并强制杀掉"""
        try:
            # mac / linux 通用 lsof
            res = subprocess.check_output(["lsof", "-ti", f":{port}"]).decode().strip().splitlines()
            for pid in res:
                if pid:
                    logger.warning(f"端口 {port} 被进程 {pid} 占用，尝试终止…")
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                        logger.info(f"已杀死进程 {pid} (端口 {port})")
                    except Exception as e:
                        logger.error(f"终止进程 {pid} 失败: {e}")
        except subprocess.CalledProcessError:
            # 没有进程占用
            pass

    # 清理常用端口，避免 "address already in use"
    for _port in (8081, 8082, 8083, 8000):
        _free_port(_port)

    try:
        # 创建必要目录
        os.makedirs('logs', exist_ok=True)
        os.makedirs('output/trajectories', exist_ok=True)
        os.makedirs('config', exist_ok=True)
        os.makedirs('data', exist_ok=True)
        
        # 初始化核心管理器
        core_manager = CoreManager()
        await core_manager.initialize()
        
        # 创建并初始化工具库（避免循环依赖）
        from core.toolscore.unified_tool_library import UnifiedToolLibrary
        tool_library = UnifiedToolLibrary(redis_url="redis://localhost:6379")
        await tool_library.initialize()
        
        # 注入工具库到监控API
        await core_manager.set_tool_library_for_monitoring(tool_library)
        
        # 🔧 修复：启动 ToolScore MCP 服务器 (8081端口)
        from core.toolscore.mcp_server import MCPServer
        from core.toolscore.interfaces import ToolCapability, ToolType
        
        toolscore_capabilities = [
            ToolCapability(
                name="register_tool",
                description="注册新工具到工具库",
                parameters={
                    "tool_spec": {
                        "type": "object",
                        "description": "工具规范",
                        "required": True
                    }
                },
                examples=[{"tool_spec": {"tool_id": "example_tool", "name": "示例工具"}}]
            ),
            ToolCapability(
                name="list_tools",
                description="列出所有可用工具",
                parameters={},
                examples=[{}]
            ),
            ToolCapability(
                name="execute_tool",
                description="执行指定工具",
                parameters={
                    "tool_id": {
                        "type": "string",
                        "description": "工具ID",
                        "required": True
                    },
                    "action": {
                        "type": "string", 
                        "description": "工具动作",
                        "required": True
                    },
                    "parameters": {
                        "type": "object",
                        "description": "动作参数",
                        "required": False
                    }
                },
                examples=[{"tool_id": "python_executor_server", "action": "python_execute", "parameters": {"code": "print('hello')"}}]
            )
        ]
        
        toolscore_server = MCPServer(
            server_name="toolscore",
            server_id="toolscore-main-server", 
            description="统一工具注册与调用中心",
            capabilities=toolscore_capabilities,
            tool_type=ToolType.MCP_SERVER,
            endpoint="ws://0.0.0.0:8081/websocket",  # 修改为8081端口
            toolscore_endpoint=None  # 自己就是toolscore
        )
        
        # 设置工具库
        toolscore_server.unified_tool_library = tool_library
        
        # 启动 ToolScore MCP 服务器
        asyncio.create_task(toolscore_server.start())
        logger.info("ToolScore MCP Server 已启动在端口 8081")

        # 🔧 修复：直接注册Python Executor到工具库，避免WebSocket连接问题
        from core.toolscore.interfaces import MCPServerSpec
        
        python_executor_spec = MCPServerSpec(
            tool_id="python-executor-mcp-server",
            name="python_executor_server",
            description="Python代码执行和数据分析工具服务器",
            tool_type=ToolType.MCP_SERVER,
            capabilities=[
                ToolCapability(
                    name="python_execute",
                    description="执行Python代码",
                    parameters={
                        "code": {
                            "type": "string",
                            "description": "要执行的Python代码",
                            "required": True
                        },
                        "timeout": {
                            "type": "integer", 
                            "description": "执行超时时间（秒），默认30秒",
                            "required": False
                        }
                    },
                    examples=[
                        {"code": "print('Hello, World!')"},
                        {"code": "import math\nresult = math.sqrt(16)\nprint(f'平方根: {result}')"}
                    ]
                )
            ],
            endpoint="ws://localhost:8083/mcp"
        )
        
        # 直接注册到工具库
        registration_result = await tool_library.register_mcp_server(python_executor_spec)
        if registration_result.success:
            logger.info("✅ Python Executor 已直接注册到工具库")
            # 同步在MCP连接注册表中登记，确保execute_tool时可用
            tool_library.mcp_server_registry.register_server(python_executor_spec.tool_id, python_executor_spec.endpoint)
        else:
            logger.error(f"❌ Python Executor 注册失败: {registration_result.error}")

        # 🔧 新增：通过HTTP API额外注册Python Executor（来自register_python_executor.py的功能）
        async def register_python_executor_via_http():
            """通过HTTP API注册Python执行器（整合register_python_executor.py功能）"""
            server_spec_http = {
                "tool_id": "python_executor_server",
                "name": "Python 执行器",
                "description": "执行 Python 代码、数据分析和可视化",
                "endpoint": "ws://localhost:8083/mcp",
                "capabilities": [
                    {
                        "name": "python_execute",
                        "description": "执行Python代码",
                        "parameters": {
                            "code": {
                                "type": "string",
                                "description": "要执行的Python代码",
                                "required": True
                            },
                            "timeout": {
                                "type": "integer", 
                                "description": "执行超时时间（秒），默认30秒",
                                "required": False
                            }
                        },
                        "examples": [
                            {"code": "print('Hello, World!')"},
                            {"code": "import math\nresult = math.sqrt(16)\nprint(f'平方根: {result}')"}
                        ]
                    }
                ],
                "tags": ["python", "code", "execution", "data-analysis", "visualization"],
                "server_config": {},
                "connection_params": {"timeout": 30},
                "enabled": True
            }
            
            registration_data = {"server_spec": server_spec_http}
            
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        'http://localhost:8082/admin/mcp/register',
                        json=registration_data,
                        headers={'Content-Type': 'application/json'}
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            if result.get('success'):
                                logger.info("✅ Python 执行器已通过HTTP API额外注册成功!")
                                return True
                            else:
                                logger.error(f"❌ HTTP API注册失败: {result.get('message', 'Unknown error')}")
                        else:
                            error_text = await response.text()
                            logger.error(f"❌ HTTP API注册错误 {response.status}: {error_text}")
            except Exception as e:
                logger.error(f"❌ HTTP API注册时发生错误: {e}")
            return False

                    # 延迟执行HTTP注册，等待监控API完全启动
            async def delayed_http_registration():
                await asyncio.sleep(5)  # 增加等待时间，确保监控API完全就绪
                await register_python_executor_via_http()
            
            asyncio.create_task(delayed_http_registration())

        # === 设置输出目录环境变量，避免只读文件系统问题 ===
        os.environ.setdefault('OUTPUT_DIR', str(Path.cwd() / 'output' / 'trajectories'))

        # 启动 Python Executor MCP Server (禁用自动注册)
        python_executor_server = PythonExecutorMCPServer()
        # 修改为不尝试注册到ToolScore
        python_executor_server.toolscore_endpoint = None
        
        # 🔧 修复：将Python Executor实例传递给ToolScore，避免WebSocket连接问题
        toolscore_server.python_executor_server = python_executor_server
        
        asyncio.create_task(python_executor_server.run())
        logger.info("Python Executor MCP Server 已启动在端口 8083 (已手动注册)")

        # 启动 Task API (8000端口)
        from core.task_api import app as task_api_app
        import uvicorn
        
        # 启动Task API服务器
        task_api_config = uvicorn.Config(
            task_api_app,
            host="0.0.0.0",
            port=8000,
            log_level="info",
            access_log=True
        )
        task_api_server = uvicorn.Server(task_api_config)
        asyncio.create_task(task_api_server.serve())
        logger.info("Task API 已启动在端口 8000")

        # 启动服务
        await core_manager.start()
        
        # 🔧 修复：将Python Executor实例传递给监控API，实现直接调用
        if hasattr(core_manager, 'monitoring_api') and core_manager.monitoring_api:
            core_manager.monitoring_api.python_executor_server = python_executor_server
            logger.info("✅ Python Executor实例已传递给监控API")
        
        # ================= 启动 Enhanced Reasoning Runtime =================
        async def start_enhanced_reasoning_runtime():
            """启动Enhanced Reasoning Runtime任务消费者（整合manual_start_consumer.py功能）"""
            try:
                logger.info("🚀 启动Enhanced Reasoning Runtime消费者...")
                
                # 配置环境变量，使增强运行时能够正确连接当前实例的 ToolScore
                os.environ.setdefault('TOOLSCORE_HTTP_URL', 'http://localhost:8082')  # Monitoring / HTTP API
                os.environ.setdefault('TOOLSCORE_WS_URL', 'ws://localhost:8082')     # WebSocket for real-time updates
                os.environ.setdefault('TOOLSCORE_URL', 'ws://localhost:8081/websocket')  # MCP WebSocket

                from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime
                from core.task_manager import start_runtime_service

                enhanced_runtime = EnhancedReasoningRuntime()
                
                # 延迟启动Enhanced Runtime，确保所有服务都已就绪
                await asyncio.sleep(8)  # 等待核心服务完全启动
                
                logger.info("⏳ 初始化Enhanced Reasoning Runtime...")
                
                # 设置更合理的初始化超时时间
                await asyncio.wait_for(enhanced_runtime.initialize(), timeout=60.0)
                
                logger.info("✅ Enhanced Reasoning Runtime初始化完成")
                logger.info(f"Runtime ID: {enhanced_runtime.runtime_id}")
                
                logger.info("🔄 启动任务队列消费服务...")
                
                # 🔧 修复：使用稳定的启动方式，避免任务被销毁
                await start_runtime_service(enhanced_runtime)
                
            except asyncio.TimeoutError:
                logger.error("Enhanced Reasoning Runtime 初始化超时，将跳过启动，但其他服务正常运行")
            except Exception as e:
                logger.error(f"启动 Enhanced Reasoning Runtime 失败: {e}")
                logger.warning("Enhanced Reasoning Runtime 启动失败，但核心服务（ToolScore、Task API）仍可正常使用")
                import traceback
                traceback.print_exc()
        
        # 在后台启动Enhanced Reasoning Runtime
        asyncio.create_task(start_enhanced_reasoning_runtime())

        logger.info("Agent Data Platform 启动成功！")
        logger.info("服务地址: http://localhost:8080")
        logger.info("WebSocket地址: ws://localhost:8081")
        logger.info("监控地址: http://localhost:8082")
        logger.info("按 Ctrl+C 停止服务")
        
        # 保持服务运行
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到停止信号，正在关闭服务...")
            
    except Exception as e:
        logger.error(f"启动失败: {e}")
        sys.exit(1)
    finally:
        # 清理资源
        try:
            await core_manager.stop()
            await toolscore_server.stop()
            logger.info("Agent Data Platform 已停止")

            # 额外清理增强运行时
            try:
                if 'enhanced_runtime' in locals():
                    await enhanced_runtime.cleanup()
            except Exception as e:
                logger.error(f"清理 Enhanced Reasoning Runtime 出错: {e}")
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