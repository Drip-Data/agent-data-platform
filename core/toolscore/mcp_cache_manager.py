"""
MCP统一缓存管理器
优化GitHub API、搜索结果、安全验证等的缓存机制
"""

import asyncio
import json
import logging
import hashlib
import time
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
import redis.asyncio as redis

logger = logging.getLogger(__name__)

@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    created_at: float
    ttl: int
    access_count: int = 0
    last_accessed: float = 0

class MCPCacheManager:
    """MCP统一缓存管理器 - 优化所有相关缓存操作"""
    
    def __init__(self, redis_url: str = "redis://redis:6379"):
        self.redis_url = redis_url
        self.redis_client = None
        
        # 内存缓存 (L1缓存)
        self.memory_cache: Dict[str, CacheEntry] = {}
        self.max_memory_items = 1000
        
        # 缓存配置
        self.cache_config = {
            # GitHub API结果缓存
            "github_api": {
                "ttl": 3600,  # 1小时
                "prefix": "mcp:github:api:",
                "use_memory": True
            },
            # MCP搜索结果缓存
            "mcp_search": {
                "ttl": 1800,  # 30分钟
                "prefix": "mcp:search:",
                "use_memory": True
            },
            # 工具缺口分析缓存
            "gap_analysis": {
                "ttl": 600,   # 10分钟
                "prefix": "mcp:gap:",
                "use_memory": True
            },
            # 安全验证结果缓存
            "security_check": {
                "ttl": 86400,  # 24小时
                "prefix": "mcp:security:",
                "use_memory": False  # 仅Redis存储
            },
            # 仓库元数据缓存
            "repo_metadata": {
                "ttl": 7200,  # 2小时
                "prefix": "mcp:repo:",
                "use_memory": True
            }
        }
        
        logger.info("MCP缓存管理器初始化完成")
    
    async def initialize(self):
        """初始化缓存管理器"""
        try:
            # 连接Redis
            self.redis_client = redis.Redis.from_url(self.redis_url)
            await self.redis_client.ping()
            logger.info("Redis缓存连接成功")
            
            # 启动缓存清理任务
            asyncio.create_task(self._cache_cleanup_loop())
            
        except Exception as e:
            logger.error(f"初始化缓存管理器失败: {e}")
            raise
    
    def _generate_cache_key(self, cache_type: str, identifier: str) -> str:
        """生成缓存键"""
        if cache_type not in self.cache_config:
            raise ValueError(f"未知的缓存类型: {cache_type}")
        
        prefix = self.cache_config[cache_type]["prefix"]
        # 使用SHA256生成稳定的键
        key_hash = hashlib.sha256(identifier.encode()).hexdigest()
        return f"{prefix}{key_hash}"
    
    async def get(self, cache_type: str, identifier: str) -> Optional[Any]:
        """获取缓存项"""
        cache_key = self._generate_cache_key(cache_type, identifier)
        config = self.cache_config[cache_type]
        
        # 先尝试内存缓存
        if config["use_memory"] and cache_key in self.memory_cache:
            entry = self.memory_cache[cache_key]
            
            # 检查是否过期
            if time.time() - entry.created_at < entry.ttl:
                entry.access_count += 1
                entry.last_accessed = time.time()
                logger.debug(f"内存缓存命中: {cache_type}")
                return entry.value
            else:
                # 过期，删除
                del self.memory_cache[cache_key]
        
        # 尝试Redis缓存
        if self.redis_client:
            try:
                cached_data = await self.redis_client.get(cache_key)
                if cached_data:
                    value = json.loads(cached_data)
                    
                    # 如果支持内存缓存，添加到内存
                    if config["use_memory"]:
                        await self._add_to_memory_cache(cache_key, value, config["ttl"])
                    
                    logger.debug(f"Redis缓存命中: {cache_type}")
                    return value
                    
            except Exception as e:
                logger.error(f"从Redis获取缓存失败: {e}")
        
        return None
    
    async def set(self, cache_type: str, identifier: str, value: Any, custom_ttl: Optional[int] = None) -> bool:
        """设置缓存项"""
        cache_key = self._generate_cache_key(cache_type, identifier)
        config = self.cache_config[cache_type]
        ttl = custom_ttl or config["ttl"]
        
        try:
            # 序列化值
            serialized_value = json.dumps(value, ensure_ascii=False)
            
            # 存储到Redis
            if self.redis_client:
                await self.redis_client.setex(cache_key, ttl, serialized_value)
            
            # 存储到内存缓存
            if config["use_memory"]:
                await self._add_to_memory_cache(cache_key, value, ttl)
            
            logger.debug(f"缓存设置成功: {cache_type}")
            return True
            
        except Exception as e:
            logger.error(f"设置缓存失败: {cache_type} - {e}")
            return False
    
    async def _add_to_memory_cache(self, cache_key: str, value: Any, ttl: int):
        """添加到内存缓存"""
        # 检查内存缓存大小限制
        if len(self.memory_cache) >= self.max_memory_items:
            await self._evict_least_used_memory_cache()
        
        entry = CacheEntry(
            key=cache_key,
            value=value,
            created_at=time.time(),
            ttl=ttl,
            access_count=1,
            last_accessed=time.time()
        )
        
        self.memory_cache[cache_key] = entry
    
    async def _evict_least_used_memory_cache(self):
        """驱逐最少使用的内存缓存项"""
        if not self.memory_cache:
            return
        
        # 找到最少使用的项
        least_used_key = min(
            self.memory_cache.keys(),
            key=lambda k: (self.memory_cache[k].access_count, self.memory_cache[k].last_accessed)
        )
        
        del self.memory_cache[least_used_key]
        logger.debug(f"驱逐内存缓存项: {least_used_key}")
    
    async def delete(self, cache_type: str, identifier: str) -> bool:
        """删除缓存项"""
        cache_key = self._generate_cache_key(cache_type, identifier)
        
        try:
            # 从内存缓存删除
            if cache_key in self.memory_cache:
                del self.memory_cache[cache_key]
            
            # 从Redis删除
            if self.redis_client:
                await self.redis_client.delete(cache_key)
            
            logger.debug(f"缓存删除成功: {cache_type}")
            return True
            
        except Exception as e:
            logger.error(f"删除缓存失败: {cache_type} - {e}")
            return False
    
    async def cache_github_api_result(self, api_url: str, result: Dict[str, Any]) -> bool:
        """缓存GitHub API结果"""
        return await self.set("github_api", api_url, result)
    
    async def get_github_api_result(self, api_url: str) -> Optional[Dict[str, Any]]:
        """获取GitHub API缓存结果"""
        return await self.get("github_api", api_url)
    
    async def cache_mcp_search_result(self, query: str, capabilities: List[str], result: List[Dict[str, Any]]) -> bool:
        """缓存MCP搜索结果"""
        search_identifier = f"{query}:{':'.join(sorted(capabilities))}"
        return await self.set("mcp_search", search_identifier, result)
    
    async def get_mcp_search_result(self, query: str, capabilities: List[str]) -> Optional[List[Dict[str, Any]]]:
        """获取MCP搜索缓存结果"""
        search_identifier = f"{query}:{':'.join(sorted(capabilities))}"
        return await self.get("mcp_search", search_identifier)
    
    async def cache_gap_analysis(self, task_description: str, available_tools: List[Dict], analysis: Dict[str, Any]) -> bool:
        """缓存工具缺口分析结果"""
        # 生成任务和工具的指纹
        tools_fingerprint = hashlib.md5(json.dumps(available_tools, sort_keys=True).encode()).hexdigest()
        analysis_identifier = f"{task_description}:{tools_fingerprint}"
        return await self.set("gap_analysis", analysis_identifier, analysis)
    
    async def get_gap_analysis(self, task_description: str, available_tools: List[Dict]) -> Optional[Dict[str, Any]]:
        """获取工具缺口分析缓存结果"""
        tools_fingerprint = hashlib.md5(json.dumps(available_tools, sort_keys=True).encode()).hexdigest()
        analysis_identifier = f"{task_description}:{tools_fingerprint}"
        return await self.get("gap_analysis", analysis_identifier)
    
    async def cache_security_check(self, repo_url: str, security_result: Dict[str, Any]) -> bool:
        """缓存安全验证结果"""
        return await self.set("security_check", repo_url, security_result)
    
    async def get_security_check(self, repo_url: str) -> Optional[Dict[str, Any]]:
        """获取安全验证缓存结果"""
        return await self.get("security_check", repo_url)
    
    async def cache_repo_metadata(self, repo_url: str, metadata: Dict[str, Any]) -> bool:
        """缓存仓库元数据"""
        return await self.set("repo_metadata", repo_url, metadata)
    
    async def get_repo_metadata(self, repo_url: str) -> Optional[Dict[str, Any]]:
        """获取仓库元数据缓存"""
        return await self.get("repo_metadata", repo_url)
    
    async def invalidate_pattern(self, cache_type: str, pattern: str) -> int:
        """根据模式批量失效缓存"""
        if cache_type not in self.cache_config:
            return 0
        
        invalidated_count = 0
        
        try:
            prefix = self.cache_config[cache_type]["prefix"]
            search_pattern = f"{prefix}*"
            
            # 从Redis批量删除
            if self.redis_client:
                keys = await self.redis_client.keys(search_pattern)
                if keys:
                    await self.redis_client.delete(*keys)
                    invalidated_count += len(keys)
            
            # 从内存缓存删除匹配的项
            memory_keys_to_delete = [
                key for key in self.memory_cache.keys()
                if key.startswith(prefix) and pattern in key
            ]
            
            for key in memory_keys_to_delete:
                del self.memory_cache[key]
                invalidated_count += 1
            
            logger.info(f"批量失效缓存: {cache_type}, 模式: {pattern}, 数量: {invalidated_count}")
            return invalidated_count
            
        except Exception as e:
            logger.error(f"批量失效缓存失败: {e}")
            return 0
    
    async def clear_expired_cache(self, cache_type: Optional[str] = None) -> int:
        """清理过期缓存"""
        cleared_count = 0
        current_time = time.time()
        
        # 清理内存缓存中的过期项
        expired_keys = []
        for key, entry in self.memory_cache.items():
            if current_time - entry.created_at >= entry.ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.memory_cache[key]
            cleared_count += 1
        
        logger.info(f"清理过期内存缓存: {cleared_count} 项")
        return cleared_count
    
    async def _cache_cleanup_loop(self):
        """缓存清理循环任务"""
        while True:
            try:
                await asyncio.sleep(300)  # 每5分钟清理一次
                await self.clear_expired_cache()
            except Exception as e:
                logger.error(f"缓存清理任务失败: {e}")
                await asyncio.sleep(60)  # 出错时等待1分钟再重试
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        stats = {
            "memory_cache": {
                "total_items": len(self.memory_cache),
                "max_items": self.max_memory_items,
                "items_by_type": {}
            },
            "redis_connected": self.redis_client is not None,
            "cache_types": {}
        }
        
        # 统计内存缓存中各类型的数量
        for key, entry in self.memory_cache.items():
            for cache_type, config in self.cache_config.items():
                if key.startswith(config["prefix"]):
                    if cache_type not in stats["memory_cache"]["items_by_type"]:
                        stats["memory_cache"]["items_by_type"][cache_type] = 0
                    stats["memory_cache"]["items_by_type"][cache_type] += 1
                    break
        
        # 添加缓存配置信息
        for cache_type, config in self.cache_config.items():
            stats["cache_types"][cache_type] = {
                "ttl": config["ttl"],
                "use_memory": config["use_memory"]
            }
        
        # 获取Redis统计信息
        if self.redis_client:
            try:
                redis_info = await self.redis_client.info()
                stats["redis_info"] = {
                    "used_memory": redis_info.get("used_memory_human", "unknown"),
                    "connected_clients": redis_info.get("connected_clients", 0),
                    "total_commands_processed": redis_info.get("total_commands_processed", 0)
                }
            except Exception as e:
                stats["redis_info"] = {"error": str(e)}
        
        return stats
    
    async def warm_up_cache(self, cache_operations: List[Tuple[str, str, Any]]):
        """预热缓存"""
        logger.info(f"开始预热缓存，操作数量: {len(cache_operations)}")
        
        successful_operations = 0
        for cache_type, identifier, value in cache_operations:
            try:
                success = await self.set(cache_type, identifier, value)
                if success:
                    successful_operations += 1
            except Exception as e:
                logger.error(f"预热缓存失败: {cache_type}:{identifier} - {e}")
        
        logger.info(f"缓存预热完成: {successful_operations}/{len(cache_operations)} 成功")
    
    async def cleanup(self):
        """清理资源"""
        try:
            # 清空内存缓存
            self.memory_cache.clear()
            
            # 关闭Redis连接
            if self.redis_client:
                await self.redis_client.close()
            
            logger.info("MCP缓存管理器清理完成")
            
        except Exception as e:
            logger.error(f"清理缓存管理器失败: {e}")
    
    async def cache_analysis_result(self, cache_key: str, analysis_result) -> bool:
        """缓存工具缺口分析结果"""
        try:
            # 将分析结果转换为可序列化的字典格式
            if hasattr(analysis_result, '__dict__'):
                # 如果是dataclass或对象，转换为字典
                analysis_data = {
                    'has_sufficient_tools': analysis_result.has_sufficient_tools,
                    'overall_assessment': analysis_result.overall_assessment,
                    'recommended_action': analysis_result.recommended_action,
                    'tool_requirements': []
                }
                
                # 转换工具需求列表
                for req in analysis_result.tool_requirements:
                    req_data = {
                        'needed': req.needed,
                        'description': req.description,
                        'suggested_search_keywords': req.suggested_search_keywords,
                        'confidence_score': req.confidence_score,
                        'reasoning': req.reasoning
                    }
                    analysis_data['tool_requirements'].append(req_data)
            else:
                # 如果已经是字典格式
                analysis_data = analysis_result
            
            # 使用gap_analysis缓存类型
            return await self.set("gap_analysis", cache_key, analysis_data)
            
        except Exception as e:
            logger.error(f"缓存分析结果失败: {e}")
            return False
    
    async def get_analysis_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """获取缓存的工具缺口分析结果"""
        try:
            return await self.get("gap_analysis", cache_key)
        except Exception as e:
            logger.error(f"获取缓存的分析结果失败: {e}")
            return None 