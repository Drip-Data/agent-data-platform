import asyncio
import json
import os
import sys # 新增导入
from typing import Dict, Any, List, Optional

from mcp_servers.base_mcp_server import BaseMCPServer
from core.toolscore.mcp.mcp_client import MCPToolClient
from core.toolscore.managers.unified_tool_library import UnifiedToolLibrary
import config.settings
from utils.port_manager import PortManager # 修复 Bug 3

class MCPServerLauncher:
    """
    用于动态加载、启动和注册 MCP Server 的类。
    """
    def __init__(self, unified_tool_library: UnifiedToolLibrary, mcp_client: MCPToolClient):
        self.unified_tool_library = unified_tool_library
        self.mcp_client = mcp_client
        self.running_servers: Dict[str, Any] = {} # 存储进程对象
        self.server_configs = self._load_server_configs()
        self.port_manager = PortManager()
        self._next_available_port = config.settings.MCP_SERVER_PORT_RANGE_START # 初始化下一个可用端口

    def _load_server_configs(self) -> List[Dict[str, Any]]: # 返回类型改为 List
        """从配置文件加载 MCP Server 配置。"""
        config_path = os.path.join(config.settings.CONFIG_DIR, "mcp_servers.json")
        if not os.path.exists(config_path):
            return [] # 返回空列表
        with open(config_path, 'r', encoding='utf-8') as f:
            # 假设 mcp_servers.json 包含一个列表
            return json.load(f)

    async def launch_and_register_server(self, server_name: str, server_module_path: str, host: str = "127.0.0.1"): # 移除 port 参数，因为是动态分配
        """
        动态加载、启动并注册一个 MCP Server。
        """
        if server_name in self.running_servers:
            print(f"MCP Server '{server_name}' 已经运行。")
            return

        try:
            # 分配端口
            port = self._next_available_port
            if not self.port_manager.check_port_available(port):
                # 如果当前端口被占用，尝试查找下一个可用端口
                port = self.port_manager.find_available_port(start_port=port,
                                           end_port=config.settings.MCP_SERVER_PORT_RANGE_END)
                if port is None:
                    raise Exception(f"无法找到 MCP Server '{server_name}' 的可用端口。")
            self._next_available_port = port + 1 # 更新下一个可用端口
            
            # 动态导入服务器模块并启动子进程
            command = [
                sys.executable, # Python 解释器路径
                "-m",
                server_module_path, # 模块路径，例如 mcp_servers.python_executor_server.main
                "--port",
                str(port)
            ]
            
            # 使用 asyncio.create_subprocess_exec 启动子进程
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=sys.stdout, # 重定向子进程的 stdout 到父进程的 stdout
                stderr=sys.stderr  # 重定向子进程的 stderr 到父进程的 stderr
            )
            
            self.running_servers[server_name] = process # 存储进程对象以便后续停止
            print(f"MCP Server '{server_name}' 已在 {host}:{port} 启动 (PID: {process.pid})。")

            # 可以在这里添加一个短暂的延迟，等待 MCP Server 启动并注册
            # 增加延迟，确保 MCP Server 有足够时间启动并注册
            await asyncio.sleep(5)

        except Exception as e:
            print(f"启动或注册 MCP Server '{server_name}' 失败: {e}")

    async def launch_all_configured_servers(self):
        """启动所有配置的 MCP Server。"""
        for server_config in self.server_configs: # 遍历列表
            server_name = server_config['name']
            module_path = server_config['module_path']
            # host 和 port 将由 launch_and_register_server 内部处理

            await self.launch_and_register_server(
                server_name=server_name,
                server_module_path=module_path,
            )

    async def stop_all_servers(self):
        """停止所有正在运行的 MCP Server 进程。"""
        for server_name, process in list(self.running_servers.items()):
            try:
                if process.returncode is None: # 检查进程是否仍在运行
                    print(f"正在停止 MCP Server '{server_name}' (PID: {process.pid})...")
                    process.terminate() # 尝试终止进程
                    await asyncio.wait_for(process.wait(), timeout=5) # 等待进程结束，设置超时
                    print(f"MCP Server '{server_name}' (PID: {process.pid}) 已停止。")
                else:
                    print(f"MCP Server '{server_name}' (PID: {process.pid}) 已退出，返回码: {process.returncode}。")
                del self.running_servers[server_name]
            except asyncio.TimeoutError:
                print(f"警告: MCP Server '{server_name}' (PID: {process.pid}) 终止超时，尝试杀死进程。")
                process.kill() # 如果终止超时，则强制杀死
                await process.wait()
                print(f"MCP Server '{server_name}' (PID: {process.pid}) 已被杀死。")
                del self.running_servers[server_name]
            except Exception as e:
                print(f"停止 MCP Server '{server_name}' (PID: {process.pid}) 失败: {e}")

# 示例用法 (在 main.py 中调用)
# async def main():
#     # ... 其他初始化
#     unified_tool_library = UnifiedToolLibrary(...) # 假设已初始化
#     mcp_client = MCPToolClient(...) # 假设已初始化
#     launcher = MCPServerLauncher(unified_tool_library, mcp_client)
#     await launcher.launch_all_configured_servers()
#     # ...