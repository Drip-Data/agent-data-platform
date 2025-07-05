"""
内存暂存工具 - 解决信息孤岛问题
允许Agent在步骤间保存和检索数据，确保工具输出有效传递给后续操作
"""

import json
import logging
import time
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class StagingData:
    """暂存数据结构"""
    key: str
    value: Any
    data_type: str
    timestamp: float
    source_step: Optional[str] = None
    source_tool: Optional[str] = None
    tags: List[str] = None
    expires_at: Optional[float] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class MemoryStagingTool:
    """
    内存暂存工具 - 核心功能：
    1. memory.write(key, value) - 保存数据到暂存区
    2. memory.read(key) - 从暂存区读取数据
    3. memory.list() - 列出所有可用的暂存数据
    4. memory.clear(key) - 清除特定数据
    5. memory.search(query) - 搜索相关数据
    """
    
    def __init__(self, max_entries: int = 1000, default_ttl_hours: int = 24):
        self.storage: Dict[str, StagingData] = {}
        self.max_entries = max_entries
        self.default_ttl_hours = default_ttl_hours
        self.current_step = None
        self.current_tool = None
        logger.info("✅ MemoryStagingTool 初始化完成")
    
    def set_context(self, step: str = None, tool: str = None):
        """设置当前步骤和工具上下文"""
        self.current_step = step
        self.current_tool = tool
    
    def write(self, key: str, value: Any, data_type: str = None, 
              tags: List[str] = None, ttl_hours: int = None) -> Dict[str, Any]:
        """
        保存数据到暂存区
        
        Args:
            key: 数据键名
            value: 数据值
            data_type: 数据类型描述
            tags: 标签列表，用于分类和搜索
            ttl_hours: 过期时间（小时），默认24小时
        
        Returns:
            操作结果
        """
        try:
            # 清理过期数据
            self._cleanup_expired()
            
            # 检查存储限制
            if len(self.storage) >= self.max_entries:
                self._cleanup_oldest()
            
            # 推断数据类型
            if data_type is None:
                data_type = self._infer_data_type(value)
            
            # 设置过期时间
            ttl = ttl_hours or self.default_ttl_hours
            expires_at = time.time() + (ttl * 3600)
            
            # 创建暂存数据
            staging_data = StagingData(
                key=key,
                value=value,
                data_type=data_type,
                timestamp=time.time(),
                source_step=self.current_step,
                source_tool=self.current_tool,
                tags=tags or [],
                expires_at=expires_at
            )
            
            # 保存到存储
            self.storage[key] = staging_data
            
            logger.info(f"🔄 已保存暂存数据: {key} (类型: {data_type})")
            
            return {
                "success": True,
                "key": key,
                "data_type": data_type,
                "timestamp": staging_data.timestamp,
                "expires_at": expires_at,
                "message": f"数据已保存到暂存区，键名: {key}"
            }
            
        except Exception as e:
            logger.error(f"❌ 保存暂存数据失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"保存数据失败: {str(e)}"
            }
    
    def read(self, key: str) -> Dict[str, Any]:
        """
        从暂存区读取数据
        
        Args:
            key: 数据键名
        
        Returns:
            数据和元信息
        """
        try:
            # 清理过期数据
            self._cleanup_expired()
            
            if key not in self.storage:
                return {
                    "success": False,
                    "error": "key_not_found",
                    "message": f"暂存区中未找到键名: {key}",
                    "available_keys": list(self.storage.keys())
                }
            
            staging_data = self.storage[key]
            
            # 检查是否过期
            if staging_data.expires_at and time.time() > staging_data.expires_at:
                del self.storage[key]
                return {
                    "success": False,
                    "error": "data_expired",
                    "message": f"数据已过期: {key}"
                }
            
            logger.info(f"📖 已读取暂存数据: {key}")
            
            return {
                "success": True,
                "key": key,
                "value": staging_data.value,
                "data_type": staging_data.data_type,
                "timestamp": staging_data.timestamp,
                "source_step": staging_data.source_step,
                "source_tool": staging_data.source_tool,
                "tags": staging_data.tags,
                "age_seconds": time.time() - staging_data.timestamp
            }
            
        except Exception as e:
            logger.error(f"❌ 读取暂存数据失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"读取数据失败: {str(e)}"
            }
    
    def list_all(self, include_values: bool = False) -> Dict[str, Any]:
        """
        列出所有暂存数据
        
        Args:
            include_values: 是否包含具体数值
        
        Returns:
            所有数据的列表
        """
        try:
            # 清理过期数据
            self._cleanup_expired()
            
            entries = []
            for key, staging_data in self.storage.items():
                entry = {
                    "key": key,
                    "data_type": staging_data.data_type,
                    "timestamp": staging_data.timestamp,
                    "age_seconds": time.time() - staging_data.timestamp,
                    "source_step": staging_data.source_step,
                    "source_tool": staging_data.source_tool,
                    "tags": staging_data.tags,
                    "expires_in_seconds": staging_data.expires_at - time.time() if staging_data.expires_at else None
                }
                
                if include_values:
                    entry["value"] = staging_data.value
                else:
                    # 提供值的预览
                    entry["value_preview"] = self._get_value_preview(staging_data.value)
                
                entries.append(entry)
            
            # 按时间戳排序（最新的在前）
            entries.sort(key=lambda x: x["timestamp"], reverse=True)
            
            return {
                "success": True,
                "total_count": len(entries),
                "entries": entries,
                "message": f"找到 {len(entries)} 个暂存数据项"
            }
            
        except Exception as e:
            logger.error(f"❌ 列出暂存数据失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"列出数据失败: {str(e)}"
            }
    
    def search(self, query: str, search_in_values: bool = True) -> Dict[str, Any]:
        """
        搜索暂存数据
        
        Args:
            query: 搜索查询
            search_in_values: 是否在值中搜索
        
        Returns:
            匹配的数据列表
        """
        try:
            # 清理过期数据
            self._cleanup_expired()
            
            query_lower = query.lower()
            matches = []
            
            for key, staging_data in self.storage.items():
                score = 0
                match_reasons = []
                
                # 在键名中搜索
                if query_lower in key.lower():
                    score += 3
                    match_reasons.append("key_match")
                
                # 在标签中搜索
                for tag in staging_data.tags:
                    if query_lower in tag.lower():
                        score += 2
                        match_reasons.append("tag_match")
                
                # 在数据类型中搜索
                if query_lower in staging_data.data_type.lower():
                    score += 1
                    match_reasons.append("type_match")
                
                # 在值中搜索
                if search_in_values:
                    value_str = str(staging_data.value).lower()
                    if query_lower in value_str:
                        score += 2
                        match_reasons.append("value_match")
                
                # 在来源信息中搜索
                if staging_data.source_step and query_lower in staging_data.source_step.lower():
                    score += 1
                    match_reasons.append("source_step_match")
                
                if staging_data.source_tool and query_lower in staging_data.source_tool.lower():
                    score += 1
                    match_reasons.append("source_tool_match")
                
                if score > 0:
                    matches.append({
                        "key": key,
                        "value": staging_data.value,
                        "data_type": staging_data.data_type,
                        "timestamp": staging_data.timestamp,
                        "age_seconds": time.time() - staging_data.timestamp,
                        "source_step": staging_data.source_step,
                        "source_tool": staging_data.source_tool,
                        "tags": staging_data.tags,
                        "score": score,
                        "match_reasons": match_reasons
                    })
            
            # 按分数排序（分数高的在前）
            matches.sort(key=lambda x: x["score"], reverse=True)
            
            return {
                "success": True,
                "query": query,
                "total_matches": len(matches),
                "matches": matches,
                "message": f"找到 {len(matches)} 个匹配项"
            }
            
        except Exception as e:
            logger.error(f"❌ 搜索暂存数据失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"搜索失败: {str(e)}"
            }
    
    def clear(self, key: str = None) -> Dict[str, Any]:
        """
        清除暂存数据
        
        Args:
            key: 要清除的键名，如果为None则清除所有数据
        
        Returns:
            操作结果
        """
        try:
            if key is None:
                # 清除所有数据
                count = len(self.storage)
                self.storage.clear()
                logger.info(f"🗑️ 已清空所有暂存数据 ({count} 项)")
                return {
                    "success": True,
                    "cleared_count": count,
                    "message": f"已清空所有暂存数据 ({count} 项)"
                }
            else:
                # 清除特定键
                if key in self.storage:
                    del self.storage[key]
                    logger.info(f"🗑️ 已清除暂存数据: {key}")
                    return {
                        "success": True,
                        "key": key,
                        "message": f"已清除暂存数据: {key}"
                    }
                else:
                    return {
                        "success": False,
                        "error": "key_not_found",
                        "message": f"暂存区中未找到键名: {key}",
                        "available_keys": list(self.storage.keys())
                    }
                    
        except Exception as e:
            logger.error(f"❌ 清除暂存数据失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"清除数据失败: {str(e)}"
            }
    
    def _infer_data_type(self, value: Any) -> str:
        """推断数据类型"""
        if isinstance(value, dict):
            return "dictionary"
        elif isinstance(value, list):
            return "list"
        elif isinstance(value, str):
            # 尝试识别特殊字符串类型
            if value.replace('.', '').replace('-', '').isdigit():
                return "numeric_string"
            elif '@' in value and '.' in value:
                return "email"
            elif value.startswith('http'):
                return "url"
            else:
                return "string"
        elif isinstance(value, (int, float)):
            return "number"
        elif isinstance(value, bool):
            return "boolean"
        else:
            return str(type(value).__name__)
    
    def _get_value_preview(self, value: Any, max_length: int = 100) -> str:
        """获取值的预览"""
        try:
            value_str = str(value)
            if len(value_str) <= max_length:
                return value_str
            else:
                return value_str[:max_length] + "..."
        except:
            return "<unprintable>"
    
    def _cleanup_expired(self):
        """清理过期数据"""
        current_time = time.time()
        expired_keys = []
        
        for key, staging_data in self.storage.items():
            if staging_data.expires_at and current_time > staging_data.expires_at:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.storage[key]
            logger.debug(f"🗑️ 清理过期数据: {key}")
    
    def _cleanup_oldest(self, keep_count: int = None):
        """清理最旧的数据"""
        if keep_count is None:
            keep_count = int(self.max_entries * 0.8)  # 保留80%
        
        if len(self.storage) <= keep_count:
            return
        
        # 按时间戳排序
        sorted_items = sorted(self.storage.items(), key=lambda x: x[1].timestamp)
        remove_count = len(self.storage) - keep_count
        
        for i in range(remove_count):
            key = sorted_items[i][0]
            del self.storage[key]
            logger.debug(f"🗑️ 清理旧数据: {key}")


# 创建全局实例，供工具集成使用
memory_staging = MemoryStagingTool()


def memory_write(key: str, value: Any, data_type: str = None, 
                tags: List[str] = None, ttl_hours: int = None) -> Dict[str, Any]:
    """内存写入工具函数"""
    return memory_staging.write(key, value, data_type, tags, ttl_hours)


def memory_read(key: str) -> Dict[str, Any]:
    """内存读取工具函数"""
    return memory_staging.read(key)


def memory_list(include_values: bool = False) -> Dict[str, Any]:
    """内存列表工具函数"""
    return memory_staging.list_all(include_values)


def memory_search(query: str, search_in_values: bool = True) -> Dict[str, Any]:
    """内存搜索工具函数"""
    return memory_staging.search(query, search_in_values)


def memory_clear(key: str = None) -> Dict[str, Any]:
    """内存清除工具函数"""
    return memory_staging.clear(key)


# 工具描述，用于LLM理解
MEMORY_TOOLS = {
    "memory_write": {
        "name": "memory_write",
        "description": "保存数据到内存暂存区，用于在步骤间传递信息。解决信息孤岛问题的关键工具。",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "数据键名，用于后续检索"
                },
                "value": {
                    "description": "要保存的数据值，可以是任何类型"
                },
                "data_type": {
                    "type": "string",
                    "description": "数据类型描述（可选）"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "标签列表，用于分类和搜索（可选）"
                },
                "ttl_hours": {
                    "type": "integer",
                    "description": "数据过期时间（小时），默认24小时（可选）"
                }
            },
            "required": ["key", "value"]
        }
    },
    "memory_read": {
        "name": "memory_read",
        "description": "从内存暂存区读取数据，获取之前保存的信息",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "要读取的数据键名"
                }
            },
            "required": ["key"]
        }
    },
    "memory_list": {
        "name": "memory_list",
        "description": "列出所有可用的暂存数据，查看当前保存了哪些信息",
        "parameters": {
            "type": "object",
            "properties": {
                "include_values": {
                    "type": "boolean",
                    "description": "是否包含具体数值，默认false只显示预览"
                }
            }
        }
    },
    "memory_search": {
        "name": "memory_search",
        "description": "搜索暂存区中的相关数据",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询词"
                },
                "search_in_values": {
                    "type": "boolean",
                    "description": "是否在数据值中搜索，默认true"
                }
            },
            "required": ["query"]
        }
    },
    "memory_clear": {
        "name": "memory_clear",
        "description": "清除暂存数据",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "要清除的键名，不提供则清除所有数据"
                }
            }
        }
    }
}