"""
WebSocket管理器 - 简化版本
"""

import asyncio
import logging
from typing import Set
import websockets

logger = logging.getLogger(__name__)

class WebSocketManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        self.connections: Set = set()
        self.is_running = False
        
    async def start(self):
        """启动WebSocket管理器"""
        self.is_running = True
        logger.info("WebSocket管理器启动完成")
        
    async def stop(self):
        """停止WebSocket管理器"""
        self.is_running = False
        # 关闭所有连接
        for connection in self.connections.copy():
            try:
                await connection.close()
            except Exception as e:
                logger.error(f"关闭WebSocket连接失败: {e}")
        self.connections.clear()
        logger.info("WebSocket管理器已停止")
        
    async def add_connection(self, websocket):
        """添加WebSocket连接"""
        self.connections.add(websocket)
        logger.info(f"新增WebSocket连接，当前连接数: {len(self.connections)}")
        
    async def remove_connection(self, websocket):
        """移除WebSocket连接"""
        self.connections.discard(websocket)
        logger.info(f"移除WebSocket连接，当前连接数: {len(self.connections)}")
        
    async def broadcast(self, message: dict):
        """广播消息到所有连接"""
        if not self.connections:
            return
            
        disconnected = set()
        for connection in self.connections:
            try:
                await connection.send(str(message))
            except Exception as e:
                logger.error(f"发送WebSocket消息失败: {e}")
                disconnected.add(connection)
        
        # 清理断开的连接
        for connection in disconnected:
            self.connections.discard(connection) 