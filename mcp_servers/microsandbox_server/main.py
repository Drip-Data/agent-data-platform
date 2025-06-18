#!/usr/bin/env python3
"""
MicroSandbox MCP Server
基于MicroSandbox的安全代码执行服务，通过MCP协议与toolscore通信
"""

import asyncio
import logging
import os
import json
from typing import Dict, Any, List, Optional
from uuid import uuid4
import time

from core.toolscore.interfaces import ToolCapability, ToolType, ExecutionResult
from core.toolscore.mcp_server import MCPServer
from core.config_manager import ConfigManager
from microsandbox import PythonSandbox

logger = logging.getLogger(__name__)

class MicroSandboxMCPServer:
    """MicroSandbox代码执行MCP服务器"""
    
    def __init__(self, config_manager: ConfigManager):
        self.server_name = "microsandbox_server"
        self.server_id = "microsandbox-mcp-server"
        self.config_manager = config_manager
        
        # 活跃的沙箱会话 {session_id: sandbox_context}
        self.active_sessions: Dict[str, Any] = {}
        self.session_timeout = 3600  # 1小时超时
        
        # 从配置中获取端口
        ports_config = self.config_manager.get_ports_config()
        
        # 检查动态分配的端口
        dynamic_port = os.getenv('MICROSANDBOX_MCP_SERVER_PORT')
        if dynamic_port:
            microsandbox_port = int(dynamic_port)
            logger.info(f"使用动态分配端口: {microsandbox_port}")
        else:
            microsandbox_port = ports_config['mcp_servers']['microsandbox_mcp']['port']
            logger.info(f"使用配置文件端口: {microsandbox_port}")
        
        toolscore_mcp_port = ports_config['mcp_servers']['toolscore_mcp']['port']
        
        # 配置监听地址
        listen_host = os.getenv("MICROSANDBOX_LISTEN_HOST", "0.0.0.0")
        public_host = os.getenv("MICROSANDBOX_HOST", "localhost")
        
        self.endpoint = f"ws://{public_host}:{microsandbox_port}"
        self._listen_host = listen_host
        self._listen_port = microsandbox_port
        
        self.toolscore_endpoint = os.getenv('TOOLSCORE_ENDPOINT', f'ws://localhost:{toolscore_mcp_port}/websocket')
        
        logger.info(f"MicroSandboxMCPServer initialized:")
        logger.info(f"  Server Name: {self.server_name}")
        logger.info(f"  Server ID: {self.server_id}")
        logger.info(f"  Listen Host: {self._listen_host}")
        logger.info(f"  Listen Port: {self._listen_port}")
        logger.info(f"  Public Endpoint: {self.endpoint}")
        logger.info(f"  ToolScore Endpoint: {self.toolscore_endpoint}")
        
    def get_capabilities(self) -> List[ToolCapability]:
        """获取MicroSandbox工具的所有能力"""
        return [
            ToolCapability(
                name="microsandbox_execute",
                description="在MicroSandbox安全环境中执行Python代码",
                parameters={
                    "code": {
                        "type": "string",
                        "description": "要执行的Python代码",
                        "required": True
                    },
                    "session_id": {
                        "type": "string",
                        "description": "会话ID，用于多轮执行和状态保持",
                        "required": False
                    },
                    "timeout": {
                        "type": "integer", 
                        "description": "执行超时时间（秒），默认30秒",
                        "required": False
                    }
                },
                examples=[
                    {"code": "print('Hello from MicroSandbox!')"},
                    {"code": "import math\\nresult = math.sqrt(16)\\nprint(f'平方根: {result}')", "timeout": 10},
                    {"code": "x = 42", "session_id": "my-session"},
                    {"code": "print(f'x = {x}')", "session_id": "my-session"}
                ]
            ),
            ToolCapability(
                name="microsandbox_install_package",
                description="在MicroSandbox环境中安装Python包",
                parameters={
                    "package_name": {
                        "type": "string",
                        "description": "要安装的包名",
                        "required": True
                    },
                    "version": {
                        "type": "string",
                        "description": "指定版本号",
                        "required": False
                    },
                    "session_id": {
                        "type": "string",
                        "description": "会话ID",
                        "required": False
                    }
                },
                examples=[
                    {"package_name": "requests"},
                    {"package_name": "numpy", "version": "1.21.0"},
                    {"package_name": "pandas", "session_id": "data-analysis"}
                ]
            ),
            ToolCapability(
                name="microsandbox_list_sessions",
                description="列出当前活跃的沙箱会话",
                parameters={},
                examples=[{}]
            ),
            ToolCapability(
                name="microsandbox_close_session",
                description="关闭指定的沙箱会话",
                parameters={
                    "session_id": {
                        "type": "string",
                        "description": "要关闭的会话ID",
                        "required": True
                    }
                },
                examples=[
                    {"session_id": "my-session"}
                ]
            ),
            ToolCapability(
                name="microsandbox_cleanup_expired",
                description="清理过期的沙箱会话",
                parameters={
                    "max_age": {
                        "type": "integer",
                        "description": "最大会话年龄（秒），默认为配置的超时时间",
                        "required": False
                    }
                },
                examples=[
                    {},
                    {"max_age": 1800}
                ]
            )
        ]
    
    async def handle_tool_action(self, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具动作执行"""
        try:
            logger.info(f"Executing MicroSandbox action: {action} with params: {parameters}")
            
            if action == "microsandbox_execute":
                return await self._execute_code(parameters)
                
            elif action == "microsandbox_install_package":
                return await self._install_package(parameters)
                
            elif action == "microsandbox_list_sessions":
                return await self._list_sessions()
                
            elif action == "microsandbox_close_session":
                return await self._close_session(parameters)
                
            elif action == "microsandbox_cleanup_expired":
                return await self._cleanup_expired_sessions(parameters)
                
            else:
                return {
                    "success": False,
                    "data": None,
                    "error_message": f"Unsupported action: {action}",
                    "error_type": "UnsupportedAction"
                }
                
        except Exception as e:
            logger.error(f"MicroSandbox tool execution failed for {action}: {e}", exc_info=True)
            return {
                "success": False,
                "data": None,
                "error_message": str(e),
                "error_type": "MicroSandboxError"
            }
    
    async def _execute_code(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行Python代码"""
        code = parameters.get("code", "")
        session_id = parameters.get("session_id")
        timeout = parameters.get("timeout", 30)
        
        if not code:
            return {
                "success": False,
                "data": None,
                "error_message": "代码不能为空",
                "error_type": "InvalidInput"
            }
        
        start_time = time.time()
        
        try:
            if session_id:
                # 使用会话执行
                result = await self._execute_with_session(code, session_id, timeout)
            else:
                # 一次性执行
                result = await self._execute_once(code, timeout)
            
            execution_time = time.time() - start_time
            
            return {
                "success": result["success"],
                "data": {
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                    "return_code": result.get("return_code", 0),
                    "execution_time": execution_time,
                    "session_id": session_id
                },
                "error_message": result.get("error_message", ""),
                "error_type": result.get("error_type", "")
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            return {
                "success": False,
                "data": {
                    "stdout": "",
                    "stderr": str(e),
                    "return_code": -1,
                    "execution_time": execution_time,
                    "session_id": session_id
                },
                "error_message": str(e),
                "error_type": "ExecutionError"
            }
    
    async def _execute_once(self, code: str, timeout: int) -> Dict[str, Any]:
        """一次性执行代码（无会话）"""
        try:
            logger.info(f"开始创建MicroSandbox实例...")
            async with PythonSandbox.create() as sandbox:
                logger.info(f"MicroSandbox实例创建成功，开始执行代码: {code[:100]}...")
                # MicroSandbox不支持timeout参数，使用默认超时
                result = await sandbox.run(code)
                logger.info(f"代码执行完成，获取输出...")
                output = await result.output()
                
                logger.info(f"代码执行结果: exit_code={output.exit_code}, stdout长度={len(output.stdout)}")
                return {
                    "success": output.exit_code == 0,
                    "stdout": output.stdout,
                    "stderr": output.stderr,
                    "return_code": output.exit_code
                }
        except Exception as e:
            logger.error(f"MicroSandbox执行出错: {e}", exc_info=True)
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "return_code": -1,
                "error_message": str(e),
                "error_type": "SandboxError"
            }
    
    async def _execute_with_session(self, code: str, session_id: str, timeout: int) -> Dict[str, Any]:
        """在指定会话中执行代码"""
        try:
            # 获取或创建会话
            sandbox = await self._get_or_create_session(session_id)
            
            # 执行代码  
            # MicroSandbox不支持timeout参数，使用默认超时
            result = await sandbox.run(code)
            output = await result.output()
            
            # 更新会话访问时间
            if session_id in self.active_sessions:
                self.active_sessions[session_id]["last_accessed"] = time.time()
            
            return {
                "success": output.exit_code == 0,
                "stdout": output.stdout,
                "stderr": output.stderr,
                "return_code": output.exit_code
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
        """安装Python包"""
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
        
        # 构造安装命令
        install_code = f"import subprocess; result = subprocess.run(['pip', 'install', '{package_name}"
        if version:
            install_code += f"=={version}"
        install_code += "'], capture_output=True, text=True); print(f'安装结果: {result.returncode}'); print(result.stdout); print(result.stderr)"
        
        # 执行安装
        result = await self._execute_code({
            "code": install_code,
            "session_id": session_id,
            "timeout": 120  # 安装包可能需要更长时间
        })
        
        if result["success"]:
            result["data"]["package_name"] = package_name
            result["data"]["version"] = version
            
        return result
    
    async def _list_sessions(self) -> Dict[str, Any]:
        """列出活跃会话"""
        sessions = []
        current_time = time.time()
        
        for session_id, session_info in self.active_sessions.items():
            sessions.append({
                "session_id": session_id,
                "created_at": session_info["created_at"],
                "last_accessed": session_info["last_accessed"],
                "uptime": current_time - session_info["created_at"],
                "idle_time": current_time - session_info["last_accessed"]
            })
        
        return {
            "success": True,
            "data": {
                "sessions": sessions,
                "total_count": len(sessions)
            },
            "error_message": "",
            "error_type": ""
        }
    
    async def _close_session(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """关闭会话"""
        session_id = parameters.get("session_id", "")
        
        if not session_id:
            return {
                "success": False,
                "data": None,
                "error_message": "会话ID不能为空",
                "error_type": "InvalidInput"
            }
        
        if session_id not in self.active_sessions:
            return {
                "success": False,
                "data": None,
                "error_message": f"会话不存在: {session_id}",
                "error_type": "SessionNotFound"
            }
        
        try:
            # 关闭沙箱
            session_info = self.active_sessions[session_id]
            await session_info["sandbox"].__aexit__(None, None, None)
            
            # 移除会话记录
            del self.active_sessions[session_id]
            
            return {
                "success": True,
                "data": {"session_id": session_id, "message": "会话已关闭"},
                "error_message": "",
                "error_type": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error_message": f"关闭会话失败: {str(e)}",
                "error_type": "SessionCloseError"
            }
    
    async def _cleanup_expired_sessions(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """清理过期会话"""
        max_age = parameters.get("max_age", self.session_timeout)
        current_time = time.time()
        expired_sessions = []
        
        for session_id, session_info in list(self.active_sessions.items()):
            if current_time - session_info["last_accessed"] > max_age:
                try:
                    await session_info["sandbox"].__aexit__(None, None, None)
                    del self.active_sessions[session_id]
                    expired_sessions.append(session_id)
                except Exception as e:
                    logger.warning(f"清理会话 {session_id} 失败: {e}")
        
        return {
            "success": True,
            "data": {
                "cleaned_sessions": expired_sessions,
                "count": len(expired_sessions)
            },
            "error_message": "",
            "error_type": ""
        }
    
    async def _get_or_create_session(self, session_id: str):
        """获取或创建会话"""
        if session_id not in self.active_sessions:
            # 创建新会话
            sandbox_context = PythonSandbox.create()
            sandbox = await sandbox_context.__aenter__()
            
            self.active_sessions[session_id] = {
                "sandbox": sandbox_context,
                "sandbox_instance": sandbox,
                "created_at": time.time(),
                "last_accessed": time.time()
            }
            
            logger.info(f"创建新的MicroSandbox会话: {session_id}")
            return sandbox
        else:
            # 更新访问时间并返回现有沙箱
            self.active_sessions[session_id]["last_accessed"] = time.time()
            return self.active_sessions[session_id]["sandbox_instance"]
    
    async def run(self):
        """启动MCP服务器"""
        logger.info(f"Starting {self.server_name}...")
        
        # 创建MCP服务器
        mcp_server = MCPServer(
            server_name=self.server_name,
            server_id=self.server_id,
            description="基于MicroSandbox的安全Python代码执行服务器",
            capabilities=self.get_capabilities(),
            tool_type=ToolType.MCP_SERVER,
            endpoint=self.endpoint,
            toolscore_endpoint=self.toolscore_endpoint
        )
        
        # 注册工具动作处理器
        mcp_server.register_tool_action_handler(self.handle_tool_action)
        
        # 配置监听地址
        os.environ["MICROSANDBOX_BIND_HOST"] = self._listen_host
        
        logger.info(f"Attempting to start MCPServer for {self.server_name} at {self.endpoint}...")
        try:
            await mcp_server.start()
            logger.info(f"MCPServer for {self.server_name} started successfully.")
        except Exception as e:
            logger.error(f"Failed to start MCPServer for {self.server_name}: {e}", exc_info=True)
            raise
    
    async def cleanup(self):
        """清理所有会话"""
        logger.info("清理所有MicroSandbox会话...")
        for session_id in list(self.active_sessions.keys()):
            try:
                session_info = self.active_sessions[session_id]
                await session_info["sandbox"].__aexit__(None, None, None)
                del self.active_sessions[session_id]
                logger.info(f"已清理会话: {session_id}")
            except Exception as e:
                logger.warning(f"清理会话 {session_id} 失败: {e}")

async def main():
    """主函数"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 初始化ConfigManager
    from core.config_manager import ConfigManager
    config_manager = ConfigManager()
    
    server = MicroSandboxMCPServer(config_manager)
    
    try:
        await server.run()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在清理...")
        await server.cleanup()
    except Exception as e:
        logger.error(f"服务器启动失败: {e}")
        await server.cleanup()
        raise

if __name__ == "__main__":
    asyncio.run(main())