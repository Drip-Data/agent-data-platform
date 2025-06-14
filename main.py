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
from dotenv import load_dotenv

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.path_utils import ensure_output_structure

# 创建必要的目录结构
ensure_output_structure()
os.makedirs(project_root / 'logs', exist_ok=True)
os.makedirs(project_root / 'config', exist_ok=True)
os.makedirs(project_root / 'data', exist_ok=True)

# 加载环境变量文件
def load_environment():
    """加载环境变量，优先级：.env > .env.local > 系统环境变量"""
    env_files = ['.env', '.env.local']
    loaded_any = False
    
    for env_file in env_files:
        env_path = project_root / env_file
        if env_path.exists():
            load_dotenv(env_path, override=False)
            loaded_any = True
            print(f"✅ 已加载环境变量文件: {env_file}")
    
    if not loaded_any:
        print("⚠️  未找到 .env 文件，将使用系统环境变量")
    
    return loaded_any

# 加载环境变量
load_environment()

# 检查并设置API密钥
def check_and_setup_api_keys():
    """检查并设置API密钥，按优先级自动选择可用的API"""
    api_providers = [
        ('GEMINI_API_KEY', 'Google Gemini'),
        ('DEEPSEEK_API_KEY', 'DeepSeek'),
        ('OPENAI_API_KEY', 'OpenAI'),
    ]
    
    available_apis = []
    for api_key, provider_name in api_providers:
        if os.getenv(api_key):
            available_apis.append(provider_name)
            print(f"✅ 发现 {provider_name} API 密钥")
    
    if available_apis:
        print(f"🚀 可用的API提供商: {', '.join(available_apis)}")
        return True
    else:
        print("❌ 错误: 未找到任何API密钥！")
        print("请设置以下任一API密钥：")
        for api_key, provider_name in api_providers:
            print(f"  - {api_key} ({provider_name})")
        print("💡 您可以创建 .env 文件或设置系统环境变量")
        print("💡 参考 .env.example 文件获取配置模板")
        return False

# 检查API密钥
if not check_and_setup_api_keys():
    print("⚠️  警告: 没有可用的LLM API密钥，某些功能可能无法正常工作")
    print("系统将继续启动，但建议配置API密钥以获得完整功能")

from core.toolscore.core_manager import CoreManager
from mcp_servers.python_executor_server.main import PythonExecutorMCPServer

# 配置日志 - 修复Windows控制台Unicode编码问题
import sys
import io

# 为Windows控制台设置UTF-8编码，修复emoji显示问题
if os.name == 'nt':
    # 设置控制台代码页为UTF-8
    try:
        import subprocess
        subprocess.run(['chcp', '65001'], shell=True, capture_output=True)
    except:
        pass
    
    # 重定向标准输出为UTF-8编码
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 配置日志，避免emoji字符导致的编码错误
class SafeFormatter(logging.Formatter):
    """安全的日志格式化器，处理Unicode字符"""
    def format(self, record):
        try:
            return super().format(record)
        except UnicodeEncodeError:
            # 移除emoji字符，替换为文字描述
            msg = record.getMessage()
            msg = msg.replace('✅', '[OK]').replace('❌', '[ERROR]').replace('⚠️', '[WARN]').replace('🚀', '[START]').replace('🔧', '[FIX]').replace('⏳', '[WAIT]').replace('🔄', '[PROC]')
            record.msg = msg
            record.args = ()
            return super().format(record)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/toolscore.log', mode='a', encoding='utf-8')
    ]
)

# 应用安全格式化器
for handler in logging.root.handlers:
    handler.setFormatter(SafeFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logger = logging.getLogger(__name__)

async def main():
    """主启动函数"""
    logger.info("启动 Agent Data Platform (无Docker版本)...")
    
    # 初始化变量，避免cleanup时的作用域错误
    core_manager = None
    toolscore_server = None
    enhanced_runtime = None
    redis_manager = None
    
    try:
        # === Redis管理器初始化 ===
        from core.redis_manager import RedisManager
        redis_manager = RedisManager()
        await redis_manager.ensure_redis_available()
        
        if redis_manager.is_fallback_mode():
            logger.warning("使用内存存储模式 - 数据将在重启后丢失")
        else:
            logger.info("Redis服务已就绪")
          # 显示当前可用的API密钥状态
        available_keys = []
        for key_name in ['GEMINI_API_KEY', 'DEEPSEEK_API_KEY', 'OPENAI_API_KEY']:
            if os.getenv(key_name):
                # 只显示前4位和后4位，中间用*号代替
                key_value = os.getenv(key_name)
                masked_key = f"{key_value[:4]}{'*' * (len(key_value) - 8)}{key_value[-4:]}" if len(key_value) > 8 else "****"
                available_keys.append(f"{key_name}: {masked_key}")
        
        if available_keys:
            logger.info(f"可用API密钥: {', '.join(available_keys)}")
        else:
            logger.warning("未发现任何API密钥，某些功能可能受限")        # ==== 端口冲突检测与自动清理 ====
        def _free_port(port: int):
            """查找占用指定端口的进程并强制杀掉"""
            try:
                # Windows使用netstat命令
                if os.name == 'nt':
                    import psutil
                    for proc in psutil.process_iter(['pid', 'name']):
                        try:
                            for conn in proc.connections():
                                if conn.laddr.port == port:
                                    logger.warning(f"端口 {port} 被进程 {proc.pid} ({proc.name()}) 占用，尝试终止…")
                                    proc.terminate()
                                    logger.info(f"已终止进程 {proc.pid} (端口 {port})")
                                    return
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                else:
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
            except (subprocess.CalledProcessError, ImportError):
                # 没有进程占用或psutil未安装
                pass

        # 清理常用端口，避免 "address already in use"
        for _port in (8081, 8082, 8083, 8000):
            _free_port(_port)
          # 初始化核心管理器
        core_manager = CoreManager(redis_manager=redis_manager)
        await core_manager.initialize()        # 创建并初始化工具库（避免循环依赖）
        from core.toolscore.unified_tool_library import UnifiedToolLibrary
        redis_url = redis_manager.get_redis_url()
        tool_library = UnifiedToolLibrary(redis_url=redis_url, redis_manager=redis_manager)
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
                from core.config_manager import get_ports_config
                
                ports_config = get_ports_config()
                toolscore_http_port = ports_config['mcp_servers']['toolscore_http']['port']
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f'http://localhost:{toolscore_http_port}/admin/mcp/register',
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
            logger.info("✅ Python Executor实例已传递给监控API")        # ================= 启动 Enhanced Reasoning Runtime =================
        async def start_enhanced_reasoning_runtime():
            """启动Enhanced Reasoning Runtime任务消费者（整合manual_start_consumer.py功能）"""
            nonlocal enhanced_runtime  # 声明使用外层作用域的变量
            try:
                logger.info("🚀 启动Enhanced Reasoning Runtime消费者...")
                  # 使用配置管理器获取端口配置
                from core.config_manager import get_ports_config
                try:
                    ports_config = get_ports_config()
                    toolscore_http_port = ports_config['mcp_servers']['toolscore_http']['port']
                    toolscore_mcp_port = ports_config['mcp_servers']['toolscore_mcp']['port']
                    
                    os.environ.setdefault('TOOLSCORE_HTTP_URL', f'http://localhost:{toolscore_http_port}')
                    os.environ.setdefault('TOOLSCORE_WS_URL', f'ws://localhost:{toolscore_http_port}')
                    os.environ.setdefault('TOOLSCORE_URL', f'ws://localhost:{toolscore_mcp_port}/websocket')
                except Exception as e:
                    logger.warning(f"配置加载失败，使用默认端口: {e}")
                    os.environ.setdefault('TOOLSCORE_HTTP_URL', 'http://localhost:8082')
                    os.environ.setdefault('TOOLSCORE_WS_URL', 'ws://localhost:8082')
                    os.environ.setdefault('TOOLSCORE_URL', 'ws://localhost:8081/websocket')

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
                
                # 🔧 修复：使用稳定的启动方式，传递redis_manager参数
                await start_runtime_service(enhanced_runtime, redis_manager=redis_manager)
                
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
        logger.info("按 Ctrl+C 停止服务")        # 保持服务运行
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
            if core_manager:
                await core_manager.stop()
            if toolscore_server:
                await toolscore_server.stop()
            if redis_manager:
                await redis_manager.stop()
            logger.info("Agent Data Platform 已停止")

            # 额外清理增强运行时
            try:
                if enhanced_runtime:
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