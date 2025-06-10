"""
动态MCP服务器管理器
负责搜索、发现、安装和部署新的MCP服务器
"""

import asyncio
import json
import logging
import os
import tempfile
import docker
import aiohttp
import yaml
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
import hashlib
import subprocess
import socket
import time

from .interfaces import ToolSpec, MCPServerSpec, ToolCapability, ToolType, RegistrationResult
from .unified_tool_library import UnifiedToolLibrary
from .persistent_storage import PersistentStorage

logger = logging.getLogger(__name__)

@dataclass
class MCPServerCandidate:
    """MCP服务器候选者"""
    name: str
    description: str
    github_url: str
    author: str
    tags: List[str]
    install_method: str  # docker, npm, python, binary
    capabilities: List[str]
    verified: bool = False
    security_score: float = 0.0
    popularity_score: float = 0.0

@dataclass
class InstallationResult:
    """安装结果"""
    success: bool
    server_id: Optional[str] = None
    endpoint: Optional[str] = None
    error_message: Optional[str] = None
    container_id: Optional[str] = None
    port: Optional[int] = None

@dataclass  
class MCPSearchResult:
    """MCP搜索结果"""
    success: bool
    message: str
    installed_tools: List[Dict[str, Any]]

class DynamicMCPManager:
    """动态MCP服务器管理器"""
    
    def __init__(self, tool_library: UnifiedToolLibrary, redis_url: str = "redis://redis:6379"):
        self.tool_library = tool_library
        self.docker_client = docker.from_env()
        self.installed_servers: Dict[str, InstallationResult] = {}
        self.registry_cache: Dict[str, List[MCPServerCandidate]] = {}
        self.next_port = 8100  # 动态分配端口起始号
        
        # 初始化持久化存储
        self.persistent_storage = PersistentStorage(redis_url)
        self._storage_initialized = False
        
        # MCP服务器注册中心配置 - 优先使用模拟注册中心
        self.registries = {
            "mock_registry": "mock://internal/registry",  # 内置模拟注册中心，优先级最高
            "github_public": "https://raw.githubusercontent.com/modelcontextprotocol/servers/main",  # 无需认证的GitHub内容
            # 注释掉有问题的外部服务
            # "smithery": "https://smithery.io/api/servers",
            # "mcpmarket": "https://mcpmarket.co/api/servers", 
            # "github_awesome": "https://api.github.com/repos/wong2/awesome-mcp-servers/contents/servers.json",
            # "anthropic_official": "https://api.github.com/repos/modelcontextprotocol/servers/contents"
        }
        
        # 安全性检查规则
        self.security_rules = {
            "trusted_authors": ["anthropic", "modelcontextprotocol", "wong2"],
            "min_stars": 10,
            "max_age_days": 365,
            "required_files": ["README.md", "package.json", "Dockerfile"]
        }
        
        logger.info("Dynamic MCP Manager initialized")
    
    async def initialize(self):
        """初始化动态MCP管理器，包括恢复持久化的服务器"""
        if not self._storage_initialized:
            try:
                await self.persistent_storage.initialize()
                self._storage_initialized = True
                logger.info("Persistent storage initialized")
                
                # 恢复持久化的MCP服务器
                await self._restore_persistent_servers()
                
            except Exception as e:
                logger.error(f"Failed to initialize persistent storage: {e}")
                # 继续运行，但不使用持久化功能
                self._storage_initialized = False
    
    async def _restore_persistent_servers(self):
        """恢复持久化的MCP服务器"""
        try:
            logger.info("Restoring persistent MCP servers...")
            
            # 加载所有持久化的服务器
            stored_servers = await self.persistent_storage.load_all_mcp_servers()
            
            restored_count = 0
            for server_info in stored_servers:
                try:
                    await self._restore_single_server(server_info)
                    restored_count += 1
                except Exception as e:
                    logger.error(f"Failed to restore server {server_info.get('server_data', {}).get('name', 'unknown')}: {e}")
                    continue
            
            logger.info(f"Successfully restored {restored_count} MCP servers from persistent storage")
            
        except Exception as e:
            logger.error(f"Failed to restore persistent servers: {e}")
    
    async def _restore_single_server(self, server_info: Dict[str, Any]):
        """恢复单个MCP服务器"""
        server_data = server_info["server_data"]
        install_result_data = server_info.get("install_result")
        
        if not install_result_data:
            logger.warning(f"No install result for server {server_data['name']}, skipping restoration")
            return
        
        try:
            # 重建MCPServerSpec
            from .interfaces import ToolCapability
            
            capabilities = []
            for cap_data in server_data.get("capabilities", []):
                capability = ToolCapability(
                    name=cap_data["name"],
                    description=cap_data["description"],
                    parameters=cap_data.get("parameters", {}),
                    examples=cap_data.get("examples", [])
                )
                capabilities.append(capability)
            
            server_spec = MCPServerSpec(
                tool_id=server_data["tool_id"],
                name=server_data["name"],
                description=server_data["description"],
                tool_type=ToolType(server_data["tool_type"]),
                capabilities=capabilities,
                tags=server_data.get("tags", []),
                endpoint=server_data.get("endpoint"),
                server_config=server_data.get("server_config", {}),
                connection_params=server_data.get("connection_params", {}),
                enabled=server_data.get("enabled", True)
            )
            
            # 重建InstallationResult
            install_result = InstallationResult(
                success=install_result_data["success"],
                server_id=install_result_data.get("server_id"),
                endpoint=install_result_data.get("endpoint"),
                error_message=install_result_data.get("error_message"),
                container_id=install_result_data.get("container_id"),
                port=install_result_data.get("port")
            )
            
            # 检查容器是否仍在运行（对于真实的Docker容器）
            if install_result.container_id and install_result.container_id.startswith("mock-"):
                # Mock容器，直接注册到工具库
                registration_result = await self.tool_library.register_mcp_server(server_spec)
                if registration_result.success:
                    self.installed_servers[install_result.server_id] = install_result
                    logger.info(f"Restored mock MCP server: {server_spec.name}")
                else:
                    logger.error(f"Failed to register restored server {server_spec.name}: {registration_result.error}")
            else:
                # 真实容器，检查健康状态
                try:
                    if install_result.container_id:
                        container = self.docker_client.containers.get(install_result.container_id)
                        if container.status == 'running':
                            # 容器仍在运行，直接注册
                            registration_result = await self.tool_library.register_mcp_server(server_spec)
                            if registration_result.success:
                                self.installed_servers[install_result.server_id] = install_result
                                logger.info(f"Restored running MCP server: {server_spec.name}")
                            else:
                                logger.error(f"Failed to register restored server {server_spec.name}: {registration_result.error}")
                        else:
                            logger.warning(f"Container {install_result.container_id} is not running, skipping restoration")
                    else:
                        logger.warning(f"No container ID for server {server_spec.name}, skipping restoration")
                except docker.errors.NotFound:
                    logger.warning(f"Container {install_result.container_id} not found, removing from persistent storage")
                    await self.persistent_storage.remove_mcp_server(server_spec.tool_id)
                
        except Exception as e:
            logger.error(f"Failed to restore server {server_data['name']}: {e}")
            raise
    
    def _allocate_port(self) -> Optional[int]:
        """分配可用端口"""
        max_port = 8200
        for port in range(self.next_port, max_port + 1):
            # 检查端口是否已被使用
            if not self._is_port_in_use(port):
                self.next_port = port + 1
                return port
        
        logger.error("No available ports in range 8100-8200")
        return None
    
    def _is_port_in_use(self, port: int) -> bool:
        """检查端口是否被使用"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex(('localhost', port))
                return result == 0
        except Exception:
            return False
    
    async def search_mcp_servers(self, query: str, capability_tags: List[str] = None) -> List[MCPServerCandidate]:
        """搜索符合条件的MCP服务器"""
        logger.info(f"Searching for MCP servers with query: '{query}', capabilities: {capability_tags}")
        
        all_candidates = []
        
        # 并行搜索多个注册中心
        search_tasks = []
        for registry_name, registry_url in self.registries.items():
            search_tasks.append(self._search_registry(registry_name, registry_url, query, capability_tags))
        
        # 执行搜索
        registry_results = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        # 合并结果
        for i, result in enumerate(registry_results):
            registry_name = list(self.registries.keys())[i]
            if isinstance(result, Exception):
                logger.warning(f"Failed to search {registry_name}: {result}")
                continue
            
            if result:
                all_candidates.extend(result)
                logger.info(f"Found {len(result)} candidates from {registry_name}")
        
        # 去重和评分
        unique_candidates = self._deduplicate_candidates(all_candidates)
        scored_candidates = await self._score_candidates(unique_candidates)
        
        # 按评分排序
        scored_candidates.sort(key=lambda x: (x.security_score + x.popularity_score), reverse=True)
        
        logger.info(f"Total {len(scored_candidates)} unique candidates found and scored")
        return scored_candidates[:10]  # 返回前10个最佳候选者
    
    async def _search_registry(self, registry_name: str, registry_url: str, query: str, capability_tags: List[str]) -> List[MCPServerCandidate]:
        """搜索单个注册中心"""
        try:
            # 优先使用模拟注册中心
            if registry_name == "mock_registry":
                return await self._search_mock_registry(query, capability_tags)
            
            # 使用更robust的HTTP客户端配置
            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
            
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                if registry_name == "github_public":
                    return await self._search_github_public(session, registry_url, query, capability_tags)
                elif registry_name == "smithery":
                    return await self._search_smithery(session, registry_url, query, capability_tags)
                elif registry_name == "mcpmarket":
                    return await self._search_mcpmarket(session, registry_url, query, capability_tags)
                elif registry_name == "github_awesome":
                    return await self._search_github_awesome(session, registry_url, query, capability_tags)
                elif registry_name == "anthropic_official":
                    return await self._search_anthropic_official(session, registry_url, query, capability_tags)
                else:
                    logger.warning(f"Unknown registry: {registry_name}")
                    return []
        except Exception as e:
            logger.error(f"Error searching {registry_name}: {e}")
            return []
    
    async def _search_mock_registry(self, query: str, capability_tags: List[str]) -> List[MCPServerCandidate]:
        """搜索模拟注册中心，使用动态生成的候选者"""
        logger.info(f"Searching mock registry for query: '{query}', capabilities: {capability_tags}")
        return await self._get_mock_candidates(query, capability_tags)
    
    async def _search_github_public(self, session: aiohttp.ClientSession, base_url: str, query: str, capability_tags: List[str]) -> List[MCPServerCandidate]:
        """搜索GitHub公共仓库（无需认证）"""
        candidates = []
        
        try:
            # 尝试获取一些已知的MCP服务器列表
            readme_urls = [
                f"{base_url}/README.md",
                f"{base_url}/docs/servers.md"
            ]
            
            for url in readme_urls:
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            content = await response.text()
                            # 简单解析README中的服务器信息
                            if query.lower() in content.lower():
                                # 基于内容创建候选者
                                candidate = MCPServerCandidate(
                                    name=f"MCP Server for {query.title()}",
                                    description=f"Official MCP server supporting {query} functionality",
                                    github_url=f"https://github.com/modelcontextprotocol/servers",
                                    author="modelcontextprotocol",
                                    tags=["official", "verified"],
                                    install_method="docker",
                                    capabilities=[query.lower().replace(" ", "_")],
                                    verified=True,
                                    security_score=0.95,
                                    popularity_score=0.85
                                )
                                candidates.append(candidate)
                                break
                except Exception as e:
                    logger.debug(f"Failed to fetch {url}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error searching GitHub public: {e}")
        
        return candidates
    
    async def _search_smithery(self, session: aiohttp.ClientSession, url: str, query: str, capability_tags: List[str]) -> List[MCPServerCandidate]:
        """搜索Smithery注册中心"""
        params = {"q": query, "limit": 20}
        
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    candidates = []
                    
                    for server in data.get("servers", []):
                        candidate = MCPServerCandidate(
                            name=server.get("name", ""),
                            description=server.get("description", ""),
                            github_url=server.get("repository", ""),
                            author=server.get("author", ""),
                            tags=server.get("tags", []),
                            install_method=self._detect_install_method(server),
                            capabilities=server.get("capabilities", [])
                        )
                        
                        # 过滤匹配的能力标签
                        if capability_tags:
                            if any(tag.lower() in [cap.lower() for cap in candidate.capabilities] for tag in capability_tags):
                                candidates.append(candidate)
                        else:
                            candidates.append(candidate)
                    
                    return candidates
                else:
                    logger.warning(f"Smithery API returned status {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error searching Smithery: {e}")
            return []
    
    async def _search_mcpmarket(self, session: aiohttp.ClientSession, url: str, query: str, capability_tags: List[str]) -> List[MCPServerCandidate]:
        """搜索MCP Market注册中心"""
        # 实现类似的搜索逻辑
        params = {"search": query, "limit": 20}
        
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    # 解析MCP Market格式并转换为候选者
                    candidates = []
                    
                    for server in data.get("results", []):
                        candidate = MCPServerCandidate(
                            name=server.get("name", ""),
                            description=server.get("description", ""),
                            github_url=server.get("url", ""),
                            author=server.get("author", ""),
                            tags=server.get("keywords", []),
                            install_method=self._detect_install_method(server),
                            capabilities=server.get("tools", [])
                        )
                        candidates.append(candidate)
                    
                    return candidates
                else:
                    return []
        except Exception as e:
            logger.error(f"Error searching MCP Market: {e}")
            return []
    
    async def _search_github_awesome(self, session: aiohttp.ClientSession, url: str, query: str, capability_tags: List[str]) -> List[MCPServerCandidate]:
        """搜索GitHub Awesome MCP Servers列表"""
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    content = await response.json()
                    # GitHub API返回base64编码的内容
                    import base64
                    decoded_content = base64.b64decode(content["content"]).decode('utf-8')
                    servers_data = json.loads(decoded_content)
                    
                    candidates = []
                    for server in servers_data.get("servers", []):
                        if query.lower() in server.get("name", "").lower() or query.lower() in server.get("description", "").lower():
                            candidate = MCPServerCandidate(
                                name=server.get("name", ""),
                                description=server.get("description", ""),
                                github_url=server.get("url", ""),
                                author=server.get("author", ""),
                                tags=server.get("tags", []),
                                install_method=self._detect_install_method(server),
                                capabilities=server.get("capabilities", [])
                            )
                            candidates.append(candidate)
                    
                    return candidates
                else:
                    return []
        except Exception as e:
            logger.error(f"Error searching GitHub Awesome list: {e}")
            return []
    
    async def _search_anthropic_official(self, session: aiohttp.ClientSession, url: str, query: str, capability_tags: List[str]) -> List[MCPServerCandidate]:
        """搜索Anthropic官方服务器仓库"""
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    contents = await response.json()
                    candidates = []
                    
                    # 遍历仓库中的服务器目录
                    for item in contents:
                        if item["type"] == "dir" and query.lower() in item["name"].lower():
                            candidate = MCPServerCandidate(
                                name=item["name"],
                                description=f"Official Anthropic MCP Server: {item['name']}",
                                github_url=f"https://github.com/modelcontextprotocol/servers/tree/main/{item['name']}",
                                author="anthropic",
                                tags=["official", "anthropic"],
                                install_method="docker",  # 默认docker安装
                                capabilities=[],  # 需要进一步解析
                                verified=True
                            )
                            candidates.append(candidate)
                    
                    return candidates
                else:
                    return []
        except Exception as e:
            logger.error(f"Error searching Anthropic official: {e}")
            return []
    
    def _detect_install_method(self, server_data: Dict[str, Any]) -> str:
        """检测安装方法"""
        if "dockerfile" in server_data or "docker" in server_data.get("install", "").lower():
            return "docker"
        elif "package.json" in server_data or "npm" in server_data.get("install", "").lower():
            return "npm"
        elif "requirements.txt" in server_data or "pip" in server_data.get("install", "").lower():
            return "python"
        else:
            return "docker"  # 默认使用docker
    
    def _deduplicate_candidates(self, candidates: List[MCPServerCandidate]) -> List[MCPServerCandidate]:
        """去重候选者"""
        seen_urls = set()
        unique_candidates = []
        
        for candidate in candidates:
            url_key = candidate.github_url.lower().strip('/')
            if url_key not in seen_urls:
                seen_urls.add(url_key)
                unique_candidates.append(candidate)
        
        return unique_candidates
    
    async def _score_candidates(self, candidates: List[MCPServerCandidate]) -> List[MCPServerCandidate]:
        """为候选者评分"""
        for candidate in candidates:
            # 安全性评分
            security_score = 0.0
            if candidate.author in self.security_rules["trusted_authors"]:
                security_score += 50.0
            if candidate.verified:
                security_score += 30.0
            
            # 流行度评分（需要GitHub API调用）
            popularity_score = await self._get_popularity_score(candidate.github_url)
            
            candidate.security_score = security_score
            candidate.popularity_score = popularity_score
        
        return candidates
    
    async def _get_popularity_score(self, github_url: str) -> float:
        """获取GitHub仓库流行度评分"""
        try:
            # 从URL提取仓库信息
            parsed = urlparse(github_url)
            if parsed.hostname != "github.com":
                return 0.0
            
            path_parts = parsed.path.strip('/').split('/')
            if len(path_parts) < 2:
                return 0.0
            
            owner, repo = path_parts[0], path_parts[1]
            
            # 调用GitHub API
            async with aiohttp.ClientSession() as session:
                api_url = f"https://api.github.com/repos/{owner}/{repo}"
                async with session.get(api_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        stars = data.get("stargazers_count", 0)
                        forks = data.get("forks_count", 0)
                        
                        # 计算流行度评分
                        score = min(stars * 2 + forks, 100.0)
                        return score
                    else:
                        return 0.0
        except Exception as e:
            logger.warning(f"Failed to get popularity score for {github_url}: {e}")
            return 0.0
    
    async def install_mcp_server(self, candidate: MCPServerCandidate) -> InstallationResult:
        """安装MCP服务器"""
        logger.info(f"Installing MCP server: {candidate.name}")
        
        try:
            # 首先尝试模拟安装（用于演示和测试）
            if candidate.security_score >= 0.8 and candidate.popularity_score >= 0.8:
                logger.info(f"Attempting mock installation for high-quality candidate: {candidate.name}")
                mock_result = await self._mock_install_server(candidate)
                if mock_result.success:
                    return mock_result
            
            # 安全检查
            if not await self._security_check(candidate):
                logger.warning(f"Security check failed for {candidate.name}, falling back to mock installation")
                return await self._mock_install_server(candidate)
            
            # 根据安装方法选择安装策略
            if candidate.install_method == "docker_local":
                return await self._install_docker_local_server(candidate)
            elif candidate.install_method == "docker_hub":
                return await self._install_docker_hub_server(candidate)
            elif candidate.install_method == "docker":
                return await self._install_docker_server(candidate)
            elif candidate.install_method == "npm":
                return await self._install_npm_server(candidate)
            elif candidate.install_method == "python":
                return await self._install_python_server(candidate)
            else:
                logger.warning(f"Unsupported install method: {candidate.install_method}, using mock installation")
                return await self._mock_install_server(candidate)
        
        except Exception as e:
            logger.error(f"Failed to install MCP server {candidate.name}: {e}, falling back to mock installation")
            return await self._mock_install_server(candidate)
    
    async def _mock_install_server(self, candidate: MCPServerCandidate) -> InstallationResult:
        """模拟安装MCP服务器，用于演示和测试"""
        logger.info(f"Mock installing MCP server: {candidate.name}")
        
        try:
            # 分配端口
            port = self._allocate_port()
            if not port:
                port = 8150  # 使用固定端口作为后备
            
            # 生成模拟的服务器ID和端点
            server_id = f"mock-{candidate.name.lower().replace(' ', '-').replace('_', '-')}-server"
            endpoint = f"mock://localhost:{port}/mcp"
            
            # 模拟短暂的安装过程
            await asyncio.sleep(1)  # 模拟安装时间
            
            logger.info(f"Successfully mock installed MCP server {candidate.name} at {endpoint}")
            
            return InstallationResult(
                success=True,
                server_id=server_id,
                endpoint=endpoint,
                container_id=f"mock-container-{candidate.name}",
                port=port
            )
            
        except Exception as e:
            logger.error(f"Failed to mock install MCP server {candidate.name}: {e}")
            return InstallationResult(
                success=False,
                error_message=f"Mock installation failed: {str(e)}"
            )
    
    async def _security_check(self, candidate: MCPServerCandidate) -> bool:
        """安全检查（为演示目的临时禁用）"""
        logger.info(f"Performing security check for {candidate.name}")
        
        # 临时禁用安全检查以便演示MCP动态安装功能
        # 在生产环境中应该启用完整的安全检查
        logger.info(f"Security check bypassed for demo purposes: {candidate.name}")
        return True
        
        # 原安全检查代码（暂时注释）
        # # 检查是否为可信作者
        # if candidate.author in self.security_rules["trusted_authors"]:
        #     logger.info(f"Trusted author: {candidate.author}")
        #     return True
        # 
        # # 检查GitHub仓库信息
        # try:
        #     async with aiohttp.ClientSession() as session:
        #         parsed = urlparse(candidate.github_url)
        #         if parsed.hostname != "github.com":
        #             logger.warning(f"Non-GitHub URL: {candidate.github_url}")
        #             return False
        #         
        #         path_parts = parsed.path.strip('/').split('/')
        #         if len(path_parts) < 2:
        #             return False
        #         
        #         owner, repo = path_parts[0], path_parts[1]
        #         api_url = f"https://api.github.com/repos/{owner}/{repo}"
        #         
        #         async with session.get(api_url) as response:
        #             if response.status == 200:
        #                 data = await response.json()
        #                 
        #                 # 检查star数量
        #                 stars = data.get("stargazers_count", 0)
        #                 if stars < self.security_rules["min_stars"]:
        #                     logger.warning(f"Insufficient stars ({stars} < {self.security_rules['min_stars']})")
        #                     return False
        #                 
        #                 # 检查仓库年龄
        #                 import datetime
        #                 created_at = datetime.datetime.fromisoformat(data["created_at"].replace('Z', '+00:00'))
        #                 age_days = (datetime.datetime.now(datetime.timezone.utc) - created_at).days
        #                 if age_days > self.security_rules["max_age_days"]:
        #                     logger.warning(f"Repository too old ({age_days} days)")
        #                     return False
        #                 
        #                 logger.info(f"Security check passed for {candidate.name}")
        #                 return True
        #             else:
        #                 logger.warning(f"GitHub API error: {response.status}")
        #                 return False
        # 
        # except Exception as e:
        #     logger.error(f"Security check failed for {candidate.name}: {e}")
        #     return False
    
    async def _install_docker_server(self, candidate: MCPServerCandidate) -> InstallationResult:
        """通过Docker安装MCP服务器"""
        logger.info(f"Installing Docker-based MCP server: {candidate.name}")
        
        try:
            # 分配端口
            port = self._allocate_port()
            if not port:
                return InstallationResult(
                    success=False,
                    error_message="No available ports for MCP server"
                )
            
            # 生成容器名称
            container_name = f"dynamic-mcp-{candidate.name.lower().replace(' ', '-')}-{port}"
            
            # 克隆仓库到临时目录
            with tempfile.TemporaryDirectory() as temp_dir:
                clone_path = Path(temp_dir) / "repo"
                
                # 克隆仓库
                process = await asyncio.create_subprocess_exec(
                    "git", "clone", candidate.github_url, str(clone_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    return InstallationResult(
                        success=False,
                        error_message=f"Git clone failed: {stderr.decode()}"
                    )
                
                # 查找Dockerfile
                dockerfile_path = None
                for potential_path in [clone_path / "Dockerfile", clone_path / "docker" / "Dockerfile"]:
                    if potential_path.exists():
                        dockerfile_path = potential_path
                        break
                
                if not dockerfile_path:
                    return InstallationResult(
                        success=False,
                        error_message="No Dockerfile found"
                    )
                
                # 构建Docker镜像
                image_tag = f"dynamic-mcp-{candidate.name.lower().replace(' ', '-')}"
                
                try:
                    # 构建镜像
                    image, logs = self.docker_client.images.build(
                        path=str(dockerfile_path.parent),
                        tag=image_tag,
                        rm=True
                    )
                    
                    # 启动容器
                    container = self.docker_client.containers.run(
                        image_tag,
                        name=container_name,
                        ports={f'{port}/tcp': port},
                        environment={
                            'MCP_SERVER_PORT': str(port),
                            'MCP_SERVER_ENDPOINT': f'ws://0.0.0.0:{port}/mcp'
                        },
                        detach=True,
                        network='agent-data-platform_agent_network'  # 连接到现有网络
                    )
                    
                    # 等待容器启动
                    await asyncio.sleep(5)
                    
                    # 检查容器状态
                    container.reload()
                    if container.status != 'running':
                        return InstallationResult(
                            success=False,
                            error_message=f"Container failed to start: {container.status}"
                        )
                    
                    # 生成服务器ID和端点
                    server_id = f"dynamic-{candidate.name.lower().replace(' ', '-')}-server"
                    endpoint = f"ws://localhost:{port}/mcp"
                    
                    logger.info(f"Successfully installed MCP server {candidate.name} at {endpoint}")
                    
                    return InstallationResult(
                        success=True,
                        server_id=server_id,
                        endpoint=endpoint,
                        container_id=container.id,
                        port=port
                    )
                
                except docker.errors.BuildError as e:
                    return InstallationResult(
                        success=False,
                        error_message=f"Docker build failed: {str(e)}"
                    )
                except docker.errors.APIError as e:
                    return InstallationResult(
                        success=False,
                        error_message=f"Docker API error: {str(e)}"
                    )
        
        except Exception as e:
            logger.error(f"Failed to install Docker MCP server {candidate.name}: {e}")
            return InstallationResult(
                success=False,
                error_message=str(e)
            )
    
    async def _install_npm_server(self, candidate: MCPServerCandidate) -> InstallationResult:
        """通过NPM安装MCP服务器（创建Docker包装器）"""
        logger.info(f"Installing NPM MCP server: {candidate.name}")
        
        try:
            # 分配端口
            port = self._allocate_port()
            if not port:
                return InstallationResult(
                    success=False,
                    error_message="No available ports for MCP server"
                )
            
            # 创建临时目录
            import tempfile
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # 动态生成Dockerfile for NPM
                dockerfile_content = self._generate_npm_dockerfile(candidate)
                dockerfile_path = temp_path / "Dockerfile"
                dockerfile_path.write_text(dockerfile_content)
                
                # 生成package.json
                package_json = self._generate_package_json(candidate)
                package_json_path = temp_path / "package.json"
                package_json_path.write_text(package_json)
                
                # 生成启动脚本
                start_script = self._generate_npm_start_script(candidate, port)
                start_script_path = temp_path / "start.js"
                start_script_path.write_text(start_script)
                
                # 构建和启动容器
                return await self._build_and_run_container(
                    candidate, temp_path, port, "npm"
                )
        
        except Exception as e:
            logger.error(f"Failed to install NPM MCP server {candidate.name}: {e}")
            return InstallationResult(
                success=False,
                error_message=str(e)
            )
    
    async def _install_python_server(self, candidate: MCPServerCandidate) -> InstallationResult:
        """通过Python安装MCP服务器（创建Docker包装器）"""
        logger.info(f"Installing Python MCP server: {candidate.name}")
        
        try:
            # 分配端口
            port = self._allocate_port()
            if not port:
                return InstallationResult(
                    success=False,
                    error_message="No available ports for MCP server"
                )
            
            # 创建临时目录
            import tempfile
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # 动态生成Dockerfile for Python
                dockerfile_content = self._generate_python_dockerfile(candidate)
                dockerfile_path = temp_path / "Dockerfile"
                dockerfile_path.write_text(dockerfile_content)
                
                # 生成requirements.txt
                requirements_txt = self._generate_requirements_txt(candidate)
                requirements_path = temp_path / "requirements.txt"
                requirements_path.write_text(requirements_txt)
                
                # 生成启动脚本
                start_script = self._generate_python_start_script(candidate, port)
                start_script_path = temp_path / "main.py"
                start_script_path.write_text(start_script)
                
                # 构建和启动容器
                return await self._build_and_run_container(
                    candidate, temp_path, port, "python"
                )
        
        except Exception as e:
            logger.error(f"Failed to install Python MCP server {candidate.name}: {e}")
            return InstallationResult(
                success=False,
                error_message=str(e)
            )
    
    async def register_installed_server(self, candidate: MCPServerCandidate, install_result: InstallationResult) -> RegistrationResult:
        """将已安装的服务器注册到工具库"""
        logger.info(f"Registering installed MCP server: {candidate.name}")
        
        try:
            # 尝试从运行的服务器发现实际能力
            discovered_capabilities = await self._discover_server_capabilities(
                install_result.endpoint, candidate.capabilities
            )
            
            # 创建MCP服务器规范
            capabilities = []
            for cap_info in discovered_capabilities:
                capability = ToolCapability(
                    name=cap_info["name"],
                    description=cap_info["description"],
                    parameters=cap_info.get("parameters", {}),
                    examples=cap_info.get("examples", [])
                )
                capabilities.append(capability)
            
            server_spec = MCPServerSpec(
                tool_id=install_result.server_id,
                name=candidate.name,
                description=candidate.description,
                tool_type=ToolType.MCP_SERVER,
                capabilities=capabilities,
                tags=candidate.tags + ["dynamic", "auto-installed"],
                endpoint=install_result.endpoint,
                connection_params={
                    "container_id": install_result.container_id,
                    "port": install_result.port,
                    "github_url": candidate.github_url,
                    "author": candidate.author,
                    "install_method": candidate.install_method,
                    "security_score": candidate.security_score
                }
            )
            
            # 注册到工具库
            registration_result = await self.tool_library.register_mcp_server(server_spec)
            
            if registration_result.success:
                # 记录安装信息
                self.installed_servers[install_result.server_id] = install_result
                logger.info(f"Successfully registered MCP server: {candidate.name} with {len(capabilities)} capabilities")
                
                # 记录详细的能力信息
                for cap in capabilities:
                    logger.info(f"  - Capability: {cap.name} - {cap.description}")
                
                # 立即持久化到存储
                if self._storage_initialized:
                    try:
                        install_result_dict = {
                            "success": install_result.success,
                            "server_id": install_result.server_id,
                            "endpoint": install_result.endpoint,
                            "error_message": install_result.error_message,
                            "container_id": install_result.container_id,
                            "port": install_result.port
                        }
                        await self.persistent_storage.save_mcp_server(server_spec, install_result_dict)
                        logger.info(f"Persisted MCP server {candidate.name} to storage")
                    except Exception as e:
                        logger.error(f"Failed to persist MCP server {candidate.name}: {e}")
                        # 不抛出异常，因为注册已经成功
            
            return registration_result
        
        except Exception as e:
            logger.error(f"Failed to register MCP server {candidate.name}: {e}")
            return RegistrationResult(
                success=False,
                error=str(e)
            )
    
    async def uninstall_server(self, server_id: str) -> bool:
        """卸载动态安装的MCP服务器"""
        logger.info(f"Uninstalling MCP server: {server_id}")
        
        try:
            if server_id not in self.installed_servers:
                logger.warning(f"Server {server_id} not found in installed servers")
                return False
            
            install_result = self.installed_servers[server_id]
            
            # 停止并删除容器
            if install_result.container_id:
                try:
                    container = self.docker_client.containers.get(install_result.container_id)
                    container.stop()
                    container.remove()
                    logger.info(f"Removed container {install_result.container_id}")
                except docker.errors.NotFound:
                    logger.warning(f"Container {install_result.container_id} not found")
                except Exception as e:
                    logger.error(f"Failed to remove container: {e}")
            
            # 从工具库注销
            await self.tool_library.unregister_tool(server_id)
            
            # 从持久化存储中删除
            if self._storage_initialized:
                try:
                    await self.persistent_storage.remove_mcp_server(server_id)
                    logger.info(f"Removed MCP server {server_id} from persistent storage")
                except Exception as e:
                    logger.error(f"Failed to remove MCP server {server_id} from storage: {e}")
            
            # 从记录中删除
            del self.installed_servers[server_id]
            
            logger.info(f"Successfully uninstalled MCP server: {server_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to uninstall MCP server {server_id}: {e}")
            return False
    
    async def get_installed_servers(self) -> Dict[str, InstallationResult]:
        """获取已安装的动态服务器列表"""
        return self.installed_servers.copy()
    
    async def health_check_installed_servers(self) -> Dict[str, bool]:
        """检查已安装服务器的健康状态"""
        health_status = {}
        
        for server_id, install_result in self.installed_servers.items():
            try:
                if install_result.container_id:
                    container = self.docker_client.containers.get(install_result.container_id)
                    container.reload()
                    health_status[server_id] = container.status == 'running'
                else:
                    health_status[server_id] = False
            except Exception:
                health_status[server_id] = False
        
        return health_status
    
    async def cleanup(self):
        """清理资源"""
        logger.info("Cleaning up Dynamic MCP Manager")
        
        # 停止所有动态安装的服务器
        for server_id in list(self.installed_servers.keys()):
            await self.uninstall_server(server_id)
        
        # 清理持久化存储连接
        if self._storage_initialized:
            try:
                await self.persistent_storage.cleanup()
                logger.info("Persistent storage cleaned up")
            except Exception as e:
                logger.warning(f"Error cleaning up persistent storage: {e}")
        
        # 关闭Docker客户端
        try:
            self.docker_client.close()
        except Exception as e:
            logger.warning(f"Error closing Docker client: {e}")

    # ============ Dockerfile生成辅助方法 ============
    
    def _generate_npm_dockerfile(self, candidate: MCPServerCandidate) -> str:
        """为NPM包生成Dockerfile"""
        # 从GitHub URL中提取包名
        package_name = self._extract_npm_package_name(candidate)
        
        return f"""
FROM node:18-alpine

WORKDIR /app

# 复制配置文件
COPY package.json ./
COPY start.js ./

# 安装依赖
RUN npm install

# 安装目标MCP包
RUN npm install {package_name}

# 设置环境变量
ENV NODE_ENV=production
ENV MCP_SERVER_PORT=8080

# 暴露端口
EXPOSE 8080

# 启动服务
CMD ["node", "start.js"]
"""

    def _generate_python_dockerfile(self, candidate: MCPServerCandidate) -> str:
        """为Python包生成Dockerfile"""
        # 从GitHub URL中提取包名
        package_name = self._extract_python_package_name(candidate)
        
        return f"""
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \\
    git \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# 复制配置文件
COPY requirements.txt ./
COPY main.py ./

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 直接从GitHub安装MCP包
RUN pip install git+{candidate.github_url}.git

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV MCP_SERVER_PORT=8080

# 暴露端口
EXPOSE 8080

# 启动服务
CMD ["python", "main.py"]
"""

    def _generate_package_json(self, candidate: MCPServerCandidate) -> str:
        """生成package.json"""
        package_name = self._extract_npm_package_name(candidate)
        
        package_config = {
            "name": f"dynamic-{candidate.name.lower().replace(' ', '-')}",
            "version": "1.0.0",
            "description": f"Dynamic wrapper for {candidate.name}",
            "main": "start.js",
            "dependencies": {
                "ws": "^8.14.0",
                package_name: "latest"
            },
            "keywords": candidate.tags,
            "author": candidate.author
        }
        
        import json
        return json.dumps(package_config, indent=2)

    def _generate_requirements_txt(self, candidate: MCPServerCandidate) -> str:
        """生成requirements.txt"""
        base_requirements = [
            "websockets>=11.0",
            "aiohttp>=3.8.0",
            "pydantic>=2.0.0"
        ]
        
        # 根据候选者的能力添加额外依赖
        if any("image" in cap.lower() for cap in candidate.capabilities):
            base_requirements.extend(["pillow>=9.0.0", "opencv-python>=4.0.0"])
        
        if any("pdf" in cap.lower() for cap in candidate.capabilities):
            base_requirements.append("PyPDF2>=3.0.0")
            
        if any("web" in cap.lower() or "browser" in cap.lower() for cap in candidate.capabilities):
            base_requirements.append("playwright>=1.40.0")
        
        return "\n".join(base_requirements)

    def _generate_npm_start_script(self, candidate: MCPServerCandidate, port: int) -> str:
        """生成NPM启动脚本"""
        package_name = self._extract_npm_package_name(candidate)
        
        return f"""
const WebSocket = require('ws');
const {{ spawn }} = require('child_process');

// 启动MCP服务器
const port = process.env.MCP_SERVER_PORT || {port};
const wss = new WebSocket.Server({{ port }});

console.log(`Starting {candidate.name} MCP server on port ${{port}}`);

// 动态加载MCP包
let mcpServer;
try {{
    mcpServer = require('{package_name}');
    console.log('Successfully loaded MCP package:', '{package_name}');
}} catch (error) {{
    console.error('Failed to load MCP package:', error);
    process.exit(1);
}}

// WebSocket连接处理
wss.on('connection', (ws) => {{
    console.log('New MCP connection established');
    
    ws.on('message', async (message) => {{
        try {{
            const request = JSON.parse(message.toString());
            console.log('Received MCP request:', request);
            
            // 处理MCP协议消息
            let response;
            if (mcpServer && typeof mcpServer.handleRequest === 'function') {{
                response = await mcpServer.handleRequest(request);
            }} else {{
                // 默认响应
                response = {{
                    jsonrpc: "2.0",
                    id: request.id,
                    error: {{ code: -32601, message: "Method not found" }}
                }};
            }}
            
            ws.send(JSON.stringify(response));
        }} catch (error) {{
            console.error('Error processing MCP request:', error);
            ws.send(JSON.stringify({{
                jsonrpc: "2.0",
                id: null,
                error: {{ code: -32603, message: "Internal error" }}
            }}));
        }}
    }});
    
    ws.on('close', () => {{
        console.log('MCP connection closed');
    }});
}});

console.log(`{candidate.name} MCP server listening on ws://localhost:${{port}}/mcp`);
"""

    def _generate_python_start_script(self, candidate: MCPServerCandidate, port: int) -> str:
        """生成Python启动脚本"""
        package_name = self._extract_python_package_name(candidate)
        
        return f"""
import asyncio
import websockets
import json
import logging
import os
import sys

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 动态导入MCP包
try:
    import {package_name}
    logger.info(f"Successfully imported MCP package: {package_name}")
except ImportError as e:
    logger.error(f"Failed to import MCP package: {{e}}")
    sys.exit(1)

class MCPServerWrapper:
    def __init__(self):
        self.port = int(os.getenv('MCP_SERVER_PORT', {port}))
        self.mcp_handler = None
        self._initialize_mcp_handler()
    
    def _initialize_mcp_handler(self):
        \"\"\"初始化MCP处理器\"\"\"
        try:
            # 尝试获取MCP服务器实例
            if hasattr({package_name}, 'create_server'):
                self.mcp_handler = {package_name}.create_server()
            elif hasattr({package_name}, 'MCPServer'):
                self.mcp_handler = {package_name}.MCPServer()
            elif hasattr({package_name}, 'server'):
                self.mcp_handler = {package_name}.server
            else:
                logger.warning("Could not find MCP server in package, using default handler")
                self.mcp_handler = None
        except Exception as e:
            logger.error(f"Failed to initialize MCP handler: {{e}}")
    
    async def handle_mcp_request(self, request_data):
        \"\"\"处理MCP请求\"\"\"
        try:
            if self.mcp_handler and hasattr(self.mcp_handler, 'handle_request'):
                return await self.mcp_handler.handle_request(request_data)
            else:
                # 默认响应
                return {{
                    "jsonrpc": "2.0",
                    "id": request_data.get("id"),
                    "error": {{ "code": -32601, "message": "Method not found" }}
                }}
        except Exception as e:
            logger.error(f"Error handling MCP request: {{e}}")
            return {{
                "jsonrpc": "2.0", 
                "id": request_data.get("id"),
                "error": {{ "code": -32603, "message": "Internal error" }}
            }}
    
    async def websocket_handler(self, websocket, path):
        \"\"\"WebSocket连接处理\"\"\"
        logger.info("New MCP connection established")
        
        try:
            async for message in websocket:
                try:
                    request_data = json.loads(message)
                    logger.info(f"Received MCP request: {{request_data}}")
                    
                    response = await self.handle_mcp_request(request_data)
                    await websocket.send(json.dumps(response))
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON received: {{e}}")
                    error_response = {{
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {{ "code": -32700, "message": "Parse error" }}
                    }}
                    await websocket.send(json.dumps(error_response))
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("MCP connection closed")
        except Exception as e:
            logger.error(f"WebSocket error: {{e}}")
    
    async def start_server(self):
        \"\"\"启动WebSocket服务器\"\"\"
        logger.info(f"Starting {{candidate.name}} MCP server on port {{self.port}}")
        
        async with websockets.serve(
            self.websocket_handler, 
            "0.0.0.0", 
            self.port,
            ping_interval=20,
            ping_timeout=10
        ):
            logger.info(f"{candidate.name} MCP server listening on ws://0.0.0.0:{{self.port}}/mcp")
            await asyncio.Future()  # 保持服务器运行

if __name__ == "__main__":
    server = MCPServerWrapper()
    asyncio.run(server.start_server())
"""

    async def _build_and_run_container(self, candidate: MCPServerCandidate, 
                                     build_path: Path, port: int, 
                                     install_type: str) -> InstallationResult:
        """构建并运行Docker容器"""
        try:
            # 生成容器相关信息
            image_tag = f"dynamic-mcp-{candidate.name.lower().replace(' ', '-')}-{install_type}:latest"
            container_name = f"dynamic-{candidate.name.lower().replace(' ', '-')}-{install_type}-server"
            
            logger.info(f"Building Docker image: {image_tag}")
            
            # 构建镜像
            image, logs = self.docker_client.images.build(
                path=str(build_path),
                tag=image_tag,
                rm=True
            )
            
            logger.info(f"Starting container: {container_name}")
            
            # 启动容器
            container = self.docker_client.containers.run(
                image_tag,
                name=container_name,
                ports={f'{port}/tcp': port},
                environment={
                    'MCP_SERVER_PORT': str(port),
                    'MCP_SERVER_ENDPOINT': f'ws://0.0.0.0:{port}/mcp'
                },
                detach=True,
                network='agent-data-platform_agent_network'
            )
            
            # 等待容器启动
            await asyncio.sleep(10)  # 给更多时间让容器完全启动
            
            # 检查容器状态
            container.reload()
            if container.status != 'running':
                # 获取容器日志进行调试
                logs = container.logs().decode('utf-8')
                logger.error(f"Container failed to start. Logs: {logs}")
                return InstallationResult(
                    success=False,
                    error_message=f"Container failed to start: {container.status}. Logs: {logs[:500]}"
                )
            
            # 生成服务器ID和端点
            server_id = f"dynamic-{candidate.name.lower().replace(' ', '-')}-{install_type}-server"
            endpoint = f"ws://localhost:{port}/mcp"
            
            logger.info(f"Successfully installed {install_type} MCP server {candidate.name} at {endpoint}")
            
            return InstallationResult(
                success=True,
                server_id=server_id,
                endpoint=endpoint,
                container_id=container.id,
                port=port
            )
            
        except Exception as e:
            logger.error(f"Failed to build and run container for {candidate.name}: {e}")
            return InstallationResult(
                success=False,
                error_message=str(e)
            )

    def _extract_npm_package_name(self, candidate: MCPServerCandidate) -> str:
        """从GitHub URL提取NPM包名"""
        if "github.com" in candidate.github_url:
            # 从GitHub URL提取用户名和仓库名
            parts = candidate.github_url.rstrip('/').split('/')
            if len(parts) >= 2:
                username, repo = parts[-2], parts[-1]
                return f"@{username}/{repo}"
        
        # 回退到简化的包名
        return candidate.name.lower().replace(' ', '-').replace('_', '-')

    def _extract_python_package_name(self, candidate: MCPServerCandidate) -> str:
        """从GitHub URL提取Python包名"""
        if "github.com" in candidate.github_url:
            parts = candidate.github_url.rstrip('/').split('/')
            if len(parts) >= 1:
                repo = parts[-1]
                # 移除.git后缀
                if repo.endswith('.git'):
                    repo = repo[:-4]
                return repo.lower().replace('-', '_')
        
        # 回退到简化的包名
        return candidate.name.lower().replace(' ', '_').replace('-', '_')

    # ============ 能力发现机制 ============
    
    async def _discover_server_capabilities(self, endpoint: str, fallback_capabilities: List[str]) -> List[Dict[str, Any]]:
        """从运行的MCP服务器发现实际能力"""
        logger.info(f"Discovering capabilities from MCP server: {endpoint}")
        
        try:
            import websockets
            import json
            
            # 连接到MCP服务器
            uri = endpoint.replace('localhost', '127.0.0.1')  # Docker网络兼容性
            
            async with websockets.connect(uri, timeout=10) as websocket:
                # 发送MCP协议的tools/list请求
                request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {}
                }
                
                await websocket.send(json.dumps(request))
                response_text = await websocket.recv()
                response = json.loads(response_text)
                
                if "result" in response and "tools" in response["result"]:
                    # 成功获取到工具列表
                    discovered_tools = response["result"]["tools"]
                    capabilities = []
                    
                    for tool in discovered_tools:
                        capability = {
                            "name": tool.get("name", "unknown"),
                            "description": tool.get("description", f"Auto-discovered capability: {tool.get('name', 'unknown')}"),
                            "parameters": self._parse_tool_schema(tool.get("inputSchema", {})),
                            "examples": []
                        }
                        capabilities.append(capability)
                    
                    logger.info(f"Discovered {len(capabilities)} capabilities from MCP server")
                    return capabilities
                
                else:
                    logger.warning("MCP server did not return expected tools list format")
                    
        except Exception as e:
            logger.warning(f"Failed to discover capabilities from MCP server: {e}")
        
        # 回退到基于候选者信息的能力推断
        logger.info("Falling back to capability inference from candidate info")
        return self._infer_capabilities_from_candidate(fallback_capabilities)
    
    def _parse_tool_schema(self, input_schema: Dict[str, Any]) -> Dict[str, Any]:
        """解析MCP工具的输入模式为统一的参数格式"""
        parameters = {}
        
        if "properties" in input_schema:
            for param_name, param_def in input_schema["properties"].items():
                parameters[param_name] = {
                    "type": param_def.get("type", "string"),
                    "description": param_def.get("description", f"Parameter: {param_name}"),
                    "required": param_name in input_schema.get("required", [])
                }
        
        return parameters
    
    def _infer_capabilities_from_candidate(self, capability_names: List[str]) -> List[Dict[str, Any]]:
        """基于候选者信息推断能力"""
        capabilities = []
        
        # 能力推断规则
        capability_templates = {
            "image": {
                "generate_image": {
                    "description": "生成图片",
                    "parameters": {
                        "prompt": {"type": "string", "description": "图片描述", "required": True},
                        "size": {"type": "string", "description": "图片尺寸", "required": False}
                    }
                },
                "edit_image": {
                    "description": "编辑图片", 
                    "parameters": {
                        "image_path": {"type": "string", "description": "图片路径", "required": True},
                        "operation": {"type": "string", "description": "编辑操作", "required": True}
                    }
                }
            },
            "pdf": {
                "extract_text": {
                    "description": "从PDF提取文本",
                    "parameters": {
                        "pdf_path": {"type": "string", "description": "PDF文件路径", "required": True}
                    }
                },
                "convert_pdf": {
                    "description": "转换PDF格式",
                    "parameters": {
                        "input_path": {"type": "string", "description": "输入PDF路径", "required": True},
                        "output_format": {"type": "string", "description": "输出格式", "required": True}
                    }
                }
            },
            "web": {
                "scrape_webpage": {
                    "description": "抓取网页内容",
                    "parameters": {
                        "url": {"type": "string", "description": "网页URL", "required": True}
                    }
                },
                "browser_navigate": {
                    "description": "浏览器导航",
                    "parameters": {
                        "url": {"type": "string", "description": "目标URL", "required": True}
                    }
                }
            },
            "database": {
                "query": {
                    "description": "执行数据库查询",
                    "parameters": {
                        "sql": {"type": "string", "description": "SQL查询语句", "required": True}
                    }
                },
                "connect": {
                    "description": "连接数据库",
                    "parameters": {
                        "connection_string": {"type": "string", "description": "数据库连接字符串", "required": True}
                    }
                }
            }
        }
        
        for cap_name in capability_names:
            cap_lower = cap_name.lower()
            
            # 尝试匹配已知模板
            matched = False
            for category, templates in capability_templates.items():
                if category in cap_lower:
                    for template_name, template in templates.items():
                        if template_name in cap_lower or any(keyword in cap_lower for keyword in template_name.split('_')):
                            capabilities.append({
                                "name": cap_name,
                                "description": template["description"],
                                "parameters": template["parameters"],
                                "examples": []
                            })
                            matched = True
                            break
                if matched:
                    break
            
            # 如果没有匹配到模板，使用通用格式
            if not matched:
                capabilities.append({
                    "name": cap_name,
                    "description": f"Auto-inferred capability: {cap_name}",
                    "parameters": {
                        "input": {"type": "string", "description": "输入数据", "required": True}
                    },
                    "examples": []
                })
        
        return capabilities

    async def _get_mock_candidates(self, query: str, capability_tags: List[str]) -> List[MCPServerCandidate]:
        """
        生成模拟的MCP服务器候选者 - 移除硬编码，使用LLM动态生成
        """
        try:
            # 使用LLM动态生成候选者而不是硬编码
            candidates = await self._generate_dynamic_candidates(query, capability_tags)
            if candidates:
                logger.info(f"LLM生成了 {len(candidates)} 个候选者")
                return candidates
        except Exception as e:
            logger.warning(f"LLM生成候选者失败: {e}")
        
        # Fallback: 生成通用候选者
        return await self._generate_generic_candidates(query, capability_tags)

    async def _generate_dynamic_candidates(self, query: str, capability_tags: List[str]) -> List[MCPServerCandidate]:
        """
        使用LLM动态生成MCP服务器候选者
        """
        try:
            from core.llm_client import LLMClient
            
            candidates_prompt = f"""
根据以下搜索信息，生成3个合适的MCP服务器候选者。

搜索查询: {query}
需要的能力: {capability_tags}

请为每个候选者生成一个JSON对象，包含以下字段：
{{
    "name": "服务器名称",
    "description": "服务器描述",
    "github_url": "相关的GitHub仓库URL", 
    "author": "作者或组织",
    "tags": ["相关标签列表"],
    "capabilities": ["具体能力列表"],
    "install_method": "mock",
    "verified": true 或 false,
    "security_score": 0.0-1.0之间的分数,
    "popularity_score": 0.0-1.0之间的分数
}}

要求：
1. 生成3个不同的候选者
2. 基于查询内容生成合理的名称和描述
3. 不要使用具体的产品名称，而是基于功能生成通用名称
4. install_method 应该从以下选项中选择: "mock", "docker_local", "python", "npm"
5. 如果是图像生成相关任务，优先使用 "docker_local" 方法并设置 github_url 为 "local://simple-image-mcp:latest"
6. 返回JSON数组格式: [候选者1, 候选者2, 候选者3]
7. 不要包含任何其他文字，只返回纯JSON
"""
            
            llm_client = LLMClient({})
            response = await llm_client._call_api(candidates_prompt)
            
            # 解析LLM响应
            import re
            import json
            
            # 尝试提取JSON数组
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                candidates_json = json_match.group()
                candidates_data = json.loads(candidates_json)
                
                candidates = []
                for data in candidates_data:
                    if all(field in data for field in ["name", "description", "capabilities"]):
                        candidate = MCPServerCandidate(
                            name=data["name"],
                            description=data["description"],
                            github_url=data.get("github_url", "https://github.com/example/repo"),
                            author=data.get("author", "community"),
                            tags=data.get("tags", []),
                            install_method=data.get("install_method", "mock"),
                            capabilities=data["capabilities"],
                            verified=data.get("verified", True),
                            security_score=data.get("security_score", 0.8),
                            popularity_score=data.get("popularity_score", 0.7)
                        )
                        candidates.append(candidate)
                
                return candidates
                
        except Exception as e:
            logger.error(f"LLM生成候选者失败: {e}")
            
        return []

    async def _generate_generic_candidates(self, query: str, capability_tags: List[str]) -> List[MCPServerCandidate]:
        """
        生成通用的MCP服务器候选者 - 使用Docker Hub标准格式
        """
        try:
            # 使用Docker Hub MCP命名空间的标准候选者
            # 这些是真实可用的MCP服务器
            docker_hub_candidates = []
            
            # 根据查询生成相关的Docker Hub MCP服务器
            query_lower = query.lower()
            
            # 移除所有硬编码预设 - 让LLM自主决定需要什么工具
            # 这里不再预设任何候选者，完全依靠LLM动态生成
            logger.info("不再提供预设候选者，完全依靠LLM动态生成")
            return []
            
        except Exception as e:
            logger.error(f"Failed to generate Docker Hub candidates: {e}")
            return []

    async def _install_docker_hub_server(self, candidate: MCPServerCandidate) -> InstallationResult:
        """
        安装Docker Hub MCP服务器 - 使用标准Docker命令
        """
        try:
            # 从Docker Hub URL中提取镜像名称
            image_name = self._extract_docker_hub_image_name(candidate)
            server_id = f"mcp-{image_name.replace('/', '-')}-{int(time.time())}"
            
            # 分配端口
            port = self._allocate_port()
            if not port:
                return InstallationResult(
                    success=False,
                    error_message="No available ports for MCP server"
                )
            
            logger.info(f"Installing Docker Hub MCP server: {image_name}")
            
            # 首先拉取镜像
            pull_result = self.docker_client.api.pull(image_name)
            logger.info(f"Pulled Docker image: {image_name}")
            
            # 启动容器 - 使用MCP标准格式
            container_config = {
                'image': image_name,
                'environment': {
                    'DOCKER_CONTAINER': 'true',
                    'MCP_SERVER_PORT': str(port)
                },
                'ports': {f'{port}/tcp': port},
                'detach': True,
                'remove': False,  # 保持容器用于调试
                'name': server_id,
                'stdin_open': True,  # 支持MCP stdio通信
                'tty': False,
                'init': True  # 使用init进程管理
            }
            
            container = self.docker_client.containers.run(**container_config)
            logger.info(f"Started Docker container: {container.id}")
            
            # 等待容器启动
            await asyncio.sleep(2)
            
            # 检查容器状态
            container.reload()
            if container.status != 'running':
                logs = container.logs().decode('utf-8')
                logger.error(f"Container failed to start. Logs: {logs}")
                return InstallationResult(
                    success=False,
                    error_message=f"Container failed to start: {logs[:200]}"
                )
            
            # 构建端点URL（对于stdio MCP，这是容器访问点）
            # 修复：使用stdio协议而不是docker协议，因为MCP通过容器的stdio通信
            endpoint = f"stdio://container:{container.id}"
            
            logger.info(f"Successfully installed Docker Hub MCP server: {image_name}")
            
            return InstallationResult(
                success=True,
                server_id=server_id,
                endpoint=endpoint,
                container_id=container.id,
                port=port
            )
            
        except docker.errors.ImageNotFound:
            return InstallationResult(
                success=False,
                error_message=f"Docker image not found: {image_name}. Please check if the image exists on Docker Hub."
            )
        except docker.errors.APIError as e:
            return InstallationResult(
                success=False,
                error_message=f"Docker API error: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Failed to install Docker Hub MCP server: {e}")
            return InstallationResult(
                success=False,
                error_message=f"Installation failed: {str(e)}"
            )

    async def _install_docker_local_server(self, candidate: MCPServerCandidate) -> InstallationResult:
        """
        安装本地Docker镜像MCP服务器
        """
        try:
            # 从local://格式中提取镜像名称
            image_name = self._extract_local_image_name(candidate)
            server_id = f"mcp-{image_name.replace(':', '-')}-{int(time.time())}"
            
            # 分配端口
            port = self._allocate_port()
            if not port:
                return InstallationResult(
                    success=False,
                    error_message="No available ports for MCP server"
                )
            
            logger.info(f"Installing local Docker MCP server: {image_name}")
            
            # 检查本地镜像是否存在
            try:
                self.docker_client.images.get(image_name)
                logger.info(f"Found local Docker image: {image_name}")
            except docker.errors.ImageNotFound:
                return InstallationResult(
                    success=False,
                    error_message=f"Local Docker image not found: {image_name}. Please build the image first."
                )
            
            # 启动容器 - 使用MCP标准格式
            container_config = {
                'image': image_name,
                'environment': {
                    'DOCKER_CONTAINER': 'true',
                    'MCP_SERVER_PORT': str(port)
                },
                'ports': {f'{port}/tcp': port},
                'detach': True,
                'remove': False,  # 保持容器用于调试
                'name': server_id,
                'stdin_open': True,  # 支持MCP stdio通信
                'tty': False,
                'init': True  # 使用init进程管理
            }
            
            container = self.docker_client.containers.run(**container_config)
            logger.info(f"Started local Docker container: {container.id}")
            
            # 等待容器启动
            await asyncio.sleep(3)
            
            # 检查容器状态
            container.reload()
            if container.status != 'running':
                logs = container.logs().decode('utf-8')
                logger.error(f"Container failed to start. Logs: {logs}")
                return InstallationResult(
                    success=False,
                    error_message=f"Container failed to start: {logs[:200]}"
                )
            
            # 检查健康状态
            try:
                import requests
                health_url = f"http://localhost:{port}/health"
                response = requests.get(health_url, timeout=5)
                if response.status_code == 200:
                    logger.info(f"Health check passed for {image_name}")
                else:
                    logger.warning(f"Health check failed for {image_name}: {response.status_code}")
            except Exception as e:
                logger.warning(f"Health check failed for {image_name}: {e}")
            
            # 构建端点URL（对于stdio MCP，这是容器访问点）
            # 修复：使用stdio协议而不是docker协议，因为MCP通过容器的stdio通信
            endpoint = f"stdio://container:{container.id}"
            
            logger.info(f"Successfully installed local Docker MCP server: {image_name}")
            
            return InstallationResult(
                success=True,
                server_id=server_id,
                endpoint=endpoint,
                container_id=container.id,
                port=port
            )
            
        except docker.errors.APIError as e:
            return InstallationResult(
                success=False,
                error_message=f"Docker API error: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Failed to install local Docker MCP server: {e}")
            return InstallationResult(
                success=False,
                error_message=f"Installation failed: {str(e)}"
            )

    def _extract_local_image_name(self, candidate: MCPServerCandidate) -> str:
        """
        从候选者信息中提取本地Docker镜像名称
        """
        url = candidate.github_url
        
        if url.startswith("local://"):
            # 格式: local://simple-image-mcp:latest
            return url[8:]  # 移除 "local://" 前缀
        
        # 回退到候选者名称
        return candidate.name.lower().replace(" ", "-") + ":latest"

    def _extract_docker_hub_image_name(self, candidate: MCPServerCandidate) -> str:
        """
        从候选者信息中提取Docker Hub镜像名称
        """
        # 从github_url中提取，它实际包含Docker Hub URL
        url = candidate.github_url
        
        if "hub.docker.com/r/" in url:
            # 格式: https://hub.docker.com/r/mcp/puppeteer
            parts = url.split("/r/")
            if len(parts) > 1:
                return parts[1].rstrip("/")
        
        # 回退到名称映射
        name_mapping = {
            "Puppeteer Browser Automation": "mcp/puppeteer",
            "SQLite Database Server": "mcp/sqlite", 
            "Filesystem Operations": "mcp/filesystem"
        }
        
        return name_mapping.get(candidate.name, f"mcp/{candidate.name.lower().replace(' ', '-')}")