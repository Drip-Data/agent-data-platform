"""
持久化容器管理器
确保MCP服务器容器在系统重启后自动恢复
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
import docker
from docker.errors import APIError, NotFound

from .interfaces import MCPServerSpec, InstallationResult

logger = logging.getLogger(__name__)

class PersistentContainerManager:
    """持久化容器管理器 - 确保容器在重启后自动恢复"""
    
    def __init__(self):
        self.docker_client = docker.from_env()
        self.restart_policy = {"Name": "unless-stopped"}  # 容器重启策略
        self.persistent_volumes = {}  # 持久化卷映射
        self.network_name = "agent-data-platform_agent_network"
        
        logger.info("持久化容器管理器初始化完成")
    
    async def initialize(self):
        """初始化容器管理器"""
        try:
            # 验证Docker连接
            self.docker_client.ping()
            logger.info("Docker连接验证成功")
            
            # 验证网络存在
            await self._ensure_network_exists()
            
        except Exception as e:
            logger.error(f"初始化容器管理器失败: {e}")
            raise
    
    async def _ensure_network_exists(self):
        """确保Docker网络存在"""
        try:
            self.docker_client.networks.get(self.network_name)
            logger.info(f"Docker网络存在: {self.network_name}")
        except NotFound:
            logger.warning(f"Docker网络不存在: {self.network_name}")
            # 尝试创建网络
            try:
                network = self.docker_client.networks.create(
                    self.network_name,
                    driver="bridge"
                )
                logger.info(f"已创建Docker网络: {self.network_name}")
            except Exception as e:
                logger.error(f"创建Docker网络失败: {e}")
                # 使用默认网络
                self.network_name = "bridge"
        except Exception as e:
            logger.error(f"检查Docker网络失败: {e}")
            # 使用默认网络
            self.network_name = "bridge"
    
    async def create_persistent_container(self, 
                                        image_id: str, 
                                        server_spec: MCPServerSpec,
                                        port: int) -> str:
        """创建持久化容器，确保重启后自动恢复"""
        
        container_name = f"mcp-{server_spec.tool_id}"
        
        # 检查是否已存在同名容器
        existing_container = await self._get_existing_container(container_name)
        if existing_container:
            logger.info(f"发现已存在的容器: {container_name}")
            # 如果容器存在但未运行，启动它
            if existing_container.status != 'running':
                try:
                    existing_container.start()
                    logger.info(f"启动已存在的容器: {container_name}")
                except Exception as e:
                    logger.warning(f"启动已存在容器失败: {e}")
                    # 删除旧容器，创建新的
                    await self._remove_container(existing_container)
                    return await self._create_new_container(image_id, server_spec, port, container_name)
            return existing_container.id
        
        # 创建新容器
        return await self._create_new_container(image_id, server_spec, port, container_name)
    
    async def _get_existing_container(self, container_name: str):
        """获取已存在的容器"""
        try:
            return self.docker_client.containers.get(container_name)
        except NotFound:
            return None
        except Exception as e:
            logger.error(f"获取容器失败: {container_name} - {e}")
            return None
    
    async def _remove_container(self, container):
        """移除容器"""
        try:
            if container.status == 'running':
                container.stop(timeout=10)
            container.remove()
            logger.info(f"已移除容器: {container.name}")
        except Exception as e:
            logger.error(f"移除容器失败: {container.name} - {e}")
    
    async def _create_new_container(self, image_id: str, server_spec: MCPServerSpec, 
                                  port: int, container_name: str) -> str:
        """创建新的持久化容器"""
        
        # 容器配置
        container_config = {
            "image": image_id,
            "name": container_name,
            "ports": {f"{port}/tcp": port},
            "environment": {
                "MCP_SERVER_PORT": str(port),
                "MCP_SERVER_ID": server_spec.tool_id,
                "MCP_SERVER_NAME": server_spec.name,
                "TOOLSCORE_ENDPOINT": "ws://toolscore:8080/websocket"
            },
            "restart_policy": self.restart_policy,
            "network": self.network_name,
            "labels": {
                "mcp.server.id": server_spec.tool_id,
                "mcp.server.name": server_spec.name,
                "mcp.server.port": str(port),
                "mcp.manager": "toolscore",
                "mcp.auto-recover": "true",
                "mcp.created_at": str(int(time.time())),
                "mcp.capabilities": ",".join([cap.name for cap in server_spec.capabilities])
            },
            "detach": True,
            "remove": False,  # 保持容器用于重启
            "stdin_open": True,  # 支持MCP stdio通信
            "tty": False,
            "init": True  # 使用init进程管理
        }
        
        # 创建持久化卷(如果需要)
        if server_spec.server_config.get("requires_persistence"):
            volume_name = f"mcp-{server_spec.tool_id}-data"
            await self._create_volume_if_not_exists(volume_name)
            container_config["volumes"] = {
                volume_name: {"bind": "/data", "mode": "rw"}
            }
            logger.info(f"为容器配置持久化卷: {volume_name}")
        
        try:
            container = self.docker_client.containers.run(**container_config)
            
            logger.info(f"创建持久化容器成功: {container.name} ({container.id[:12]})")
            
            # 等待容器启动
            await asyncio.sleep(2)
            
            # 检查容器状态
            container.reload()
            if container.status != 'running':
                logger.error(f"容器启动失败: {container.name} - {container.status}")
                # 获取容器日志进行诊断
                logs = container.logs().decode('utf-8')
                logger.error(f"容器日志: {logs}")
                raise Exception(f"容器启动失败: {container.status}")
            
            return container.id
            
        except Exception as e:
            logger.error(f"创建持久化容器失败: {e}")
            raise
    
    async def _create_volume_if_not_exists(self, volume_name: str):
        """创建Docker卷（如果不存在）"""
        try:
            self.docker_client.volumes.get(volume_name)
            logger.info(f"Docker卷已存在: {volume_name}")
        except NotFound:
            try:
                self.docker_client.volumes.create(
                    name=volume_name,
                    driver="local"
                )
                logger.info(f"创建Docker卷: {volume_name}")
            except Exception as e:
                logger.error(f"创建Docker卷失败: {volume_name} - {e}")
                raise
    
    async def recover_all_containers(self) -> int:
        """恢复所有标记为自动恢复的容器"""
        try:
            # 查找所有MCP容器
            containers = self.docker_client.containers.list(
                all=True,
                filters={"label": "mcp.auto-recover=true"}
            )
            
            recovered_count = 0
            failed_containers = []
            
            for container in containers:
                try:
                    if container.status != 'running':
                        logger.info(f"恢复容器: {container.name}")
                        container.start()
                        
                        # 等待启动
                        await asyncio.sleep(1)
                        container.reload()
                        
                        if container.status == 'running':
                            logger.info(f"容器恢复成功: {container.name}")
                            recovered_count += 1
                        else:
                            logger.error(f"容器恢复失败: {container.name} - {container.status}")
                            failed_containers.append(container.name)
                    else:
                        logger.debug(f"容器已在运行: {container.name}")
                        recovered_count += 1
                        
                except Exception as e:
                    logger.error(f"恢复容器失败: {container.name} - {e}")
                    failed_containers.append(container.name)
                    continue
            
            if failed_containers:
                logger.warning(f"以下容器恢复失败: {failed_containers}")
            
            logger.info(f"容器恢复完成 - 成功: {recovered_count}, 失败: {len(failed_containers)}")
            return recovered_count
            
        except Exception as e:
            logger.error(f"恢复容器过程失败: {e}")
            return 0
    
    async def stop_container(self, container_id: str) -> bool:
        """停止指定容器"""
        try:
            container = self.docker_client.containers.get(container_id)
            if container.status == 'running':
                container.stop(timeout=10)
                logger.info(f"容器已停止: {container.name}")
                return True
            else:
                logger.info(f"容器已停止: {container.name}")
                return True
        except NotFound:
            logger.warning(f"容器不存在: {container_id}")
            return False
        except Exception as e:
            logger.error(f"停止容器失败: {container_id} - {e}")
            return False
    
    async def remove_container(self, container_id: str) -> bool:
        """移除指定容器"""
        try:
            container = self.docker_client.containers.get(container_id)
            
            # 先停止容器
            if container.status == 'running':
                container.stop(timeout=10)
            
            # 移除容器
            container.remove()
            logger.info(f"容器已移除: {container.name}")
            return True
            
        except NotFound:
            logger.warning(f"容器不存在: {container_id}")
            return True  # 容器不存在也算成功
        except Exception as e:
            logger.error(f"移除容器失败: {container_id} - {e}")
            return False
    
    async def get_container_status(self, container_id: str) -> str:
        """获取容器状态"""
        try:
            container = self.docker_client.containers.get(container_id)
            container.reload()
            return container.status
        except NotFound:
            return "not_found"
        except Exception as e:
            logger.error(f"获取容器状态失败: {container_id} - {e}")
            return "error"
    
    async def get_container_logs(self, container_id: str, lines: int = 50) -> str:
        """获取容器日志"""
        try:
            container = self.docker_client.containers.get(container_id)
            logs = container.logs(tail=lines).decode('utf-8')
            return logs
        except NotFound:
            return "容器不存在"
        except Exception as e:
            logger.error(f"获取容器日志失败: {container_id} - {e}")
            return f"获取日志失败: {e}"
    
    async def list_mcp_containers(self) -> List[Dict[str, Any]]:
        """列出所有MCP容器"""
        try:
            containers = self.docker_client.containers.list(
                all=True,
                filters={"label": "mcp.manager=toolscore"}
            )
            
            container_list = []
            for container in containers:
                container_info = {
                    "id": container.id,
                    "name": container.name,
                    "status": container.status,
                    "image": container.image.tags[0] if container.image.tags else "unknown",
                    "created": container.attrs.get("Created", ""),
                    "labels": container.labels,
                    "ports": container.ports
                }
                container_list.append(container_info)
            
            return container_list
            
        except Exception as e:
            logger.error(f"列出MCP容器失败: {e}")
            return []
    
    async def get_container_stats(self) -> Dict[str, Any]:
        """获取容器统计信息"""
        try:
            containers = self.docker_client.containers.list(
                all=True,
                filters={"label": "mcp.manager=toolscore"}
            )
            
            stats = {
                "total_containers": len(containers),
                "running_containers": 0,
                "stopped_containers": 0,
                "auto_recover_containers": 0,
                "containers": []
            }
            
            for container in containers:
                container.reload()
                
                if container.status == 'running':
                    stats["running_containers"] += 1
                else:
                    stats["stopped_containers"] += 1
                
                if container.labels.get("mcp.auto-recover") == "true":
                    stats["auto_recover_containers"] += 1
                
                stats["containers"].append({
                    "name": container.name,
                    "status": container.status,
                    "server_id": container.labels.get("mcp.server.id", "unknown"),
                    "port": container.labels.get("mcp.server.port", "unknown"),
                    "auto_recover": container.labels.get("mcp.auto-recover", "false")
                })
            
            return stats
            
        except Exception as e:
            logger.error(f"获取容器统计失败: {e}")
            return {"error": str(e)}
    
    async def cleanup_orphaned_containers(self) -> int:
        """清理孤立的MCP容器"""
        try:
            # 获取所有MCP容器
            containers = self.docker_client.containers.list(
                all=True,
                filters={"label": "mcp.manager=toolscore"}
            )
            
            cleaned_count = 0
            
            for container in containers:
                try:
                    # 检查容器是否长时间未运行
                    created_time = container.attrs.get("Created", "")
                    if created_time:
                        # 这里可以添加更复杂的清理逻辑
                        # 例如：超过7天未运行的容器
                        pass
                    
                    # 检查容器是否有效
                    if container.status in ['exited', 'dead'] and not container.labels.get("mcp.auto-recover"):
                        logger.info(f"清理孤立容器: {container.name}")
                        container.remove()
                        cleaned_count += 1
                        
                except Exception as e:
                    logger.error(f"清理容器失败: {container.name} - {e}")
                    continue
            
            logger.info(f"清理完成，移除了 {cleaned_count} 个孤立容器")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"清理孤立容器失败: {e}")
            return 0
    
    async def cleanup(self):
        """清理资源"""
        try:
            self.docker_client.close()
            logger.info("持久化容器管理器清理完成")
        except Exception as e:
            logger.error(f"清理容器管理器失败: {e}") 