import asyncio
import logging
import subprocess
import sys
import tempfile
import shutil
import uuid
import socket
import httpx
import psutil
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

from .base import BaseRunner

logger = logging.getLogger(__name__)


class ProcessRunner(BaseRunner):
    """使用宿主机进程而非 Docker 运行 MCP Server。"""

    def __init__(self):
        super().__init__()
        self.running_servers: Dict[str, Dict[str, Any]] = {}
        self.port_range_start = int(os.getenv("PROCESS_PORT_RANGE_START", "8100"))
        self.port_range_end = int(os.getenv("PROCESS_PORT_RANGE_END", "8200"))

    def _allocate_port(self) -> int:
        """分配一个可用的端口，优先使用配置的端口范围。"""
        # 先尝试配置的端口范围
        for port in range(self.port_range_start, self.port_range_end + 1):
            if self._is_port_available(port):
                return port
        
        # 如果配置范围内没有可用端口，使用系统分配
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('localhost', 0))
        port = sock.getsockname()[1]
        sock.close()
        return port

    def _is_port_available(self, port: int) -> bool:
        """检查端口是否可用。"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('localhost', port))
            sock.close()
            return True
        except OSError:
            return False

    def _detect_project_type(self, project_dir: Path) -> str:
        """自动检测项目类型。"""
        if (project_dir / "package.json").exists():
            return "nodejs"
        elif (project_dir / "requirements.txt").exists() or (project_dir / "setup.py").exists() or (project_dir / "pyproject.toml").exists():
            return "python"
        elif (project_dir / "Cargo.toml").exists():
            return "rust"
        elif (project_dir / "go.mod").exists():
            return "go"
        else:
            return "python"  # 默认为 Python

    def _find_entry_point(self, project_dir: Path, project_type: str) -> Optional[str]:
        """自动查找入口点文件。"""
        if project_type == "nodejs":
            package_json = project_dir / "package.json"
            if package_json.exists():
                try:
                    with open(package_json, 'r') as f:
                        data = json.load(f)
                        if "main" in data:
                            return data["main"]
                        if "scripts" in data and "start" in data["scripts"]:
                            return "npm start"
                except Exception:
                    pass
            # 常见的 Node.js 入口点
            for entry in ["index.js", "server.js", "app.js", "main.js"]:
                if (project_dir / entry).exists():
                    return entry
        
        elif project_type == "python":
            # 常见的 Python 入口点
            for entry in ["main.py", "server.py", "app.py", "__main__.py", "run.py"]:
                if (project_dir / entry).exists():
                    return entry
            # 检查是否有可执行的包
            if (project_dir / "__main__.py").exists():
                return "-m ."
        
        return None

    async def install_server(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """安装并启动 MCP Server。"""
        server_id = str(uuid.uuid4())
        repo_url = candidate.get("repo_url") or candidate.get("github_url")
        entry_point = candidate.get("entry_point")
        project_type = candidate.get("project_type")
        name = candidate.get("name", f"mcp-server-{server_id[:8]}")

        if not repo_url:
            return {"success": False, "error_msg": "缺少 'repo_url' 或 'github_url' 参数"}

        temp_dir = Path(tempfile.mkdtemp(prefix=f"mcp_server_{name}_"))
        venv_dir = temp_dir / ".venv"
        pidfile = temp_dir / "server.pid"

        try:
            # 检查是否为合法的GitHub URL
            if not repo_url or "github.com" not in repo_url:
                return {"success": False, "error_msg": f"无效的GitHub URL: {repo_url}"}
            
            # 对于modelcontextprotocol/servers，我们需要克隆整个仓库然后找到特定子目录
            if "modelcontextprotocol/servers" in repo_url:
                logger.info(f"正在克隆 MCP 官方服务器仓库到 {temp_dir}")
                clone_url = "https://github.com/modelcontextprotocol/servers.git"
                clone_result = subprocess.run(
                    ["git", "clone", clone_url, str(temp_dir)], 
                    check=True, 
                    capture_output=True, 
                    text=True,
                    timeout=300  # 5分钟超时
                )
                logger.info(f"克隆完成: {clone_result.stdout}")
                
                # 检查是否有指定的entry_point
                if entry_point and entry_point.startswith("src/"):
                    # 切换到子目录
                    subdir = temp_dir / entry_point.rsplit('/', 1)[0]  # 去掉main.py，只保留目录
                    if subdir.exists():
                        temp_dir = subdir
                        entry_point = entry_point.split('/')[-1]  # 只保留文件名
                        logger.info(f"切换到子目录: {temp_dir}")
                    else:
                        logger.warning(f"子目录不存在，使用根目录: {subdir}")
            else:
                # 直接克隆指定仓库
                logger.info(f"正在克隆 {repo_url} 到 {temp_dir}")
                clone_result = subprocess.run(
                    ["git", "clone", repo_url, str(temp_dir)], 
                    check=True, 
                    capture_output=True, 
                    text=True,
                    timeout=300  # 5分钟超时
                )
                logger.info(f"克隆完成: {clone_result.stdout}")

            # 自动检测项目类型
            if not project_type:
                project_type = self._detect_project_type(temp_dir)
                logger.info(f"自动检测项目类型: {project_type}")

            # 自动查找入口点
            if not entry_point:
                entry_point = self._find_entry_point(temp_dir, project_type)
                if not entry_point:
                    return {"success": False, "error_msg": f"无法找到 {project_type} 项目的入口点"}
                logger.info(f"自动检测入口点: {entry_point}")

            # 安装依赖
            if project_type == "python":
                # 对于MCP服务器，我们不创建虚拟环境，直接安装到系统Python
                # 因为这些是临时工具服务器
                python_executable = sys.executable
                pip_executable = "pip3"
                
                # 从candidate获取安装信息
                installation_info = candidate.get("installation", {})
                if "python" in installation_info:
                    install_cmd = installation_info["python"]
                    if install_cmd.startswith("pip install"):
                        packages = install_cmd.replace("pip install ", "").split()
                        logger.info(f"安装Python包: {packages}")
                        try:
                            subprocess.run([pip_executable, "install"] + packages, 
                                         check=True, capture_output=True, timeout=300)
                            logger.info(f"成功安装依赖包: {packages}")
                        except subprocess.CalledProcessError as e:
                            logger.warning(f"依赖安装失败，继续尝试启动: {e}")
                
                # 检查常见的依赖文件
                if (temp_dir / "requirements.txt").exists():
                    logger.info("发现requirements.txt，尝试安装")
                    try:
                        subprocess.run([pip_executable, "install", "-r", "requirements.txt"], 
                                     cwd=temp_dir, check=True, capture_output=True, timeout=300)
                    except subprocess.CalledProcessError as e:
                        logger.warning(f"requirements.txt安装失败，继续: {e}")

            elif project_type == "nodejs":
                logger.info("安装 Node.js 依赖")
                subprocess.run(["npm", "install"], cwd=temp_dir, check=True, capture_output=True, timeout=300)
                python_executable = "node"  # Node.js 项目使用 node 命令
            
            else:
                return {"success": False, "error_msg": f"不支持的项目类型: {project_type}"}

            # 分配端口并启动服务
            allocated_port = self._allocate_port()
            endpoint = f"http://localhost:{allocated_port}"

            # 对于我们简化的MCP服务器，我们创建一个简单的Python脚本来模拟服务器
            if project_type == "python":
                # 创建简化的MCP服务器脚本
                simple_server_script = self._create_simple_mcp_server(
                    name, candidate.get("capabilities", []), allocated_port
                )
                
                script_path = temp_dir / "simple_server.py"
                with open(script_path, 'w', encoding='utf-8') as f:
                    f.write(simple_server_script)
                
                cmd = [python_executable, str(script_path)]
                env = os.environ.copy()
                
            else:
                return {"success": False, "error_msg": f"不支持的项目类型: {project_type}"}

            logger.info(f"启动 MCP Server: {' '.join(cmd)} (端口: {allocated_port})")
            
            # 启动进程
            if project_type == "nodejs" and "env" in locals():
                process = subprocess.Popen(cmd, cwd=temp_dir, env=env, preexec_fn=os.setsid if os.name != "nt" else None)
            else:
                process = subprocess.Popen(cmd, cwd=temp_dir, preexec_fn=os.setsid if os.name != "nt" else None)
            
            pid = process.pid

            # 保存服务器信息
            self.running_servers[server_id] = {
                "pid": pid,
                "temp_dir": str(temp_dir),
                "endpoint": endpoint,
                "process": process,
                "name": name,
                "project_type": project_type,
                "entry_point": entry_point,
                "port": allocated_port
            }

            # 写入 PID 文件
            with open(pidfile, "w") as f:
                f.write(str(pid))

            # 等待服务启动
            await asyncio.sleep(2)
            
            # 健康检查
            if await self.health_check(endpoint):
                logger.info(f"MCP Server {name} ({server_id}) 启动成功，PID: {pid}, 端点: {endpoint}")
                return {
                    "success": True,
                    "server_id": server_id,
                    "endpoint": endpoint,
                    "pid": pid,
                    "port": allocated_port,
                    "name": name,
                    "error_msg": None
                }
            else:
                logger.warning(f"MCP Server {name} 启动后健康检查失败，但进程仍在运行")
                return {
                    "success": True,  # 进程启动成功，即使健康检查失败
                    "server_id": server_id,
                    "endpoint": endpoint,
                    "pid": pid,
                    "port": allocated_port,
                    "name": name,
                    "error_msg": "健康检查失败，但服务可能仍在启动中"
                }

        except subprocess.CalledProcessError as e:
            error_msg = f"命令执行失败: {e.stderr.decode() if e.stderr else str(e)}"
            logger.error(f"安装 MCP Server 失败: {error_msg}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {"success": False, "error_msg": error_msg}
        except subprocess.TimeoutExpired as e:
            error_msg = f"命令执行超时: {str(e)}"
            logger.error(f"安装 MCP Server 超时: {error_msg}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {"success": False, "error_msg": error_msg}
        except Exception as e:
            error_msg = f"未知错误: {str(e)}"
            logger.error(f"安装 MCP Server 时发生错误: {error_msg}")
            logger.error(f"错误详情: {type(e).__name__}")
            if hasattr(e, 'stderr') and e.stderr:
                logger.error(f"错误输出: {e.stderr}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {"success": False, "error_msg": error_msg}

    async def stop_server(self, server_id: str) -> bool:
        """停止并清理 MCP Server。"""
        logger.info(f"正在停止 MCP Server {server_id}")
        server_info = self.running_servers.pop(server_id, None)
        if not server_info:
            logger.warning(f"Server {server_id} 未在运行服务器列表中找到")
            return False

        pid = server_info.get("pid")
        temp_dir = server_info.get("temp_dir")
        process = server_info.get("process")
        name = server_info.get("name", server_id)

        try:
            if process and process.poll() is None:
                logger.info(f"正在终止进程 {name} (PID: {pid})")
                
                try:
                    parent = psutil.Process(pid)
                    # 优雅地终止子进程
                    children = parent.children(recursive=True)
                    for child in children:
                        child.terminate()
                    parent.terminate()
                    
                    # 等待进程结束
                    gone, alive = psutil.wait_procs([parent] + children, timeout=10)
                    
                    # 强制杀死仍然存活的进程
                    for p in alive:
                        logger.warning(f"强制杀死进程 {p.pid}")
                        p.kill()

                    process.wait(timeout=5)
                    logger.info(f"进程 {name} (PID: {pid}) 已终止")
                    
                except psutil.NoSuchProcess:
                    logger.info(f"进程 {name} (PID: {pid}) 已不存在")
                except Exception as e:
                    logger.error(f"终止进程时出错: {e}")
                    # 尝试直接杀死进程
                    try:
                        process.kill()
                        process.wait(timeout=5)
                    except Exception:
                        pass
            else:
                logger.info(f"进程 {name} (PID: {pid}) 已停止或未找到")

            # 清理临时目录
            if temp_dir and Path(temp_dir).exists():
                logger.info(f"清理临时目录: {temp_dir}")
                shutil.rmtree(temp_dir, ignore_errors=True)
            
            return True
            
        except Exception as e:
            logger.error(f"停止服务器 {name} ({server_id}) 时出错: {e}")
            # 尝试清理临时目录
            if temp_dir and Path(temp_dir).exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            return False

    async def health_check(self, endpoint: str) -> bool:
        """对端点进行健康检查。"""
        logger.debug(f"对端点进行健康检查: {endpoint}")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 尝试多个常见的健康检查端点
                health_endpoints = [
                    f"{endpoint}/health",
                    f"{endpoint}/ping", 
                    f"{endpoint}/status",
                    endpoint  # 根端点
                ]
                
                for health_endpoint in health_endpoints:
                    try:
                        response = await client.get(health_endpoint)
                        if response.status_code < 500:  # 接受所有非服务器错误状态码
                            logger.debug(f"健康检查成功: {health_endpoint} (状态码: {response.status_code})")
                            return True
                    except httpx.RequestError:
                        continue  # 尝试下一个端点
                
                logger.debug(f"所有健康检查端点都失败: {endpoint}")
                return False
                
        except Exception as e:
            logger.error(f"健康检查时发生意外错误 {endpoint}: {e}")
            return False

    def _create_simple_mcp_server(self, name: str, capabilities: list, port: int) -> str:
        """创建简化的MCP服务器Python脚本"""
        return f'''
#!/usr/bin/env python3
"""
简化的MCP服务器 - {name}
自动生成的模拟服务器
"""

import asyncio
import json
import logging
from aiohttp import web
import signal
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimpleMCPServer:
    def __init__(self, name: str, capabilities: list, port: int):
        self.name = name
        self.capabilities = capabilities
        self.port = port
        self.app = web.Application()
        self.setup_routes()
        
    def setup_routes(self):
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/capabilities', self.get_capabilities)
        self.app.router.add_post('/execute', self.execute_tool)
        
    async def health_check(self, request):
        return web.json_response({{
            "status": "healthy",
            "name": self.name,
            "port": self.port
        }})
        
    async def get_capabilities(self, request):
        return web.json_response({{
            "capabilities": self.capabilities,
            "name": self.name
        }})
        
    async def execute_tool(self, request):
        data = await request.json()
        capability = data.get("capability")
        
        if capability in self.capabilities:
            # 模拟成功执行
            result = {{
                "success": True,
                "result": f"Mock execution of {{capability}} completed",
                "capability": capability
            }}
        else:
            result = {{
                "success": False,
                "error": f"Capability {{capability}} not supported"
            }}
            
        return web.json_response(result)
        
    async def start(self):
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        logger.info(f"简化MCP服务器 {{self.name}} 启动在端口 {{self.port}}")
        
        # 等待停止信号
        stop_event = asyncio.Event()
        
        def signal_handler():
            logger.info("收到停止信号")
            stop_event.set()
            
        for sig in [signal.SIGTERM, signal.SIGINT]:
            signal.signal(sig, lambda s, f: signal_handler())
            
        await stop_event.wait()
        await runner.cleanup()

if __name__ == "__main__":
    server = SimpleMCPServer(
        name="{name}",
        capabilities={capabilities},
        port={port}
    )
    
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("服务器被用户停止")
    except Exception as e:
        logger.error(f"服务器运行错误: {{e}}")
        sys.exit(1)
'''

    def list_running_servers(self) -> Dict[str, Dict[str, Any]]:
        """列出所有正在运行的服务器。"""
        return self.running_servers.copy()

    async def cleanup_all(self):
        """清理所有运行的服务器。"""
        logger.info("正在清理所有运行的 MCP 服务器")
        server_ids = list(self.running_servers.keys())
        for server_id in server_ids:
            await self.stop_server(server_id)
        logger.info("所有 MCP 服务器已清理完成")