"""
外部MCP服务器自动管理器
负责自动启动、停止和监控外部MCP服务器
"""

import asyncio
import json
import logging
import subprocess
import time
import aiohttp
from typing import Dict, List, Optional, Any
from pathlib import Path
import socket
import psutil

logger = logging.getLogger(__name__)

class ExternalMCPManager:
    """外部MCP服务器自动管理器"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.running_servers = {}  # {server_id: process_info}
        self.port_allocations = {}  # {server_id: port}
        self.base_port = 6000  # 外部服务器端口起始值
        logger.info("🚀 ExternalMCPManager初始化完成")
        
    def find_free_port(self, start_port: int = None) -> int:
        """找到可用端口"""
        start = start_port or self.base_port
        
        for port in range(start, start + 1000):
            if port in self.port_allocations.values():
                continue
                
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(('', port))
                    return port
                except OSError:
                    continue
        
        raise Exception("无法找到可用端口")
    
    async def start_external_server(self, server_id: str) -> Dict[str, Any]:
        """通用外部服务器启动方法"""
        try:
            # 从配置中获取服务器信息
            ports_config = self.config_manager.get_ports_config()
            server_config = ports_config.get('mcp_servers', {}).get(server_id)
            
            if not server_config:
                return {
                    "success": False,
                    "server_id": server_id,
                    "error": f"服务器配置未找到: {server_id}",
                    "status": "config_not_found"
                }
            
            # 检查是否需要自动启动
            if not server_config.get('auto_start', False):
                return await self.try_connect_existing_server(server_id, server_config)
            
            # 根据不同服务器调用相应启动方法
            if server_id == "microsandbox":
                return await self.start_microsandbox_server()
            else:
                return await self.start_generic_external_server(server_id, server_config)
                
        except Exception as e:
            logger.error(f"启动外部服务器失败 {server_id}: {e}")
            return {
                "success": False,
                "server_id": server_id,
                "error": str(e),
                "status": "failed"
            }
    
    async def start_generic_external_server(self, server_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """启动通用外部服务器"""
        startup_method = config.get('startup_method', 'docker')
        
        if startup_method == 'docker':
            return await self.start_docker_server(server_id, config)
        elif startup_method == 'process':
            return await self.start_process_server(server_id, config)
        else:
            return {
                "success": False,
                "server_id": server_id,
                "error": f"不支持的启动方式: {startup_method}",
                "status": "unsupported_method"
            }
    
    async def start_docker_server(self, server_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """启动Docker容器服务器"""
        port = config.get('port', self.find_free_port())
        docker_image = config.get('docker_image')
        
        if not docker_image:
            return {
                "success": False,
                "server_id": server_id,
                "error": "Docker镜像未配置",
                "status": "missing_docker_image"
            }
        
        try:
            # 检查是否已经运行
            if server_id in self.running_servers:
                process_info = self.running_servers[server_id]
                if self.is_process_running(process_info['pid']):
                    logger.info(f"{server_id}服务器已在运行 (容器: {process_info['pid'][:12]})")
                    return {
                        "success": True,
                        "server_id": server_id,
                        "port": process_info['port'],
                        "endpoint": f"http://localhost:{process_info['port']}{config.get('endpoint', '')}",
                        "status": "already_running"
                    }
            
            # 启动Docker容器
            logger.info(f"正在启动{server_id}服务器，端口: {port}")
            
            # 首先检查Docker是否可用
            try:
                docker_check = subprocess.run(
                    ["docker", "--version"], 
                    capture_output=True, 
                    text=True, 
                    timeout=5
                )
                if docker_check.returncode != 0:
                    logger.warning(f"⚠️ Docker不可用，尝试连接现有的{server_id}实例")
                    return await self.try_connect_existing_server(server_id, config)
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                logger.warning(f"⚠️ Docker命令不可用: {e}，尝试连接现有的{server_id}实例")
                return await self.try_connect_existing_server(server_id, config)
            
            cmd = [
                "docker", "run", "-d",
                "--name", f"{server_id}-mcp-{port}",
                "-p", f"{port}:8000",
                "--rm",
                docker_image
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                container_id = result.stdout.strip()
                
                # 等待服务启动
                health_endpoint = config.get('health_endpoint', '/health')
                max_startup_time = config.get('max_startup_time', 30)
                await self.wait_for_server_ready(f"http://localhost:{port}{health_endpoint}", max_startup_time)
                
                # 记录运行信息
                self.running_servers[server_id] = {
                    "pid": container_id,
                    "port": port,
                    "start_time": time.time(),
                    "type": "docker",
                    "command": cmd
                }
                
                logger.info(f"✅ {server_id}服务器启动成功 (端口: {port}, 容器: {container_id[:12]})")
                
                return {
                    "success": True,
                    "server_id": server_id,
                    "port": port,
                    "endpoint": f"http://localhost:{port}{config.get('endpoint', '')}",
                    "container_id": container_id,
                    "status": "started"
                }
            else:
                error_msg = result.stderr.strip()
                logger.error(f"Docker启动失败: {error_msg}")
                return await self.try_connect_existing_server(server_id, config)
                
        except Exception as e:
            logger.error(f"启动{server_id}失败: {e}")
            return {
                "success": False,
                "server_id": server_id,
                "error": str(e),
                "status": "failed"
            }
    
    async def try_connect_existing_server(self, server_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """尝试连接现有的服务器实例"""
        # 尝试配置端口和常见端口
        ports_to_try = [config.get('port', 5555)]
        if server_id == "microsandbox":
            ports_to_try.extend([5555, 8000, 3000, 9000])
        
        for port in ports_to_try:
            try:
                health_endpoint = config.get('health_endpoint', '/health')
                health_url = f"http://localhost:{port}{health_endpoint}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(health_url, timeout=3) as resp:
                        if resp.status == 200:
                            logger.info(f"✅ 发现运行中的{server_id}实例，端口: {port}")
                            
                            self.running_servers[server_id] = {
                                "pid": "external",
                                "port": port,
                                "start_time": time.time(),
                                "type": "external",
                                "command": None
                            }
                            
                            return {
                                "success": True,
                                "server_id": server_id,
                                "port": port,
                                "endpoint": f"http://localhost:{port}{config.get('endpoint', '')}",
                                "status": "connected_existing"
                            }
            except Exception:
                continue
        
        return {
            "success": False,
            "server_id": server_id,
            "error": f"无法连接到{server_id}实例",
            "status": "not_found"
        }
    
    async def start_microsandbox_server(self) -> Dict[str, Any]:
        """启动microsandbox MCP服务器"""
        server_id = "microsandbox"
        
        # 检查是否已经运行
        if server_id in self.running_servers:
            process_info = self.running_servers[server_id]
            if self.is_process_running(process_info['pid']):
                logger.info(f"MicroSandbox服务器已在运行 (PID: {process_info['pid']})")
                return {
                    "success": True,
                    "server_id": server_id,
                    "port": process_info['port'],
                    "endpoint": f"http://localhost:{process_info['port']}/mcp",
                    "status": "already_running"
                }
        
        # 分配端口
        port = self.find_free_port(5555)  # 优先使用5555
        self.port_allocations[server_id] = port
        
        try:
            # 启动MicroSandbox服务器
            logger.info(f"正在启动MicroSandbox服务器，端口: {port}")
            
            # 使用Docker启动microsandbox
            cmd = [
                "docker", "run", "-d",
                "--name", f"microsandbox-mcp-{port}",
                "-p", f"{port}:8000",
                "--rm",
                "microsandbox/microsandbox:latest"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                container_id = result.stdout.strip()
                
                # 等待服务启动
                await self.wait_for_server_ready(f"http://localhost:{port}/health", timeout=30)
                
                # 记录运行信息
                self.running_servers[server_id] = {
                    "pid": container_id,  # Docker容器ID
                    "port": port,
                    "start_time": time.time(),
                    "type": "docker",
                    "command": cmd
                }
                
                logger.info(f"✅ MicroSandbox服务器启动成功 (端口: {port}, 容器: {container_id[:12]})")
                
                return {
                    "success": True,
                    "server_id": server_id,
                    "port": port,
                    "endpoint": f"http://localhost:{port}/mcp",
                    "container_id": container_id,
                    "status": "started"
                }
            else:
                error_msg = result.stderr.strip()
                logger.error(f"Docker启动失败: {error_msg}")
                
                # 尝试备用方法：检查是否已有现成的microsandbox进程
                return await self.try_connect_existing_server("microsandbox", {
                    "port": 5555,
                    "health_endpoint": "/health",
                    "endpoint": "/mcp"
                })
                
        except Exception as e:
            logger.error(f"启动MicroSandbox失败: {e}")
            return {
                "success": False,
                "server_id": server_id,
                "error": str(e),
                "status": "failed"
            }
    
    async def try_connect_existing_microsandbox(self) -> Dict[str, Any]:
        """尝试连接现有的microsandbox实例"""
        # 常见的microsandbox端口
        common_ports = [5555, 8000, 3000, 9000]
        
        for port in common_ports:
            try:
                health_url = f"http://localhost:{port}/health"
                async with aiohttp.ClientSession() as session:
                    async with session.get(health_url, timeout=3) as resp:
                        if resp.status == 200:
                            logger.info(f"✅ 发现运行中的MicroSandbox实例，端口: {port}")
                            
                            server_id = "microsandbox"
                            self.running_servers[server_id] = {
                                "pid": "external",
                                "port": port,
                                "start_time": time.time(),
                                "type": "external",
                                "command": None
                            }
                            
                            return {
                                "success": True,
                                "server_id": server_id,
                                "port": port,
                                "endpoint": f"http://localhost:{port}/mcp",
                                "status": "connected_existing"
                            }
            except Exception:
                continue
        
        return {
            "success": False,
            "server_id": "microsandbox",
            "error": "无法连接到MicroSandbox实例",
            "status": "not_found"
        }
    
    async def wait_for_server_ready(self, health_url: str, timeout: int = 30):
        """等待服务器就绪"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(health_url, timeout=2) as resp:
                        if resp.status == 200:
                            return True
            except Exception:
                pass
            
            await asyncio.sleep(1)
        
        raise Exception(f"服务器在{timeout}秒内未就绪")
    
    def is_process_running(self, pid_or_container_id: str) -> bool:
        """检查进程或容器是否在运行"""
        try:
            if pid_or_container_id == "external":
                return True  # 外部进程假设一直运行
            
            # 检查Docker容器
            result = subprocess.run(
                ["docker", "inspect", pid_or_container_id],
                capture_output=True, text=True
            )
            return result.returncode == 0
        except Exception:
            return False
    
    async def stop_server(self, server_id: str) -> bool:
        """停止指定的服务器"""
        if server_id not in self.running_servers:
            return True
        
        process_info = self.running_servers[server_id]
        
        try:
            if process_info['type'] == 'docker':
                # 停止Docker容器
                subprocess.run(["docker", "stop", process_info['pid']], check=True)
                logger.info(f"✅ 已停止Docker容器: {process_info['pid']}")
            elif process_info['type'] == 'process':
                # 停止进程
                psutil.Process(int(process_info['pid'])).terminate()
                logger.info(f"✅ 已停止进程: {process_info['pid']}")
            
            # 清理记录
            del self.running_servers[server_id]
            if server_id in self.port_allocations:
                del self.port_allocations[server_id]
            
            return True
        except Exception as e:
            logger.error(f"停止服务器失败: {e}")
            return False
    
    async def cleanup_all(self):
        """清理所有外部服务器"""
        for server_id in list(self.running_servers.keys()):
            await self.stop_server(server_id)
    
    def get_server_status(self) -> Dict[str, Any]:
        """获取所有服务器状态"""
        status = {}
        
        for server_id, info in self.running_servers.items():
            status[server_id] = {
                "running": self.is_process_running(info['pid']),
                "port": info['port'],
                "uptime": time.time() - info['start_time'],
                "type": info['type']
            }
        
        return status
    
    async def ensure_microsandbox_running(self) -> Dict[str, Any]:
        """确保microsandbox服务器正在运行"""
        try:
            # 检查msb命令是否可用
            result = subprocess.run(["which", "msb"], capture_output=True, text=True)
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": "msb命令未找到，请先安装microsandbox CLI",
                    "status": "msb_not_found"
                }
            
            # 检查当前状态
            status_result = subprocess.run(["msb", "server", "status"], capture_output=True, text=True)
            logger.info(f"MicroSandbox状态: {status_result.stdout}")
            
            # 尝试连接现有实例
            ports_to_try = [5555, 8000, 3000]
            for port in ports_to_try:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(f"http://localhost:{port}/v1/sandboxes", 
                                               json={"language": "python"},
                                               timeout=3) as resp:
                            if resp.status in [200, 201]:
                                logger.info(f"✅ 发现运行中的MicroSandbox实例，端口: {port}")
                                
                                self.running_servers["microsandbox"] = {
                                    "pid": "external",
                                    "port": port,
                                    "start_time": time.time(),
                                    "type": "external",
                                    "command": None
                                }
                                
                                return {
                                    "success": True,
                                    "server_id": "microsandbox",
                                    "port": port,
                                    "endpoint": f"http://localhost:{port}",
                                    "status": "connected_existing"
                                }
                except Exception:
                    continue
            
            # 如果没有找到运行的实例，尝试启动
            logger.info("未找到运行的MicroSandbox实例，尝试启动...")
            subprocess.run(["msb", "server", "stop"], capture_output=True)
            await asyncio.sleep(2)
            
            result = subprocess.run(["msb", "server", "start", "--detach", "--dev"], 
                                   capture_output=True, text=True)
            
            if result.returncode == 0:
                # 等待服务启动
                await asyncio.sleep(8)  # 给microsandbox更多启动时间
                
                # 再次尝试连接
                for port in ports_to_try:
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.post(f"http://localhost:{port}/v1/sandboxes", 
                                                   json={"language": "python"},
                                                   timeout=5) as resp:
                                if resp.status in [200, 201]:
                                    logger.info(f"✅ MicroSandbox启动成功 (端口: {port})")
                                    
                                    self.running_servers["microsandbox"] = {
                                        "pid": "msb",
                                        "port": port,
                                        "start_time": time.time(),
                                        "type": "microsandbox",
                                        "command": "msb server start --detach --dev"
                                    }
                                    
                                    return {
                                        "success": True,
                                        "server_id": "microsandbox",
                                        "port": port,
                                        "endpoint": f"http://localhost:{port}",
                                        "status": "started"
                                    }
                    except Exception as e:
                        logger.debug(f"端口 {port} 连接失败: {e}")
                        continue
                
                error_msg = "MicroSandbox启动后无法连接"
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logger.error(f"microsandbox启动失败: {error_msg}")
            
            return {
                "success": False,
                "server_id": "microsandbox",
                "error": error_msg,
                "status": "failed"
            }
                
        except Exception as e:
            logger.error(f"确保microsandbox运行失败: {e}")
            return {
                "success": False,
                "server_id": "microsandbox",
                "error": str(e),
                "status": "failed"
            }