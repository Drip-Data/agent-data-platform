"""
动态MCP服务器管理器 - 无Docker版本
负责搜索、发现、安装和部署新的MCP服务器
"""

import asyncio
import json
import logging
import os
import tempfile
import aiohttp
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
import socket
import time

from .interfaces import InstallationResult
from .runners import BaseRunner, ProcessRunner

logger = logging.getLogger(__name__)

@dataclass
class MCPServerCandidate:
    """MCP服务器候选者"""
    name: str
    description: str
    github_url: str
    author: str
    tags: List[str]
    install_method: str  # python, nodejs, binary
    capabilities: List[str]
    verified: bool = False
    security_score: float = 0.0
    popularity_score: float = 0.0

@dataclass
class MCPSearchResult:
    """MCP搜索结果"""
    success: bool
    message: str
    installed_tools: List[Dict[str, Any]]
    error_message: Optional[str] = None

class DynamicMCPManager:
    """动态MCP服务器管理器 - 无Docker版本"""
    
    def __init__(self, runner: BaseRunner = None):
        self.runner = runner or ProcessRunner()
        self.installed_servers: Dict[str, InstallationResult] = {}
        self.registry_cache: Dict[str, List[MCPServerCandidate]] = {}
        
        # MCP服务器注册中心配置
        self.registries = {
            "github_public": "https://api.github.com/repos/modelcontextprotocol/servers/contents/src",
            "github_search": "https://api.github.com/search/repositories",
        }
        
        # 安全性检查规则
        self.security_rules = {
            "trusted_authors": ["anthropic", "modelcontextprotocol", "wong2"],
            "min_stars": 10,
            "max_age_days": 365,
        }
        
        logger.info("Dynamic MCP Manager initialized (ProcessRunner mode)")
    
    async def start(self):
        """启动动态MCP管理器"""
        logger.info("启动动态MCP管理器...")
        try:
            await self._restore_persistent_servers()
            logger.info("动态MCP管理器启动完成")
        except Exception as e:
            logger.error(f"启动动态MCP管理器失败: {e}")
            raise

    async def stop(self):
        """停止动态MCP管理器"""
        logger.info("停止动态MCP管理器...")
        try:
            await self._save_persistent_servers()
            if hasattr(self.runner, 'cleanup_all'):
                await self.runner.cleanup_all()
            logger.info("动态MCP管理器已停止")
        except Exception as e:
            logger.error(f"停止动态MCP管理器时出错: {e}")
    
    async def _restore_persistent_servers(self):
        """恢复持久化的MCP服务器"""
        try:
            config_path = Path("config/mcp_servers.json")
            if not config_path.exists():
                logger.info("没有找到持久化的MCP服务器配置")
                return
            
            with open(config_path, 'r', encoding='utf-8') as f:
                servers_config = json.load(f)
            
            restored_count = 0
            for server_name, server_config in servers_config.items():
                try:
                    result = await self.runner.install_server(server_config)
                    if result.get("success"):
                        install_result = InstallationResult(
                            success=True,
                            server_id=result["server_id"],
                            endpoint=result["endpoint"],
                            container_id=None,
                            process_id=result.get("pid"),
                            port=result.get("port"),
                            error_message=None
                        )
                        self.installed_servers[result["server_id"]] = install_result
                        restored_count += 1
                        logger.info(f"MCP服务器 {server_name} 恢复成功")
                except Exception as e:
                    logger.error(f"恢复MCP服务器 {server_name} 时出错: {e}")
            
            logger.info(f"成功恢复 {restored_count} 个MCP服务器")
        except Exception as e:
            logger.error(f"恢复持久化MCP服务器失败: {e}")

    async def _save_persistent_servers(self):
        """保存持久化MCP服务器状态"""
        try:
            config_path = Path("config/mcp_servers.json")
            config_path.parent.mkdir(exist_ok=True)
            
            servers_config = {}
            if hasattr(self.runner, 'list_running_servers'):
                running_servers = self.runner.list_running_servers()
                for server_id, server_info in running_servers.items():
                    servers_config[server_info.get("name", server_id)] = {
                        "name": server_info.get("name"),
                        "repo_url": server_info.get("repo_url"),
                        "project_type": server_info.get("project_type"),
                        "entry_point": server_info.get("entry_point"),
                    }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(servers_config, f, indent=2, ensure_ascii=False)
            
            logger.info(f"MCP服务器配置已保存到 {config_path}")
        except Exception as e:
            logger.error(f"保存MCP服务器配置时出错: {e}")

    async def search_mcp_servers(self, query: str, capability_tags: List[str] = None) -> List[MCPServerCandidate]:
        """搜索MCP服务器"""
        logger.info(f"搜索MCP服务器: query='{query}', tags={capability_tags}")
        
        if capability_tags is None:
            capability_tags = []
        
        all_candidates = []
        
        try:
            # 搜索本地数据库
            local_candidates = await self._search_local_mcp_database(query, capability_tags)
            all_candidates.extend(local_candidates)
            
            # 搜索远程注册中心
            remote_candidates = await self._search_remote_registries(query, capability_tags)
            all_candidates.extend(remote_candidates)
            
            # 去重和评分
            unique_candidates = self._deduplicate_candidates(all_candidates)
            scored_candidates = await self._score_candidates(unique_candidates)
            
            # 按评分排序
            scored_candidates.sort(key=lambda x: (x.security_score + x.popularity_score), reverse=True)
            
            logger.info(f"找到 {len(scored_candidates)} 个MCP服务器候选者")
            return scored_candidates[:20]  # 返回前20个结果
            
        except Exception as e:
            logger.error(f"搜索MCP服务器时出错: {e}")
            return []

    async def _search_local_mcp_database(self, query: str, capability_tags: List[str]) -> List[MCPServerCandidate]:
        """搜索本地MCP数据库"""
        candidates = []
        
        try:
            mcp_json_path = await self._find_mcp_json_file()
            if not mcp_json_path:
                return candidates
            
            with open(mcp_json_path, 'r', encoding='utf-8') as f:
                mcp_data = json.load(f)
            
            query_lower = query.lower()
            
            for mcp_entry in mcp_data.get("servers", []):
                if not isinstance(mcp_entry, dict):
                    continue
                
                match_score = self._calculate_match_score(mcp_entry, query_lower, capability_tags)
                
                if match_score > 0.1:
                    name = mcp_entry.get("name", "Unknown")
                    description = mcp_entry.get("description", "")
                    github_url = mcp_entry.get("url", "")
                    capabilities = mcp_entry.get("capabilities", [])
                    
                    install_method = self._infer_install_method_from_url(github_url)
                    author = self._extract_author_from_url(github_url)
                    tags = self._generate_tags_from_entry(mcp_entry, capabilities)
                    
                    verified = self._is_verified_author(author)
                    security_score = self._calculate_security_score(mcp_entry, author)
                    
                    candidate = MCPServerCandidate(
                        name=name,
                        description=description,
                        github_url=github_url,
                        author=author,
                        tags=tags,
                        install_method=install_method,
                        capabilities=capabilities,
                        verified=verified,
                        security_score=security_score,
                        popularity_score=match_score
                    )
                    
                    candidates.append(candidate)
            
            logger.info(f"本地数据库搜索找到 {len(candidates)} 个候选者")
            
        except Exception as e:
            logger.error(f"搜索本地MCP数据库时出错: {e}")
        
        return candidates

    async def _find_mcp_json_file(self) -> Optional[str]:
        """查找MCP JSON文件"""
        possible_paths = [
            "mcp_tools.json",
            "config/mcp_tools.json",
            "data/mcp_tools.json",
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                logger.info(f"找到MCP数据库文件: {path}")
                return path
        
        return None

    def _calculate_match_score(self, mcp_entry: Dict, query_lower: str, capability_tags: List[str]) -> float:
        """计算匹配分数"""
        score = 0.0
        
        name = mcp_entry.get("name", "").lower()
        if query_lower in name:
            score += 1.0
        
        description = mcp_entry.get("description", "").lower()
        if query_lower in description:
            score += 0.5
        
        capabilities = [cap.lower() for cap in mcp_entry.get("capabilities", [])]
        for tag in capability_tags:
            if tag.lower() in capabilities:
                score += 0.8
        
        return score

    def _infer_install_method_from_url(self, url: str) -> str:
        """从URL推断安装方法"""
        url_lower = url.lower()
        
        if "python" in url_lower or "py" in url_lower:
            return "python"
        elif "node" in url_lower or "npm" in url_lower or "js" in url_lower:
            return "nodejs"
        else:
            return "python"  # 默认为Python

    def _extract_author_from_url(self, url: str) -> str:
        """从URL提取作者"""
        try:
            parsed = urlparse(url)
            if parsed.hostname == "github.com":
                path_parts = parsed.path.strip("/").split("/")
                if len(path_parts) >= 1:
                    return path_parts[0]
        except Exception:
            pass
        return "unknown"

    def _generate_tags_from_entry(self, mcp_entry: Dict, capabilities: List[str]) -> List[str]:
        """从条目生成标签"""
        tags = set()
        
        explicit_tags = mcp_entry.get("tags", [])
        if isinstance(explicit_tags, list):
            tags.update(explicit_tags)
        
        for capability in capabilities:
            if isinstance(capability, str):
                tags.add(capability.lower())
        
        return list(tags)

    def _is_verified_author(self, author: str) -> bool:
        """检查是否为可信作者"""
        return author.lower() in [a.lower() for a in self.security_rules["trusted_authors"]]

    def _calculate_security_score(self, mcp_entry: Dict, author: str) -> float:
        """计算安全分数"""
        score = 0.0
        
        if self._is_verified_author(author):
            score += 0.5
        
        if mcp_entry.get("description"):
            score += 0.1
        
        if mcp_entry.get("capabilities"):
            score += 0.2
        
        return min(score, 1.0)

    async def _search_remote_registries(self, query: str, capability_tags: List[str]) -> List[MCPServerCandidate]:
        """搜索远程注册中心"""
        all_candidates = []
        
        for registry_name, registry_url in self.registries.items():
            try:
                candidates = await self._search_registry(registry_name, registry_url, query, capability_tags)
                all_candidates.extend(candidates)
                logger.info(f"从 {registry_name} 找到 {len(candidates)} 个候选者")
            except Exception as e:
                logger.error(f"搜索注册中心 {registry_name} 时出错: {e}")
        
        return all_candidates

    async def _search_registry(self, registry_name: str, registry_url: str, query: str, capability_tags: List[str]) -> List[MCPServerCandidate]:
        """搜索单个注册中心"""
        candidates = []
        
        try:
            async with aiohttp.ClientSession() as session:
                if registry_name == "github_search":
                    candidates = await self._search_github_repositories(session, registry_url, query, capability_tags)
                elif registry_name == "github_public":
                    candidates = await self._search_github_public(session, registry_url, query, capability_tags)
                
        except Exception as e:
            logger.error(f"搜索注册中心 {registry_name} 时出错: {e}")
        
        return candidates

    async def _search_github_repositories(self, session: aiohttp.ClientSession, url: str, query: str, capability_tags: List[str]) -> List[MCPServerCandidate]:
        """搜索GitHub仓库"""
        candidates = []
        
        try:
            search_query = f"{query} mcp server"
            params = {
                "q": search_query,
                "sort": "stars",
                "order": "desc",
                "per_page": 20
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    for repo in data.get("items", []):
                        try:
                            candidate = MCPServerCandidate(
                                name=repo["name"],
                                description=repo.get("description", ""),
                                github_url=repo["html_url"],
                                author=repo["owner"]["login"],
                                tags=repo.get("topics", []),
                                install_method=self._infer_install_method_from_url(repo["html_url"]),
                                capabilities=[],
                                verified=self._is_verified_author(repo["owner"]["login"]),
                                security_score=self._calculate_security_score(repo, repo["owner"]["login"]),
                                popularity_score=min(repo.get("stargazers_count", 0) / 100.0, 1.0)
                            )
                            candidates.append(candidate)
                            
                        except Exception as e:
                            logger.error(f"处理GitHub仓库时出错: {e}")
                            continue
                
        except Exception as e:
            logger.error(f"搜索GitHub仓库时出错: {e}")
        
        return candidates

    async def _search_github_public(self, session: aiohttp.ClientSession, base_url: str, query: str, capability_tags: List[str]) -> List[MCPServerCandidate]:
        """搜索GitHub公共MCP服务器"""
        candidates = []
        
        try:
            async with session.get(base_url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    for item in data:
                        if item.get("type") == "dir":
                            try:
                                candidate = MCPServerCandidate(
                                    name=item["name"],
                                    description=f"Official MCP Server: {item['name']}",
                                    github_url=f"https://github.com/modelcontextprotocol/servers/tree/main/src/{item['name']}",
                                    author="modelcontextprotocol",
                                    tags=["official", "mcp"],
                                    install_method="python",
                                    capabilities=[],
                                    verified=True,
                                    security_score=1.0,
                                    popularity_score=0.8
                                )
                                candidates.append(candidate)
                                
                            except Exception as e:
                                logger.error(f"处理官方MCP服务器时出错: {e}")
                                continue
                
        except Exception as e:
            logger.error(f"搜索GitHub公共MCP服务器时出错: {e}")
        
        return candidates

    def _deduplicate_candidates(self, candidates: List[MCPServerCandidate]) -> List[MCPServerCandidate]:
        """去重候选者"""
        seen_urls = set()
        unique_candidates = []
        
        for candidate in candidates:
            if candidate.github_url not in seen_urls:
                seen_urls.add(candidate.github_url)
                unique_candidates.append(candidate)
        
        return unique_candidates

    async def _score_candidates(self, candidates: List[MCPServerCandidate]) -> List[MCPServerCandidate]:
        """为候选者评分"""
        for candidate in candidates:
            if not candidate.popularity_score:
                candidate.popularity_score = await self._get_popularity_score(candidate.github_url)
        
        return candidates

    async def _get_popularity_score(self, github_url: str) -> float:
        """获取GitHub仓库的流行度分数"""
        try:
            parsed = urlparse(github_url)
            if parsed.hostname != "github.com":
                return 0.0
            
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) < 2:
                return 0.0
            
            owner, repo = path_parts[0], path_parts[1]
            api_url = f"https://api.github.com/repos/{owner}/{repo}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        stars = data.get("stargazers_count", 0)
                        forks = data.get("forks_count", 0)
                        score = min((stars * 0.7 + forks * 0.3) / 100.0, 1.0)
                        return score
        
        except Exception as e:
            logger.error(f"获取流行度分数时出错: {e}")
        
        return 0.0

    async def install_mcp_server(self, candidate: MCPServerCandidate) -> InstallationResult:
        """安装MCP服务器"""
        logger.info(f"安装MCP服务器: {candidate.name}")
        
        try:
            if not await self._security_check(candidate):
                return InstallationResult(
                    success=False,
                    server_id=None,
                    endpoint=None,
                    container_id=None,
                    process_id=None,
                    port=None,
                    error_message="安全检查失败"
                )
            
            install_config = {
                "name": candidate.name,
                "repo_url": candidate.github_url,
                "project_type": candidate.install_method,
                "author": candidate.author,
                "description": candidate.description
            }
            
            result = await self.runner.install_server(install_config)
            
            if result.get("success"):
                install_result = InstallationResult(
                    success=True,
                    server_id=result["server_id"],
                    endpoint=result["endpoint"],
                    container_id=None,
                    process_id=result.get("pid"),
                    port=result.get("port"),
                    error_message=None
                )
                
                self.installed_servers[result["server_id"]] = install_result
                await self._save_persistent_servers()
                
                logger.info(f"MCP服务器 {candidate.name} 安装成功")
                return install_result
            else:
                return InstallationResult(
                    success=False,
                    server_id=None,
                    endpoint=None,
                    container_id=None,
                    process_id=None,
                    port=None,
                    error_message=result.get("error_msg", "安装失败")
                )
                
        except Exception as e:
            logger.error(f"安装MCP服务器 {candidate.name} 时出错: {e}")
            return InstallationResult(
                success=False,
                server_id=None,
                endpoint=None,
                container_id=None,
                process_id=None,
                port=None,
                error_message=str(e)
            )

    async def _security_check(self, candidate: MCPServerCandidate) -> bool:
        """安全检查"""
        try:
            if candidate.verified:
                return True
            
            if candidate.security_score >= 0.5:
                return True
            
            if candidate.popularity_score >= 0.3:
                return True
            
            logger.warning(f"MCP服务器 {candidate.name} 未通过安全检查")
            return False
            
        except Exception as e:
            logger.error(f"安全检查时出错: {e}")
            return False

    async def uninstall_server(self, server_id: str) -> bool:
        """卸载服务器"""
        logger.info(f"卸载MCP服务器: {server_id}")
        
        try:
            if server_id in self.installed_servers:
                del self.installed_servers[server_id]
            
            success = await self.runner.stop_server(server_id)
            
            if success:
                await self._save_persistent_servers()
                logger.info(f"MCP服务器 {server_id} 卸载成功")
            
            return True
            
        except Exception as e:
            logger.error(f"卸载MCP服务器 {server_id} 时出错: {e}")
            return False

    async def get_installed_servers(self) -> Dict[str, InstallationResult]:
        """获取已安装的服务器"""
        return self.installed_servers.copy()

    async def health_check_installed_servers(self) -> Dict[str, bool]:
        """健康检查已安装的服务器"""
        health_status = {}
        
        for server_id, install_result in self.installed_servers.items():
            try:
                if install_result.endpoint:
                    is_healthy = await self.runner.health_check(install_result.endpoint)
                    health_status[server_id] = is_healthy
                else:
                    health_status[server_id] = False
            except Exception as e:
                logger.error(f"健康检查服务器 {server_id} 时出错: {e}")
                health_status[server_id] = False
        
        return health_status

    async def cleanup(self):
        """清理资源"""
        logger.info("清理动态MCP管理器资源...")
        
        try:
            server_ids = list(self.installed_servers.keys())
            for server_id in server_ids:
                await self.uninstall_server(server_id)
            
            if hasattr(self.runner, 'cleanup_all'):
                await self.runner.cleanup_all()
            
            logger.info("动态MCP管理器资源清理完成")
            
        except Exception as e:
            logger.error(f"清理资源时出错: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        running_servers = getattr(self.runner, 'list_running_servers', lambda: {})()
        
        return {
            "installed_servers": len(self.installed_servers),
            "running_servers": len(running_servers),
            "cached_registries": len(self.registry_cache),
            "runner_type": type(self.runner).__name__
        } 