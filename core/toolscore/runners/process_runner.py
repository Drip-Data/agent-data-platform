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
        # 端口使用记录，避免快速重用造成的冲突
        self.used_ports: set = set()
        # 连接重试配置
        self.max_connection_retries = int(os.getenv("MAX_CONNECTION_RETRIES", "3"))
        self.connection_retry_delay = float(os.getenv("CONNECTION_RETRY_DELAY", "1.0"))

    def _allocate_port(self) -> int:
        """分配一个可用的端口，优化版本：避免端口冲突和快速重用。"""
        # 先尝试配置的端口范围，跳过最近使用的端口
        for port in range(self.port_range_start, self.port_range_end + 1):
            if port not in self.used_ports and self._is_port_available(port):
                self.used_ports.add(port)
                logger.info(f"🔌 分配端口 {port} (范围内分配)")
                return port
        
        # 如果配置范围内没有可用端口，清理使用记录并重试
        if self.used_ports:
            logger.info("♻️ 清理端口使用记录，重新尝试分配")
            self.used_ports.clear()
            for port in range(self.port_range_start, self.port_range_end + 1):
                if self._is_port_available(port):
                    self.used_ports.add(port)
                    logger.info(f"🔌 分配端口 {port} (清理后分配)")
                    return port
        
        # 最后使用系统分配
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('localhost', 0))
        port = sock.getsockname()[1]
        sock.close()
        logger.info(f"🔌 分配端口 {port} (系统分配)")
        return port

    def _is_port_available(self, port: int) -> bool:
        """检查端口是否可用。"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)  # 设置超时避免长时间等待
            sock.bind(('localhost', port))
            sock.close()
            return True
        except OSError:
            return False

    async def _wait_for_service_ready(self, port: int, max_wait_time: int = 30) -> bool:
        """等待服务启动并可用，增强版本：支持健康检查。"""
        logger.info(f"⏳ 等待服务启动，端口: {port}")
        
        start_time = asyncio.get_event_loop().time()
        check_interval = 0.5
        
        while (asyncio.get_event_loop().time() - start_time) < max_wait_time:
            # 基础端口连接检查
            if self._is_port_occupied(port):
                # 尝试健康检查（如果可能）
                if await self._check_service_health(port):
                    logger.info(f"✅ 服务就绪，端口: {port}")
                    return True
                else:
                    logger.debug(f"🔄 端口 {port} 已占用但健康检查失败，继续等待...")
            
            await asyncio.sleep(check_interval)
        
        logger.warning(f"⚠️ 服务启动超时，端口: {port}")
        return False
    
    def _is_port_occupied(self, port: int) -> bool:
        """检查端口是否被占用（与_is_port_available相反）。"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            return result == 0  # 0表示连接成功
        except Exception:
            return False
    
    async def _check_service_health(self, port: int) -> bool:
        """检查服务健康状态，支持多种健康检查端点。"""
        health_endpoints = ['/health', '/ping', '/status', '/']
        
        for endpoint in health_endpoints:
            try:
                timeout = httpx.Timeout(2.0)  # 短超时
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.get(f"http://localhost:{port}{endpoint}")
                    if response.status_code < 400:
                        logger.debug(f"✅ 健康检查成功，端点: {endpoint}")
                        return True
            except Exception:
                continue
        
        return False

    def _check_command_available(self, command: str) -> bool:
        """检查命令是否可用。"""
        try:
            subprocess.run([command, "--version"], capture_output=True, check=True, timeout=10)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
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
        logger.info(f"🔍 正在搜索入口点: 目录={project_dir}, 类型={project_type}")
        
        # 列出目录内容以便调试
        try:
            dir_contents = list(project_dir.iterdir())
            logger.info(f"📁 目录内容: {[f.name for f in dir_contents]}")
        except Exception as e:
            logger.warning(f"⚠️ 无法列出目录内容: {e}")
        
        if project_type == "nodejs":
            package_json = project_dir / "package.json"
            is_typescript = (project_dir / "tsconfig.json").exists()
            
            if package_json.exists():
                try:
                    with open(package_json, 'r') as f:
                        data = json.load(f)
                        if "main" in data:
                            logger.info(f"✅ 从package.json找到入口点: {data['main']}")
                            return data["main"]
                        if "scripts" in data and "start" in data["scripts"]:
                            logger.info(f"✅ 从package.json scripts找到启动命令")
                            return "npm start"
                except Exception as e:
                    logger.warning(f"⚠️ 解析package.json失败: {e}")
            
            # 常见的 Node.js/TypeScript 入口点
            if is_typescript:
                logger.info("🔍 检测到TypeScript项目")
                ts_entries = ["index.ts", "server.ts", "app.ts", "main.ts", "src/index.ts", "src/server.ts", "src/app.ts", "src/main.ts"]
                for entry in ts_entries:
                    entry_path = project_dir / entry
                    if entry_path.exists():
                        logger.info(f"✅ 找到TypeScript入口点: {entry}")
                        return entry
            
            # JavaScript 入口点
            js_entries = ["index.js", "server.js", "app.js", "main.js", "src/index.js", "src/server.js", "src/app.js", "src/main.js"]
            for entry in js_entries:
                entry_path = project_dir / entry
                if entry_path.exists():
                    logger.info(f"✅ 找到Node.js入口点: {entry}")
                    return entry
            
            # 检查是否有 TypeScript 文件（没有找到常见入口点时）
            if is_typescript:
                ts_files = list(project_dir.glob("*.ts")) + list(project_dir.glob("src/*.ts"))
                if ts_files:
                    logger.info(f"✅ 回退策略找到TypeScript入口点: {ts_files[0].relative_to(project_dir)}")
                    return str(ts_files[0].relative_to(project_dir))
        
        elif project_type == "python":
            # 🔧 增强的Python入口点搜索
            python_entries = [
                "main.py", 
                "server.py", 
                "app.py", 
                "__main__.py", 
                "run.py",
                "start.py",
                "index.py"
            ]
            
            for entry in python_entries:
                entry_path = project_dir / entry
                if entry_path.exists():
                    logger.info(f"✅ 找到Python入口点: {entry}")
                    return entry
            
            # 🔧 新增：搜索子目录中的入口点（用于MCP服务器）
            # 检查常见的MCP服务器结构
            mcp_patterns = [
                "src/main.py",
                "*/main.py", 
                "*/server.py",
                "*/app.py"
            ]
            
            for pattern in mcp_patterns:
                if '*' in pattern:
                    # 搜索匹配模式的文件
                    try:
                        matches = list(project_dir.glob(pattern))
                        if matches:
                            relative_path = matches[0].relative_to(project_dir)
                            logger.info(f"✅ 找到MCP入口点: {relative_path}")
                            return str(relative_path)
                    except Exception as e:
                        logger.debug(f"模式匹配失败 {pattern}: {e}")
                else:
                    entry_path = project_dir / pattern
                    if entry_path.exists():
                        logger.info(f"✅ 找到MCP入口点: {pattern}")
                        return pattern
            
            # 检查是否有可执行的包
            main_py = project_dir / "__main__.py"
            if main_py.exists():
                logger.info("✅ 找到Python包入口点: __main__.py")
                return "-m ."
            
            # 🔧 最后的回退策略：查找任何.py文件
            py_files = list(project_dir.glob("*.py"))
            if py_files:
                # 优先选择包含"main"、"server"、"app"的文件
                for py_file in py_files:
                    name_lower = py_file.name.lower()
                    if any(keyword in name_lower for keyword in ["main", "server", "app", "start"]):
                        logger.info(f"✅ 回退策略找到入口点: {py_file.name}")
                        return py_file.name
                
                # 如果没有明显的入口点，选择第一个.py文件
                logger.info(f"⚠️ 使用第一个Python文件作为入口点: {py_files[0].name}")
                return py_files[0].name
        
        logger.warning(f"❌ 未找到合适的入口点，目录: {project_dir}")
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

            # 根据项目类型构建启动命令
            cmd = []
            env = os.environ.copy()

            if project_type == "python":
                # 创建简化的MCP服务器脚本
                simple_server_script = self._create_simple_mcp_server(
                    name, candidate.get("capabilities", []), allocated_port
                )
                
                script_path = temp_dir / "simple_server.py"
                with open(script_path, 'w', encoding='utf-8') as f:
                    f.write(simple_server_script)
                
                cmd = [python_executable, str(script_path)]
                
            elif project_type == "nodejs":
                # Node.js/TypeScript 项目启动逻辑
                env["PORT"] = str(allocated_port)
                
                # 检测是否为 TypeScript 项目
                is_typescript = (temp_dir / "tsconfig.json").exists()
                
                if entry_point == "npm start":
                    cmd = ["npm", "start"]
                    logger.info("🚀 使用 npm start 启动 Node.js 服务")
                elif entry_point and entry_point.endswith('.ts') and is_typescript:
                    # TypeScript 文件，尝试使用 ts-node
                    if self._check_command_available("npx"):
                        cmd = ["npx", "ts-node", entry_point]
                        logger.info(f"🚀 使用 ts-node 启动 TypeScript 服务: {entry_point}")
                    else:
                        logger.warning("ts-node 不可用，尝试先编译 TypeScript")
                        # 尝试编译 TypeScript
                        try:
                            subprocess.run(["npx", "tsc"], cwd=temp_dir, check=True, capture_output=True, timeout=60)
                            # 使用编译后的 JS 文件
                            js_entry = entry_point.replace('.ts', '.js')
                            cmd = ["node", js_entry]
                            logger.info(f"🚀 编译后使用 Node.js 启动: {js_entry}")
                        except subprocess.CalledProcessError:
                            return {"success": False, "error_msg": f"TypeScript 编译失败: {entry_point}"}
                elif entry_point:
                    # JavaScript 文件或其他
                    cmd = ["node", entry_point]
                    logger.info(f"🚀 使用 Node.js 启动: {entry_point}")
                else:
                    return {"success": False, "error_msg": "未找到有效的 Node.js 入口点"}
                
            else:
                return {"success": False, "error_msg": f"不支持的项目类型: {project_type}"}

            if not cmd:
                return {"success": False, "error_msg": "无法确定启动命令"}

            logger.info(f"启动 MCP Server: {' '.join(cmd)} (端口: {allocated_port})")
            
            # 启动进程
            logger.info(f"🚀 启动命令: {' '.join(cmd)} (工作目录: {temp_dir})")
            process = subprocess.Popen(cmd, cwd=temp_dir, env=env, preexec_fn=os.setsid if os.name != "nt" else None)
            
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