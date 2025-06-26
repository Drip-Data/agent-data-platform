"""
MCP会话管理器
提供会话级别的管理和协调功能
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .session_handler import MCPSessionHandler
from ..exceptions import SessionError


@dataclass
class SessionInfo:
    """会话信息"""
    session_id: str
    server_id: str
    handler: MCPSessionHandler
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    status: str = "active"
    metadata: Dict[str, Any] = field(default_factory=dict)


class MCPSessionManager:
    """MCP会话管理器"""
    
    def __init__(self, session_timeout: float = 3600.0):
        self.sessions: Dict[str, SessionInfo] = {}
        self.session_timeout = session_timeout
        self.logger = logging.getLogger(__name__)
        self._cleanup_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """启动会话管理器"""
        self.logger.info("启动MCP会话管理器")
        self._cleanup_task = asyncio.create_task(self._cleanup_sessions())
        
    async def stop(self):
        """停止会话管理器"""
        self.logger.info("停止MCP会话管理器")
        
        # 取消清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
                
        # 关闭所有会话
        await self.close_all_sessions()
        
    async def create_session(self, server_id: str, connection_config: Dict[str, Any]) -> str:
        """创建新会话"""
        session_id = f"session_{server_id}_{datetime.now().timestamp()}"
        
        try:
            handler = MCPSessionHandler()
            await handler.connect(
                connection_config.get("uri", f"ws://localhost:8080"),
                connection_config.get("transport", "websocket")
            )
            
            await handler.initialize()
            
            session_info = SessionInfo(
                session_id=session_id,
                server_id=server_id,
                handler=handler,
                metadata=connection_config
            )
            
            self.sessions[session_id] = session_info
            self.logger.info(f"创建会话: {session_id} for server: {server_id}")
            
            return session_id
            
        except Exception as e:
            self.logger.error(f"创建会话失败: {e}")
            raise SessionError(f"会话创建失败: {e}", session_id=session_id)
            
    async def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """获取会话信息"""
        session_info = self.sessions.get(session_id)
        if session_info:
            session_info.last_activity = datetime.now()
        return session_info
        
    async def close_session(self, session_id: str):
        """关闭指定会话"""
        session_info = self.sessions.get(session_id)
        if session_info:
            try:
                await session_info.handler.disconnect()
                session_info.status = "closed"
                self.logger.info(f"关闭会话: {session_id}")
            except Exception as e:
                self.logger.error(f"关闭会话失败: {e}")
            finally:
                self.sessions.pop(session_id, None)
                
    async def close_all_sessions(self):
        """关闭所有会话"""
        session_ids = list(self.sessions.keys())
        for session_id in session_ids:
            await self.close_session(session_id)
            
    async def list_sessions(self) -> List[SessionInfo]:
        """列出所有活跃会话"""
        return [info for info in self.sessions.values() if info.status == "active"]
        
    async def get_sessions_by_server(self, server_id: str) -> List[SessionInfo]:
        """获取指定服务器的所有会话"""
        return [
            info for info in self.sessions.values() 
            if info.server_id == server_id and info.status == "active"
        ]
        
    async def _cleanup_sessions(self):
        """定期清理超时会话"""
        while True:
            try:
                await asyncio.sleep(300)  # 每5分钟检查一次
                now = datetime.now()
                timeout_threshold = now - timedelta(seconds=self.session_timeout)
                
                expired_sessions = [
                    session_id for session_id, info in self.sessions.items()
                    if info.last_activity < timeout_threshold
                ]
                
                for session_id in expired_sessions:
                    self.logger.info(f"清理超时会话: {session_id}")
                    await self.close_session(session_id)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"会话清理错误: {e}")
                
    def get_session_stats(self) -> Dict[str, Any]:
        """获取会话统计信息"""
        active_sessions = [info for info in self.sessions.values() if info.status == "active"]
        server_counts = {}
        
        for session in active_sessions:
            server_counts[session.server_id] = server_counts.get(session.server_id, 0) + 1
            
        return {
            "total_sessions": len(self.sessions),
            "active_sessions": len(active_sessions),
            "sessions_by_server": server_counts,
            "average_session_age": self._calculate_average_session_age()
        }
        
    def _calculate_average_session_age(self) -> float:
        """计算平均会话年龄（秒）"""
        if not self.sessions:
            return 0.0
            
        now = datetime.now()
        total_age = sum(
            (now - info.created_at).total_seconds() 
            for info in self.sessions.values()
        )
        
        return total_age / len(self.sessions)