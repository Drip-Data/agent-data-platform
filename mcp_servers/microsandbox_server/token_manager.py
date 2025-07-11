#!/usr/bin/env python3
"""
MicroSandbox Token Manager
自动处理API Token的生成、刷新和过期检测
确保agent无痛使用MicroSandbox服务
"""

import asyncio
import logging
import time
import subprocess
import re
from typing import Optional, Dict, Any
from pathlib import Path
import json
from datetime import datetime, timedelta
import jwt
from dotenv import load_dotenv
import os

logger = logging.getLogger(__name__)

class MicroSandboxTokenManager:
    """MicroSandbox Token管理器 - 自动处理token生成和刷新"""
    
    def __init__(self, env_path: Optional[Path] = None):
        self.env_path = env_path or Path(__file__).parent / '.env'
        self.current_token = None
        self.token_expiry = None
        self.last_refresh_attempt = 0
        self.refresh_cooldown = 30  # 30秒冷却时间避免频繁刷新
        self.refresh_before_expiry = 300  # 提前5分钟刷新
        
        # 初始化时加载现有token
        self._load_current_token()
        
    def _load_current_token(self):
        """从环境文件加载当前token"""
        try:
            if self.env_path.exists():
                load_dotenv(self.env_path)
                self.current_token = os.getenv('MSB_API_KEY')
                if self.current_token:
                    self.token_expiry = self._get_token_expiry(self.current_token)
                    logger.info(f"Loaded existing token, expires: {self.token_expiry}")
        except Exception as e:
            logger.warning(f"Failed to load existing token: {e}")
            
    def _get_token_expiry(self, token: str) -> Optional[datetime]:
        """从JWT token解析过期时间"""
        try:
            if token and token.startswith('msb_'):
                # 去掉msb_前缀
                jwt_token = token[4:]
                # 不验证签名，只解析payload
                decoded = jwt.decode(jwt_token, options={"verify_signature": False})
                if 'exp' in decoded:
                    return datetime.fromtimestamp(decoded['exp'])
        except Exception as e:
            logger.warning(f"Failed to parse token expiry: {e}")
        return None
        
    def _is_token_expired_or_expiring(self) -> bool:
        """检查token是否已过期或即将过期"""
        if not self.current_token or not self.token_expiry:
            return True
            
        now = datetime.now()
        # 如果token在5分钟内过期，就认为需要刷新
        return now >= (self.token_expiry - timedelta(seconds=self.refresh_before_expiry))
        
    def _can_refresh_now(self) -> bool:
        """检查是否可以进行刷新（避免频繁刷新）"""
        current_time = time.time()
        return (current_time - self.last_refresh_attempt) >= self.refresh_cooldown
        
    async def _generate_new_token(self) -> Optional[str]:
        """生成新的API token"""
        try:
            logger.info("Generating new MicroSandbox API token...")
            
            # 执行token生成命令
            result = subprocess.run(
                ['msb', 'server', 'keygen'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"Token generation failed: {result.stderr}")
                return None
                
            # 从输出中提取token
            output = result.stdout.strip()
            token_match = re.search(r'(msb_[a-zA-Z0-9._-]+)', output)
            
            if token_match:
                new_token = token_match.group(1)
                logger.info("Successfully generated new token")
                return new_token
            else:
                logger.error(f"Could not extract token from output: {output}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error("Token generation timed out")
            return None
        except Exception as e:
            logger.error(f"Error generating token: {e}")
            return None
            
    def _update_env_file(self, new_token: str) -> bool:
        """更新.env文件中的token"""
        try:
            lines = []
            token_updated = False
            
            # 读取现有内容
            if self.env_path.exists():
                with open(self.env_path, 'r') as f:
                    lines = f.readlines()
            
            # 更新或添加MSB_API_KEY
            new_lines = []
            for line in lines:
                if line.startswith('MSB_API_KEY='):
                    new_lines.append(f'MSB_API_KEY={new_token}\n')
                    token_updated = True
                else:
                    new_lines.append(line)
            
            # 如果没有找到MSB_API_KEY行，添加它
            if not token_updated:
                new_lines.append(f'MSB_API_KEY={new_token}\n')
            
            # 写入文件
            with open(self.env_path, 'w') as f:
                f.writelines(new_lines)
                
            logger.info(f"Updated token in {self.env_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update env file: {e}")
            return False
            
    async def refresh_token_if_needed(self) -> bool:
        """如果需要，刷新token"""
        try:
            # 检查是否需要刷新
            if not self._is_token_expired_or_expiring():
                return True  # token仍然有效
                
            # 检查冷却时间
            if not self._can_refresh_now():
                logger.info("Token refresh is in cooldown period")
                return False
                
            self.last_refresh_attempt = time.time()
            
            # 生成新token
            new_token = await self._generate_new_token()
            if not new_token:
                logger.error("Failed to generate new token")
                return False
                
            # 更新环境文件
            if not self._update_env_file(new_token):
                logger.error("Failed to update env file with new token")
                return False
                
            # 更新内存中的token信息
            self.current_token = new_token
            self.token_expiry = self._get_token_expiry(new_token)
            
            # 重新加载环境变量
            load_dotenv(self.env_path, override=True)
            
            logger.info(f"Successfully refreshed token, new expiry: {self.token_expiry}")
            return True
            
        except Exception as e:
            logger.error(f"Error during token refresh: {e}")
            return False
            
    async def get_valid_token(self) -> Optional[str]:
        """获取有效的token，如果需要会自动刷新"""
        # 尝试刷新token
        refresh_success = await self.refresh_token_if_needed()
        
        if refresh_success and self.current_token:
            return self.current_token
        else:
            logger.warning("No valid token available")
            return None
            
    def get_token_info(self) -> Dict[str, Any]:
        """获取token状态信息"""
        return {
            "has_token": bool(self.current_token),
            "token_expiry": self.token_expiry.isoformat() if self.token_expiry else None,
            "is_expired": self._is_token_expired_or_expiring(),
            "time_until_expiry": str(self.token_expiry - datetime.now()) if self.token_expiry else None
        }
        
    def is_token_error(self, error_message: str) -> bool:
        """检查错误消息是否表示token问题"""
        token_error_patterns = [
            "Invalid or expired token",
            "Authentication failed",
            "Unauthorized",
            "code\":1004",  # MicroSandbox specific token error code
            "Authentication error"
        ]
        
        error_lower = error_message.lower()
        return any(pattern.lower() in error_lower for pattern in token_error_patterns)


class AutoRefreshTokenManager:
    """带自动后台刷新的Token管理器"""
    
    def __init__(self, env_path: Optional[Path] = None):
        self.token_manager = MicroSandboxTokenManager(env_path)
        self.auto_refresh_task = None
        self.is_running = False
        
    async def start_auto_refresh(self, check_interval: int = 60):
        """启动自动刷新后台任务"""
        if self.is_running:
            return
            
        self.is_running = True
        self.auto_refresh_task = asyncio.create_task(
            self._auto_refresh_loop(check_interval)
        )
        logger.info("Started automatic token refresh service")
        
    async def stop_auto_refresh(self):
        """停止自动刷新"""
        self.is_running = False
        if self.auto_refresh_task:
            self.auto_refresh_task.cancel()
            try:
                await self.auto_refresh_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped automatic token refresh service")
        
    async def _auto_refresh_loop(self, check_interval: int):
        """自动刷新循环"""
        while self.is_running:
            try:
                await self.token_manager.refresh_token_if_needed()
                await asyncio.sleep(check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in auto refresh loop: {e}")
                await asyncio.sleep(check_interval)
                
    async def get_valid_token(self) -> Optional[str]:
        """获取有效token"""
        return await self.token_manager.get_valid_token()
        
    async def refresh_token_if_needed(self) -> bool:
        """如果需要，刷新token"""
        return await self.token_manager.refresh_token_if_needed()
        
    def is_token_error(self, error_message: str) -> bool:
        """检查是否为token错误"""
        return self.token_manager.is_token_error(error_message)
        
    def get_token_info(self) -> Dict[str, Any]:
        """获取token信息"""
        return self.token_manager.get_token_info()