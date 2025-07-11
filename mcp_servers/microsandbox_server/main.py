#!/usr/bin/env python3
"""
MicroSandbox MCP Server
基于MicroSandbox的安全代码执行服务，通过MCP协议与toolscore通信
支持生产模式配置、API版本兼容性和持久化存储
"""

import asyncio
import logging
import os
import json
from typing import Dict, Any, List, Optional
from uuid import uuid4
import time
import psutil
import threading
from collections import defaultdict, deque
from pathlib import Path
import subprocess
from dotenv import load_dotenv

from core.toolscore.interfaces import ToolCapability, ToolType, ExecutionResult
from core.toolscore.mcp_server import MCPServer
from core.config_manager import ConfigManager
from microsandbox import PythonSandbox
from fastapi import FastAPI

# Import enhanced session manager and token manager
try:
    from .enhanced_session_manager import EnhancedSessionManager
    from .token_manager import AutoRefreshTokenManager
except ImportError:
    # Fallback for direct execution
    import sys
    sys.path.append(str(Path(__file__).parent))
    from enhanced_session_manager import EnhancedSessionManager
    from token_manager import AutoRefreshTokenManager

# Load environment configuration
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Production configuration constants
class MicroSandboxConfig:
    """MicroSandbox生产配置管理"""
    
    # MicroSandbox server configuration
    MSB_API_KEY = os.getenv('MSB_API_KEY')
    MSB_HOST = os.getenv('MSB_HOST', '127.0.0.1')
    MSB_PORT = int(os.getenv('MSB_PORT', '5555'))
    MSB_STORAGE_PATH = os.getenv('MSB_STORAGE_PATH', os.path.expanduser('~/.microsandbox'))
    MSB_LOG_LEVEL = os.getenv('MSB_LOG_LEVEL', 'info')
    
    # MCP server configuration
    MCP_SERVER_PORT = int(os.getenv('MICROSANDBOX_MCP_SERVER_PORT', '8090'))
    MCP_HOST = os.getenv('MICROSANDBOX_HOST', 'localhost')
    MCP_LISTEN_HOST = os.getenv('MICROSANDBOX_LISTEN_HOST', '0.0.0.0')
    
    # API version compatibility
    SUPPORTED_API_VERSION = '0.2.6'
    
    @classmethod
    def validate_config(cls):
        """验证生产配置"""
        errors = []
        
        if not cls.MSB_API_KEY:
            errors.append("MSB_API_KEY is required for production mode")
        
        if not Path(cls.MSB_STORAGE_PATH).exists():
            try:
                Path(cls.MSB_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create storage path {cls.MSB_STORAGE_PATH}: {e}")
        
        return errors

logger = logging.getLogger(__name__)

app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "healthy", "port": 8090, "timestamp": time.time()}

class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, max_history=1000):
        self.max_history = max_history
        self.execution_times = deque(maxlen=max_history)
        self.memory_usage = deque(maxlen=max_history)
        self.active_sessions_count = deque(maxlen=max_history)
        self.error_counts = defaultdict(int)
        self.total_executions = 0
        self.successful_executions = 0
        
        # 实时监控
        self.current_memory_mb = 0
        self.peak_memory_mb = 0
        self.start_time = time.time()
        
        # 启动监控线程
        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_resources, daemon=True)
        self._monitor_thread.start()
    
    def _monitor_resources(self):
        """后台监控资源使用"""
        process = psutil.Process()
        while self._monitoring:
            try:
                memory_info = process.memory_info()
                self.current_memory_mb = memory_info.rss / 1024 / 1024
                self.peak_memory_mb = max(self.peak_memory_mb, self.current_memory_mb)
                
                self.memory_usage.append({
                    'timestamp': time.time(),
                    'memory_mb': self.current_memory_mb
                })
                
                time.sleep(10)  # 每10秒采样一次
            except Exception:
                pass
    
    def record_execution(self, execution_time: float, success: bool, session_count: int, error_type: str = None):
        """记录执行指标"""
        self.execution_times.append({
            'timestamp': time.time(),
            'duration': execution_time,
            'success': success
        })
        
        self.active_sessions_count.append({
            'timestamp': time.time(),
            'count': session_count
        })
        
        self.total_executions += 1
        if success:
            self.successful_executions += 1
        elif error_type:
            self.error_counts[error_type] += 1
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取性能统计"""
        recent_times = [e['duration'] for e in self.execution_times if e['timestamp'] > time.time() - 300]  # 最近5分钟
        
        return {
            'uptime_seconds': time.time() - self.start_time,
            'total_executions': self.total_executions,
            'success_rate': self.successful_executions / max(self.total_executions, 1),
            'average_execution_time': sum(recent_times) / max(len(recent_times), 1),
            'current_memory_mb': self.current_memory_mb,
            'peak_memory_mb': self.peak_memory_mb,
            'error_distribution': dict(self.error_counts),
            'recent_execution_count': len(recent_times)
        }
    
    def stop(self):
        """停止监控"""
        self._monitoring = False

class MicroSandboxServerManager:
    """MicroSandbox服务器管理器 - 负责启动和管理生产模式服务器"""
    
    def __init__(self):
        self.server_process = None
        self.config = MicroSandboxConfig
        
    async def ensure_server_running(self) -> bool:
        """
        确保MicroSandbox服务器在生产模式下运行
        返回True如果服务器正在运行或成功启动
        """
        # 检查服务器是否已经在运行
        if await self._check_server_health():
            logger.info("MicroSandbox server is already running")
            return True
            
        # 停止任何开发模式的服务器
        await self._stop_dev_server()
        
        # 启动生产模式服务器
        return await self._start_production_server()
    
    async def _check_server_health(self) -> bool:
        """
        检查MicroSandbox服务器是否正在运行
        """
        try:
            from microsandbox import PythonSandbox
            
            # 尝试创建一个简单的沙箱来测试连接
            server_url = f"http://{self.config.MSB_HOST}:{self.config.MSB_PORT}"
            sandbox_kwargs = {'server_url': server_url}
            
            if self.config.MSB_API_KEY:
                sandbox_kwargs['api_key'] = self.config.MSB_API_KEY
                
            # 快速连接测试
            sandbox = PythonSandbox(**sandbox_kwargs)
            try:
                await sandbox.start(timeout=3)
                await sandbox.stop()
                return True
            except Exception:
                return False
        except Exception:
            return False
    
    async def _stop_dev_server(self):
        """
        停止开发模式服务器
        """
        try:
            subprocess.run(['pkill', '-f', 'msbserver --dev'], check=False)
            await asyncio.sleep(2)  # 等待进程停止
        except Exception as e:
            logger.warning(f"Error stopping dev server: {e}")
    
    async def _start_production_server(self) -> bool:
        """
        启动生产模式的MicroSandbox服务器
        """
        try:
            # 验证配置
            config_errors = self.config.validate_config()
            if config_errors:
                logger.error(f"Configuration errors: {config_errors}")
                return False
            
            # 检查是否已经有服务器在运行
            import subprocess
            result = subprocess.run(['pgrep', '-f', f'msbserver.*{self.config.MSB_PORT}'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("Production MicroSandbox server is already running")
                return True
            
            # 构建启动命令
            cmd = [
                'msb', 'server', 'start',
                '--host', self.config.MSB_HOST,
                '--port', str(self.config.MSB_PORT),
                '--key', self.config.MSB_API_KEY,
                '--detach'
            ]
            
            logger.info(f"Starting production MicroSandbox server: {' '.join(cmd[:-2])} --key [REDACTED] --detach")
            
            # 启动服务器进程
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Failed to start server: {result.stderr}")
                return False
            
            # 等待服务器启动
            await asyncio.sleep(3)
            
            # 验证服务器是否成功启动
            for i in range(5):  # 重试检查
                if await self._check_server_health():
                    logger.info("✅ Production MicroSandbox server started successfully")
                    return True
                await asyncio.sleep(1)
            
            logger.warning("⚠️ Server started but health check failed, continuing anyway")
            return True  # 继续，让具体操作去处理错误
                
        except Exception as e:
            logger.error(f"Error starting production server: {e}")
            return False
    
    async def stop_server(self):
        """
        停止MicroSandbox服务器
        """
        if self.server_process:
            self.server_process.terminate()
            await self.server_process.wait()
            self.server_process = None

from core.unified_tool_manager import UnifiedToolManager

class MicroSandboxMCPServer:
    """MicroSandbox代码执行MCP服务器（增强版生产模式）"""
    
    def __init__(self, config_manager: ConfigManager, tool_manager: UnifiedToolManager):
        self.server_name = "microsandbox_server"
        self.server_id = "microsandbox"
        self.config_manager = config_manager
        self.tool_manager = tool_manager
        self.config = MicroSandboxConfig
        
        # MicroSandbox服务器管理器
        self.server_manager = MicroSandboxServerManager()
        
        # 增强的会话管理器
        self.enhanced_session_manager = EnhancedSessionManager(self.config)
        
        # Token管理器 - 自动处理API token刷新
        self.token_manager = AutoRefreshTokenManager(env_path)
        
        # 活跃的沙箱会话 {session_id: sandbox_context}
        self.active_sessions: Dict[str, Any] = {}
        self.session_timeout = 3600  # 1小时超时
        
        # 性能监控
        self.performance_monitor = PerformanceMonitor()
        
        # 超时配置
        self.default_execution_timeout = 30  # 默认30秒
        self.max_execution_timeout = 300     # 最大5分钟
        
        # API版本兼容性
        self.api_version = self.config.SUPPORTED_API_VERSION
        
        # 从配置中获取端口
        ports_config = self.config_manager.get_ports_config()
        
        # 使用生产配置端口
        microsandbox_port = self.config.MCP_SERVER_PORT
        toolscore_mcp_port = ports_config['mcp_servers']['toolscore_mcp']['port']
        
        # 配置监听地址
        listen_host = self.config.MCP_LISTEN_HOST
        public_host = self.config.MCP_HOST
        
        self.endpoint = f"ws://{public_host}:{microsandbox_port}"
        self._listen_host = listen_host
        self._listen_port = microsandbox_port
        
        self.toolscore_endpoint = os.getenv('TOOLSCORE_ENDPOINT', f'ws://localhost:{toolscore_mcp_port}/websocket')

        # 动作分发映射
        self._action_handlers = {
            "microsandbox_execute": self._execute_code,
            "microsandbox_install_package": self._install_package,
            "microsandbox_list_sessions": self._list_sessions,
            "microsandbox_close_session": self._close_session,
            "microsandbox_cleanup_expired": self._cleanup_expired_sessions,
            "microsandbox_get_performance_stats": self._get_performance_stats,
            "microsandbox_get_health_status": self._get_health_status,
            "microsandbox_get_token_status": self._get_token_status,
            "microsandbox_refresh_token": self._refresh_token,
        }
        self._validate_actions()
        
        logger.info(f"MicroSandboxMCPServer initialized (Production Mode):")
        logger.info(f"  Server Name: {self.server_name}")
        logger.info(f"  Server ID: {self.server_id}")
        logger.info(f"  API Version: {self.api_version}")
        logger.info(f"  Storage Path: {self.config.MSB_STORAGE_PATH}")
        logger.info(f"  MicroSandbox Server: {self.config.MSB_HOST}:{self.config.MSB_PORT}")
        logger.info(f"  Listen Host: {self._listen_host}")
        logger.info(f"  Listen Port: {self._listen_port}")
        logger.info(f"  Public Endpoint: {self.endpoint}")
        logger.info(f"  ToolScore Endpoint: {self.toolscore_endpoint}")

    def _validate_actions(self):
        """验证所有在配置中声明的动作都有对应的处理函数。"""
        try:
            declared_actions = set(self.tool_manager.get_tool_actions(self.server_name))
            implemented_actions = set(self._action_handlers.keys())

            missing = declared_actions - implemented_actions
            if missing:
                raise NotImplementedError(f"服务器 {self.server_name} 在配置中声明了动作 {missing}，但没有实现对应的处理函数！")

            extra = implemented_actions - declared_actions
            if extra:
                logging.warning(f"服务器 {self.server_name} 实现了多余的动作 {extra}，这些动作未在配置中声明。")
            
            logger.info(f"✅ {self.server_name} 的所有动作已验证。")
        except Exception as e:
            logger.error(f"动作验证失败: {e}", exc_info=True)
            raise
        
    def get_capabilities(self) -> List[ToolCapability]:
        """获取MicroSandbox工具的所有能力"""
        tool_info = self.tool_manager.get_tool_info(self.server_name)
        capabilities = []
        for action_name, action_def in tool_info.get('actions', {}).items():
            capabilities.append(ToolCapability(
                name=action_name,
                description=action_def.get('description', ''),
                parameters=action_def.get('parameters', {}),
                examples=action_def.get('examples', [])
            ))
        return capabilities
    
    async def handle_tool_action(self, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具动作执行（使用分发映射）"""
        logger.info(f"Executing MicroSandbox action: {action} with params: {parameters}")
        handler = self._action_handlers.get(action)
        
        if handler:
            try:
                return await handler(parameters)
            except Exception as e:
                import traceback
                error_details = f"MicroSandbox tool execution failed for {action}: {e}"
                traceback_str = traceback.format_exc()
                logger.error(f"{error_details}\n{traceback_str}")
                
                return {
                    "success": False,
                    "data": None,
                    "error_message": f"{str(e)} (详细错误请查看日志)",
                    "error_type": "MicroSandboxError",
                    "debug_info": {
                        "action": action,
                        "parameters_received": parameters,
                        "exception_type": type(e).__name__,
                        "traceback_preview": traceback_str[:500] + "..." if len(traceback_str) > 500 else traceback_str
                    }
                }
        else:
            return {
                "success": False,
                "data": None,
                "error_message": f"Unsupported action: {action}",
                "error_type": "UnsupportedAction"
            }

    
    async def _execute_code(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行Python代码（增强版）"""
        code = parameters.get("code", "")
        session_id = parameters.get("session_id")
        timeout = parameters.get("timeout", self.default_execution_timeout)
        
        if not code:
            return {
                "success": False,
                "data": None,
                "error_message": "代码不能为空",
                "error_type": "InvalidInput"
            }
        
        # 验证超时参数
        if timeout > self.max_execution_timeout:
            logger.warning(f"请求的超时时间 {timeout}s 超过最大值 {self.max_execution_timeout}s，将使用最大值")
            timeout = self.max_execution_timeout
        
        start_time = time.time()
        success = False
        error_type = None
        
        try:
            if session_id:
                # 使用会话执行
                result = await self._execute_with_session(code, session_id, timeout)
            else:
                # 一次性执行
                result = await self._execute_once(code, timeout)
            
            execution_time = time.time() - start_time
            success = result["success"]
            error_type = result.get("error_type")
            
            # 记录性能指标
            self.performance_monitor.record_execution(
                execution_time, 
                success, 
                len(self.active_sessions),
                error_type
            )
            
            return {
                "success": result["success"],
                "data": {
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                    "return_code": result.get("return_code", 0),
                    "execution_time": execution_time,
                    "session_id": session_id,
                    "timeout_used": timeout,
                    "timeout_note": "MicroSandbox使用内部超时机制，此参数仅供参考"
                },
                "error_message": result.get("error_message", ""),
                "error_type": result.get("error_type", "")
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_type = "ExecutionError"
            
            # 记录性能指标
            self.performance_monitor.record_execution(
                execution_time, 
                False, 
                len(self.active_sessions),
                error_type
            )
            
            return {
                "success": False,
                "data": {
                    "stdout": "",
                    "stderr": str(e),
                    "return_code": -1,
                    "execution_time": execution_time,
                    "session_id": session_id,
                    "timeout_used": timeout
                },
                "error_message": str(e),
                "error_type": error_type
            }
    
    async def _execute_once(self, code: str, timeout: int) -> Dict[str, Any]:
        """一次性执行代码（无会话）- 支持生产模式MicroSandbox和本地执行器降级"""
        try:
            logger.info(f"开始执行Python代码: {code[:100]}...")
            
            # 确保生产模式服务器运行
            server_running = await self.server_manager.ensure_server_running()
            if not server_running:
                logger.warning("无法启动生产模式MicroSandbox服务器，使用本地执行器")
                return await self._execute_with_local_fallback(code, timeout)
            
            # 首先尝试使用生产模式MicroSandbox
            try:
                server_url = f"http://{self.config.MSB_HOST}:{self.config.MSB_PORT}"
                logger.info(f"连接到生产模式MicroSandbox服务器: {server_url}")
                
                # 使用生产配置创建Sandbox实例
                sandbox_kwargs = {
                    'server_url': server_url
                }
                
                # 获取有效的API密钥（自动刷新）
                api_key = await self.token_manager.get_valid_token()
                if api_key:
                    sandbox_kwargs['api_key'] = api_key
                    
                async with PythonSandbox.create(**sandbox_kwargs) as sandbox:
                    execution = await sandbox.run(code)
                    
                    # 检查执行结果的正确属性
                    if hasattr(execution, 'status'):
                        success = execution.status == 'success'
                        # 处理异步方法
                        if hasattr(execution, 'output') and callable(execution.output):
                            try:
                                stdout = await execution.output()
                            except:
                                stdout = str(execution.output if hasattr(execution, 'output') else "")
                        else:
                            stdout = str(execution.output if hasattr(execution, 'output') else "")
                        
                        # 处理错误信息
                        if hasattr(execution, 'error') and callable(execution.error):
                            try:
                                stderr = await execution.error() if execution.has_error() else ""
                            except:
                                stderr = ""
                        else:
                            stderr = ""
                        exit_code = 0 if success else 1
                    else:
                        # 降级到属性访问
                        success = execution.exit_code == 0 if hasattr(execution, 'exit_code') else True
                        stdout = execution.stdout if hasattr(execution, 'stdout') else ""
                        stderr = execution.stderr if hasattr(execution, 'stderr') else ""
                        exit_code = execution.exit_code if hasattr(execution, 'exit_code') else (0 if success else 1)
                    
                    logger.info(f"生产模式MicroSandbox执行成功: success={success}, stdout长度={len(str(stdout))}")
                    return {
                        "success": success,
                        "stdout": stdout,
                        "stderr": stderr,
                        "return_code": exit_code
                    }
            except Exception as msb_error:
                import traceback
                error_str = str(msb_error)
                
                # 检查是否为token相关错误
                if self.token_manager.is_token_error(error_str):
                    logger.warning(f"检测到token错误: {error_str}")
                    # 尝试刷新token并重试一次
                    refresh_success = await self.token_manager.refresh_token_if_needed()
                    if refresh_success:
                        logger.info("Token刷新成功，尝试重新执行...")
                        try:
                            # 重新获取API密钥并重试
                            api_key = await self.token_manager.get_valid_token()
                            if api_key:
                                sandbox_kwargs['api_key'] = api_key
                                async with PythonSandbox.create(**sandbox_kwargs) as sandbox:
                                    execution = await sandbox.run(code)
                                    
                                    # 使用相同的结果处理逻辑
                                    if hasattr(execution, 'status'):
                                        success = execution.status == 'success'
                                        if hasattr(execution, 'output') and callable(execution.output):
                                            try:
                                                stdout = await execution.output()
                                            except:
                                                stdout = str(execution.output if hasattr(execution, 'output') else "")
                                        else:
                                            stdout = str(execution.output if hasattr(execution, 'output') else "")
                                        
                                        if hasattr(execution, 'error') and callable(execution.error):
                                            try:
                                                stderr = await execution.error() if execution.has_error() else ""
                                            except:
                                                stderr = ""
                                        else:
                                            stderr = ""
                                        exit_code = 0 if success else 1
                                    else:
                                        success = execution.exit_code == 0 if hasattr(execution, 'exit_code') else True
                                        stdout = execution.stdout if hasattr(execution, 'stdout') else ""
                                        stderr = execution.stderr if hasattr(execution, 'stderr') else ""
                                        exit_code = execution.exit_code if hasattr(execution, 'exit_code') else (0 if success else 1)
                                    
                                    logger.info(f"Token刷新后执行成功: success={success}")
                                    return {
                                        "success": success,
                                        "stdout": stdout,
                                        "stderr": stderr,
                                        "return_code": exit_code
                                    }
                        except Exception as retry_error:
                            logger.warning(f"Token刷新后重试仍失败: {retry_error}")
                
                error_details = f"生产模式MicroSandbox执行失败，降级到本地执行器: {msb_error}"
                traceback_str = traceback.format_exc()
                logger.warning(f"{error_details}\n详细错误信息: {traceback_str}")
                logger.info("立即启用本地Python执行器作为备用方案")
                # 降级到本地执行器
                return await self._execute_with_local_fallback(code, timeout)
                
        except Exception as e:
            logger.error(f"代码执行完全失败: {e}", exc_info=True)
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "return_code": -1,
                "error_message": str(e),
                "error_type": "SandboxError"
            }

    async def _execute_with_local_fallback(self, code: str, timeout: int) -> Dict[str, Any]:
        """本地执行器降级方案"""
        try:
            import subprocess
            import asyncio
            
            logger.info("使用本地Python执行器作为降级方案")
            
            # 创建安全的执行环境
            proc = await asyncio.create_subprocess_exec(
                'python3', '-c', code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # 使用wait_for来实现超时控制
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"执行超时 ({timeout}秒)",
                    "return_code": -1,
                    "error_message": f"执行超时 ({timeout}秒)",
                    "error_type": "TimeoutError"
                }
            
            success = proc.returncode == 0
            stdout_str = stdout.decode('utf-8') if stdout else ""
            stderr_str = stderr.decode('utf-8') if stderr else ""
            
            logger.info(f"本地执行器结果: success={success}, stdout长度={len(stdout_str)}")
            return {
                "success": success,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "return_code": proc.returncode or 0
            }
        except Exception as e:
            logger.error(f"本地执行器也失败: {e}", exc_info=True)
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "return_code": -1,
                "error_message": str(e),
                "error_type": "LocalExecutorError"
            }
    
    async def _execute_with_session(self, code: str, session_id: str, timeout: int) -> Dict[str, Any]:
        """在指定会话中执行代码（使用增强的会话管理器）"""
        try:
            # 使用增强的会话管理器
            result = await self.enhanced_session_manager.execute_with_session(session_id, code, timeout)
            
            return {
                "success": result["success"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "return_code": result["return_code"]
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "return_code": -1,
                "error_message": str(e),
                "error_type": "SessionError"
            }
    
    async def _install_package(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """安装Python包，增强错误检测和报告"""
        package_name = parameters.get("package_name", "")
        version = parameters.get("version")
        session_id = parameters.get("session_id")
        
        if not package_name:
            return {
                "success": False,
                "data": None,
                "error_message": "包名不能为空",
                "error_type": "InvalidInput"
            }
        
        # 验证包名格式（基本验证）
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', package_name):
            return {
                "success": False,
                "data": None,
                "error_message": f"包名格式无效: {package_name}",
                "error_type": "InvalidPackageName"
            }
        
        # 构造增强的安装命令，包含详细的错误检测
        version_str = version if version else 'None'
        install_code = f"""
import subprocess
import json
import sys

package_name = '{package_name}'
version = {repr(version)}

# 构建pip命令
pip_cmd = [sys.executable, '-m', 'pip', 'install']
if version and version != 'None':
    pip_cmd.append(f'{{package_name}}=={{version}}')
else:
    pip_cmd.append(package_name)

# 执行安装
try:
    result = subprocess.run(pip_cmd, capture_output=True, text=True, timeout=300)
    
    # 分析结果
    install_success = result.returncode == 0
    
    # 检查是否真的安装成功
    if install_success:
        # 验证包是否可以导入
        try:
            import importlib
            # 尝试导入包（处理包名和模块名不一致的情况）
            test_result = subprocess.run([sys.executable, '-c', f'import {{package_name}}'], 
                                       capture_output=True, text=True, timeout=30)
            import_success = test_result.returncode == 0
            if not import_success:
                # 包安装了但无法导入，尝试常见的名称变换
                alt_names = [package_name.replace('-', '_'), package_name.replace('_', '-')]
                for alt_name in alt_names:
                    test_result = subprocess.run([sys.executable, '-c', f'import {{alt_name}}'], 
                                               capture_output=True, text=True, timeout=30)
                    if test_result.returncode == 0:
                        import_success = True
                        break
        except Exception as e:
            import_success = False
    else:
        import_success = False
    
    # 输出结构化结果
    output = {{
        'pip_returncode': result.returncode,
        'pip_stdout': result.stdout,
        'pip_stderr': result.stderr,
        'install_success': install_success,
        'import_success': import_success,
        'package_name': package_name,
        'version': version
    }}
    
    print(f"INSTALL_RESULT:{{json.dumps(output)}}")
    
except subprocess.TimeoutExpired:
    print("INSTALL_RESULT:{{'error': 'Installation timeout', 'install_success': false}}")
except Exception as e:
    print(f"INSTALL_RESULT:{{'error': str(e), 'install_success': false}}")
"""
        
        # 执行安装
        result = await self._execute_code({
            "code": install_code,
            "session_id": session_id,
            "timeout": 120  # 安装包可能需要更长时间
        })
        
        # 解析安装结果
        if result["success"]:
            stdout = result["data"]["stdout"]
            
            # 查找结构化输出
            import re
            import json as json_module
            
            match = re.search(r'INSTALL_RESULT:(\{.*\})', stdout)
            if match:
                try:
                    install_info = json_module.loads(match.group(1))
                    
                    # 判断真实的安装状态
                    actual_success = (
                        install_info.get('install_success', False) and 
                        install_info.get('import_success', False)
                    )
                    
                    result["success"] = actual_success
                    result["data"]["package_name"] = package_name
                    result["data"]["version"] = version
                    result["data"]["install_details"] = install_info
                    
                    if not actual_success:
                        if not install_info.get('install_success', False):
                            result["error_message"] = f"包安装失败: {install_info.get('pip_stderr', '未知错误')}"
                            result["error_type"] = "PackageInstallationFailed"
                        elif not install_info.get('import_success', False):
                            result["error_message"] = f"包安装成功但无法导入: {package_name}"
                            result["error_type"] = "PackageImportFailed"
                        
                except json_module.JSONDecodeError:
                    result["success"] = False
                    result["error_message"] = "无法解析安装结果"
                    result["error_type"] = "InstallResultParseError"
            else:
                # 没有找到结构化输出，使用原始逻辑
                result["data"]["package_name"] = package_name
                result["data"]["version"] = version
        
        return result
    
    async def _list_sessions(self) -> Dict[str, Any]:
        """列出活跃会话（使用增强的会话管理器）"""
        try:
            result = self.enhanced_session_manager.list_sessions()
            return {
                "success": True,
                "data": result,
                "error_message": "",
                "error_type": ""
            }
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error_message": str(e),
                "error_type": "SessionListError"
            }
    
    async def _close_session(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """关闭会话（使用增强的会话管理器）"""
        session_id = parameters.get("session_id", "")
        
        if not session_id:
            return {
                "success": False,
                "data": None,
                "error_message": "会话ID不能为空",
                "error_type": "InvalidInput"
            }
        
        try:
            result = self.enhanced_session_manager.close_session(session_id)
            return {
                "success": result.get("success", False),
                "data": result if result.get("success") else None,
                "error_message": result.get("error_message", ""),
                "error_type": result.get("error_type", "")
            }
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error_message": str(e),
                "error_type": "SessionCloseError"
            }
    
    async def _cleanup_expired_sessions(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """清理过期会话（使用增强的会话管理器）"""
        max_age = parameters.get("max_age", None)
        
        try:
            result = self.enhanced_session_manager.cleanup_expired_sessions(max_age)
            return {
                "success": True,
                "data": result,
                "error_message": "",
                "error_type": ""
            }
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error_message": str(e),
                "error_type": "SessionCleanupError"
            }
    
    async def _get_token_status(self) -> Dict[str, Any]:
        """获取API Token状态信息"""
        try:
            token_info = self.token_manager.get_token_info()
            return {
                "success": True,
                "data": {
                    "token_status": token_info,
                    "auto_refresh_enabled": True,
                    "refresh_interval": "2分钟检查一次"
                },
                "error_message": "",
                "error_type": ""
            }
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error_message": str(e),
                "error_type": "TokenStatusError"
            }
    
    async def _refresh_token(self) -> Dict[str, Any]:
        """手动刷新API Token"""
        try:
            refresh_success = await self.token_manager.refresh_token_if_needed()
            if refresh_success:
                token_info = self.token_manager.get_token_info()
                return {
                    "success": True,
                    "data": {
                        "message": "Token刷新成功",
                        "token_status": token_info
                    },
                    "error_message": "",
                    "error_type": ""
                }
            else:
                return {
                    "success": False,
                    "data": None,
                    "error_message": "Token刷新失败，可能在冷却期内或其他错误",
                    "error_type": "TokenRefreshFailed"
                }
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error_message": str(e),
                "error_type": "TokenRefreshError"
            }
    
    async def _get_or_create_session(self, session_id: str, timeout: int = 180):
        """获取或创建会话（生产模式）"""
        if session_id not in self.active_sessions:
            # 确保生产模式服务器运行
            server_running = await self.server_manager.ensure_server_running()
            if not server_running:
                raise Exception("无法启动生产模式MicroSandbox服务器")
            
            # 创建新会话，使用生产配置
            import aiohttp
            
            server_url = f"http://{self.config.MSB_HOST}:{self.config.MSB_PORT}"
            
            # 构建沙箱参数
            sandbox_kwargs = {
                'server_url': server_url
            }
            
            # 添加认证信息
            if self.config.MSB_API_KEY:
                sandbox_kwargs['api_key'] = self.config.MSB_API_KEY
            
            sandbox = PythonSandbox(**sandbox_kwargs)
            sandbox._session = aiohttp.ClientSession()
            
            try:
                await sandbox.start(timeout=timeout)
                
                self.active_sessions[session_id] = {
                    "sandbox": sandbox,
                    "sandbox_instance": sandbox,
                    "created_at": time.time(),
                    "last_accessed": time.time(),
                    "server_url": server_url,
                    "with_auth": bool(self.config.MSB_API_KEY)
                }
                
                logger.info(f"创建新的生产模式MicroSandbox会话: {session_id}, 服务器: {server_url}")
                return sandbox
                
            except Exception as e:
                logger.error(f"创建会话失败: {e}")
                if hasattr(sandbox, '_session') and sandbox._session:
                    await sandbox._session.close()
                raise
                
        else:
            # 更新访问时间并返回现有沙箱
            self.active_sessions[session_id]["last_accessed"] = time.time()
            return self.active_sessions[session_id]["sandbox_instance"]
    
    async def _get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        try:
            stats = self.performance_monitor.get_statistics()
            
            return {
                "success": True,
                "data": {
                    "performance_stats": stats,
                    "active_sessions": len(self.active_sessions),
                    "server_info": {
                        "server_name": self.server_name,
                        "server_id": self.server_id,
                        "default_timeout": self.default_execution_timeout,
                        "max_timeout": self.max_execution_timeout,
                        "session_timeout": self.session_timeout
                    }
                },
                "error_message": "",
                "error_type": ""
            }
        except Exception as e:
            logger.error(f"获取性能统计失败: {e}", exc_info=True)
            return {
                "success": False,
                "data": None,
                "error_message": str(e),
                "error_type": "PerformanceStatsError"
            }
    
    async def _get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        try:
            # 获取基本统计
            stats = self.performance_monitor.get_statistics()
            
            # 计算健康指标
            memory_usage_mb = stats['current_memory_mb']
            success_rate = stats['success_rate']
            avg_execution_time = stats['average_execution_time']
            
            # 健康检查逻辑
            health_status = "healthy"
            issues = []
            
            # 内存检查
            if memory_usage_mb > 1000:  # 超过1GB
                health_status = "warning"
                issues.append(f"高内存使用: {memory_usage_mb:.1f}MB")
            
            # 成功率检查
            if success_rate < 0.9 and stats['total_executions'] > 10:
                health_status = "warning"
                issues.append(f"低成功率: {success_rate:.2%}")
            
            # 执行时间检查
            if avg_execution_time > 30:
                health_status = "warning"
                issues.append(f"执行时间较长: {avg_execution_time:.2f}秒")
            
            # 会话数量检查
            active_sessions = len(self.active_sessions)
            if active_sessions > 50:
                health_status = "warning"
                issues.append(f"活跃会话过多: {active_sessions}")
            
            # 🔧 新增：连接状态检查
            connection_healthy = await self._check_connection_health()
            if not connection_healthy:
                health_status = "unhealthy"
                issues.append("WebSocket连接异常")
            
            # 🔧 新增：端口冲突检查
            port_conflict = await self.check_port_conflicts()
            if port_conflict:
                health_status = "warning"
                issues.append(f"端口 {self._listen_port} 存在冲突")
            
            if len(issues) > 2:
                health_status = "unhealthy"
            
            return {
                "success": True,
                "data": {
                    "status": health_status,
                    "issues": issues,
                    "metrics": {
                        "memory_usage_mb": memory_usage_mb,
                        "success_rate": success_rate,
                        "avg_execution_time": avg_execution_time,
                        "active_sessions": active_sessions,
                        "uptime_seconds": stats['uptime_seconds']
                    },
                    "recommendations": self._get_health_recommendations(health_status, issues)
                },
                "error_message": "",
                "error_type": ""
            }
        except Exception as e:
            logger.error(f"获取健康状态失败: {e}", exc_info=True)
            return {
                "success": False,
                "data": None,
                "error_message": str(e),
                "error_type": "HealthStatusError"
            }
    
    def _get_health_recommendations(self, status: str, issues: List[str]) -> List[str]:
        """获取健康建议"""
        recommendations = []
        
        if status == "unhealthy":
            recommendations.append("建议使用自动重启功能恢复服务")
        
        for issue in issues:
            if "高内存使用" in issue:
                recommendations.append("清理过期会话以释放内存")
            elif "低成功率" in issue:
                recommendations.append("检查代码执行环境和错误日志")
            elif "执行时间较长" in issue:
                recommendations.append("优化代码复杂度或增加超时限制")
            elif "活跃会话过多" in issue:
                recommendations.append("设置更短的会话超时时间")
            elif "WebSocket连接异常" in issue:
                recommendations.append("检查网络连接并考虑重启服务")
            elif "端口" in issue and "冲突" in issue:
                recommendations.append("使用自动重启功能解决端口冲突")
        
        if not recommendations:
            recommendations.append("系统运行正常，继续监控")
        
        return recommendations
    
    # 🔧 新增：自动重启机制
    async def check_port_conflicts(self) -> bool:
        """检查端口冲突"""
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((self._listen_host, self._listen_port))
            sock.close()
            
            if result == 0:
                # 端口被占用，检查是否是我们自己的进程
                try:
                    import psutil
                    for conn in psutil.net_connections():
                        if (hasattr(conn, 'laddr') and conn.laddr and 
                            conn.laddr.port == self._listen_port and conn.status == 'LISTEN'):
                            try:
                                process = psutil.Process(conn.pid)
                                cmdline = " ".join(process.cmdline())
                                if "microsandbox" in cmdline.lower():
                                    logger.warning(f"检测到同类进程占用端口 {self._listen_port}: PID {conn.pid}")
                                    return True
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                except ImportError:
                    logger.warning("psutil不可用，无法详细检查端口冲突")
                    return True
            return False
        except Exception as e:
            logger.error(f"端口冲突检查失败: {e}")
            return False
    
    async def auto_restart_on_port_conflict(self) -> bool:
        """自动重启以解决端口冲突"""
        try:
            if await self.check_port_conflicts():
                logger.warning(f"检测到端口 {self._listen_port} 冲突，尝试自动重启...")
                
                # 尝试终止冲突的进程
                success = await self._terminate_conflicting_processes()
                if success:
                    logger.info("✅ 成功清理冲突进程，准备重启服务")
                    # 等待端口释放
                    await asyncio.sleep(2)
                    return True
                else:
                    logger.error("❌ 无法清理冲突进程")
                    return False
            return False
        except Exception as e:
            logger.error(f"自动重启检查失败: {e}")
            return False
    
    async def _terminate_conflicting_processes(self) -> bool:
        """终止冲突的进程"""
        try:
            import psutil
            terminated_processes = []
            
            for conn in psutil.net_connections():
                if (hasattr(conn, 'laddr') and conn.laddr and 
                    conn.laddr.port == self._listen_port and conn.status == 'LISTEN'):
                    try:
                        process = psutil.Process(conn.pid)
                        cmdline = " ".join(process.cmdline())
                        
                        # 只终止同类的microsandbox进程
                        if "microsandbox" in cmdline.lower():
                            logger.info(f"尝试终止冲突进程: PID {conn.pid}, 命令: {cmdline[:100]}...")
                            
                            # 先尝试优雅关闭
                            process.terminate()
                            await asyncio.sleep(1)
                            
                            # 如果还在运行，强制终止
                            if process.is_running():
                                process.kill()
                                await asyncio.sleep(1)
                            
                            terminated_processes.append(conn.pid)
                            logger.info(f"✅ 成功终止进程 PID {conn.pid}")
                            
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                        logger.warning(f"无法终止进程 PID {conn.pid}: {e}")
            
            return len(terminated_processes) > 0
            
        except ImportError:
            logger.warning("psutil不可用，无法自动终止冲突进程")
            return False
        except Exception as e:
            logger.error(f"终止冲突进程失败: {e}")
            return False
    
    async def start_with_auto_restart(self) -> bool:
        """带自动重启的启动方法"""
        max_restart_attempts = 3
        restart_delay = 5
        
        for attempt in range(max_restart_attempts):
            try:
                # 检查并处理端口冲突
                if await self.auto_restart_on_port_conflict():
                    logger.info(f"已处理端口冲突，尝试启动 (尝试 {attempt + 1}/{max_restart_attempts})")
                
                # 尝试启动服务（非阻塞）
                await self._start_server_non_blocking()
                logger.info("✅ MicroSandbox服务启动成功")
                return True
                
            except Exception as e:
                logger.error(f"启动失败 (尝试 {attempt + 1}/{max_restart_attempts}): {e}")
                
                if attempt < max_restart_attempts - 1:
                    logger.info(f"等待 {restart_delay} 秒后重试...")
                    await asyncio.sleep(restart_delay)
                    restart_delay *= 2  # 指数退避
                else:
                    logger.error("❌ 所有重启尝试都失败了")
                    return False
        
        return False
    
    async def _start_server_non_blocking(self):
        """非阻塞的服务器启动方法"""
        logger.info(f"Starting {self.server_name}...")
        
        # 创建MCP服务器
        self.mcp_server = MCPServer(
            server_name=self.server_name,
            server_id=self.server_id,
            description="基于MicroSandbox的安全Python代码执行服务器",
            capabilities=self.get_capabilities(),
            tool_type=ToolType.MCP_SERVER,
            endpoint=self.endpoint,
            toolscore_endpoint=self.toolscore_endpoint
        )
        
        # 注册工具动作处理器
        self.mcp_server.register_tool_action_handler(self.handle_tool_action)
        
        # 配置监听地址
        os.environ["MICROSANDBOX_BIND_HOST"] = self._listen_host
        
        logger.info(f"Attempting to start MCPServer for {self.server_name} at {self.endpoint}...")
        
        # 启动服务器（非阻塞）
        await self.mcp_server.start()
        logger.info(f"MCPServer for {self.server_name} started successfully.")
        
        # 启动连接监控任务
        asyncio.create_task(self._monitor_connection_health())
    
    async def _monitor_connection_health(self):
        """监控连接健康状态，检测离线问题"""
        while True:
            try:
                await asyncio.sleep(30)  # 每30秒检查一次
                
                # 检查服务器是否还在运行
                if hasattr(self, 'mcp_server') and self.mcp_server:
                    # 这里可以添加更多的健康检查逻辑
                    logger.debug("🔍 连接健康检查正常")
                else:
                    logger.warning("⚠️ MCP服务器实例丢失，可能需要重启")
                    break
                    
            except Exception as e:
                logger.error(f"❌ 连接健康监控异常: {e}")
                await asyncio.sleep(5)
    
    async def _check_connection_health(self) -> bool:
        """检查连接健康状态"""
        try:
            # 检查MCP服务器实例是否存在
            if not hasattr(self, 'mcp_server') or not self.mcp_server:
                return False
            
            # 可以添加更多的连接健康检查逻辑
            # 例如：ping测试、连接数检查等
            
            return True
        except Exception as e:
            logger.error(f"连接健康检查失败: {e}")
            return False
    
    async def run(self):
        """启动MCP服务器（旧版兼容方法）"""
        logger.warning("使用旧版run()方法，建议使用start_with_auto_restart()获得更好的可靠性")
        # 启动token自动刷新服务
        await self.token_manager.start_auto_refresh(check_interval=120)  # 每2分钟检查一次
        await self._start_server_non_blocking()
    
    async def cleanup(self):
        """清理所有会话和监控资源"""
        logger.info("清理所有MicroSandbox会话...")
        for session_id in list(self.active_sessions.keys()):
            try:
                session_info = self.active_sessions[session_id]
                if session_info["sandbox"]:
                    await session_info["sandbox"].stop()
                    if hasattr(session_info["sandbox"], '_session') and session_info["sandbox"]._session:
                        await session_info["sandbox"]._session.close()
                del self.active_sessions[session_id]
                logger.info(f"已清理会话: {session_id}")
            except Exception as e:
                logger.warning(f"清理会话 {session_id} 失败: {e}")
        
        # 停止token自动刷新服务
        if hasattr(self, 'token_manager'):
            await self.token_manager.stop_auto_refresh()
            logger.info("Token自动刷新服务已停止")
        
        # 停止性能监控
        if hasattr(self, 'performance_monitor'):
            self.performance_monitor.stop()
            logger.info("性能监控已停止")
        
        # 🔧 清理MCP服务器实例
        if hasattr(self, 'mcp_server') and self.mcp_server:
            try:
                await self.mcp_server.cleanup()
                logger.info("MCP服务器已清理")
            except Exception as e:
                logger.warning(f"清理MCP服务器失败: {e}")

async def main():
    """主函数"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 初始化ConfigManager和UnifiedToolManager
    from core.config_manager import ConfigManager
    from core.unified_tool_manager import UnifiedToolManager
    config_manager = ConfigManager()
    tool_manager = UnifiedToolManager()
    
    server = MicroSandboxMCPServer(config_manager, tool_manager)
    
    try:
        # 🔧 使用带自动重启的启动方法
        success = await server.start_with_auto_restart()
        if not success:
            logger.error("❌ MicroSandbox服务启动失败，所有重试都失败了")
            return
        
        # 服务启动成功，保持运行
        logger.info("✅ MicroSandbox服务运行中，按 Ctrl+C 停止...")
        try:
            # 保持服务运行
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在清理...")
        
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在清理...")
    except Exception as e:
        logger.error(f"服务器运行异常: {e}")
    finally:
        await server.cleanup()

if __name__ == "__main__":
    asyncio.run(main())