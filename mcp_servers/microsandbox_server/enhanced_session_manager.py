#!/usr/bin/env python3
"""
增强的会话管理器
解决会话管理核心问题，包括本地会话支持
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Any, Optional
import subprocess
import os
from pathlib import Path

logger = logging.getLogger(__name__)

class LocalSessionManager:
    """本地会话管理器 - 当MicroSandbox不可用时使用"""
    
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.session_timeout = 3600  # 1小时
        
    def create_session(self, session_id: str) -> Dict[str, Any]:
        """创建本地会话"""
        session_data = {
            'session_id': session_id,
            'created_at': time.time(),
            'last_accessed': time.time(),
            'variables': {},  # 存储会话变量
            'execution_count': 0,
            'type': 'local'
        }
        
        self.sessions[session_id] = session_data
        logger.info(f"Created local session: {session_id}")
        return session_data
        
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话"""
        if session_id in self.sessions:
            self.sessions[session_id]['last_accessed'] = time.time()
            return self.sessions[session_id]
        return None
        
    def close_session(self, session_id: str) -> bool:
        """关闭会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Closed local session: {session_id}")
            return True
        return False
        
    def list_sessions(self) -> list:
        """列出所有会话"""
        return [
            {
                'session_id': sid,
                'created_at': data['created_at'],
                'last_accessed': data['last_accessed'],
                'execution_count': data['execution_count'],
                'type': data['type']
            }
            for sid, data in self.sessions.items()
        ]
        
    def cleanup_expired_sessions(self, max_age: int = None) -> list:
        """清理过期会话"""
        if max_age is None:
            max_age = self.session_timeout
            
        current_time = time.time()
        expired_sessions = []
        
        for session_id, session_data in list(self.sessions.items()):
            if current_time - session_data['last_accessed'] > max_age:
                expired_sessions.append(session_id)
                del self.sessions[session_id]
                
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired local sessions")
            
        return expired_sessions
        
    async def execute_code(self, session_id: str, code: str, timeout: int = 30) -> Dict[str, Any]:
        """在本地会话中执行代码"""
        session = self.get_session(session_id)
        if not session:
            session = self.create_session(session_id)
            
        try:
            # 构建包含会话变量的执行环境
            session_vars = session['variables']
            
            # 创建包含会话变量的代码
            setup_code = ""
            for var_name, var_value in session_vars.items():
                setup_code += f"{var_name} = {repr(var_value)}\n"
                
            full_code = setup_code + code
            
            # 执行代码
            proc = await asyncio.create_subprocess_exec(
                'python3', '-c', full_code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                success = proc.returncode == 0
                
                # 尝试提取新的会话变量（简单实现）
                if success:
                    # 这里可以实现更复杂的变量提取逻辑
                    # 目前只处理简单赋值
                    lines = code.strip().split('\n')
                    for line in lines:
                        line = line.strip()
                        if '=' in line and not line.startswith('#'):
                            parts = line.split('=', 1)
                            if len(parts) == 2:
                                var_name = parts[0].strip()
                                if var_name.isidentifier():
                                    # 简单赋值检测
                                    try:
                                        var_value = eval(parts[1].strip())
                                        session['variables'][var_name] = var_value
                                    except:
                                        pass  # 忽略复杂表达式
                
                session['execution_count'] += 1
                session['last_accessed'] = time.time()
                
                return {
                    "success": success,
                    "stdout": stdout.decode('utf-8') if stdout else "",
                    "stderr": stderr.decode('utf-8') if stderr else "",
                    "return_code": proc.returncode or 0
                }
                
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Execution timeout ({timeout}s)",
                    "return_code": -1
                }
                
        except Exception as e:
            logger.error(f"Local session execution error: {e}")
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "return_code": -1
            }

class EnhancedSessionManager:
    """增强的会话管理器 - 支持MicroSandbox和本地回退"""
    
    def __init__(self, config):
        self.config = config
        self.local_manager = LocalSessionManager()
        self.use_local_fallback = True  # 默认使用本地回退
        
    async def ensure_microsandbox_available(self) -> bool:
        """检查MicroSandbox是否可用"""
        try:
            from microsandbox import PythonSandbox
            
            # 获取最新的API密钥
            env_path = Path(__file__).parent / '.env'
            api_key = None
            if env_path.exists():
                with open(env_path) as f:
                    for line in f:
                        if line.startswith('MSB_API_KEY='):
                            api_key = line.split('=', 1)[1].strip()
                            break
            
            if not api_key:
                logger.warning("No API key found in .env file")
                return False
                
            # 测试连接
            server_url = f"http://{self.config.MSB_HOST}:{self.config.MSB_PORT}"
            sandbox_kwargs = {
                'server_url': server_url,
                'api_key': api_key
            }
            
            sandbox = PythonSandbox(**sandbox_kwargs)
            try:
                await sandbox.start(timeout=3)
                await sandbox.stop()
                logger.info("MicroSandbox is available")
                return True
            except Exception as e:
                logger.warning(f"MicroSandbox test failed: {e}")
                return False
                
        except Exception as e:
            logger.warning(f"MicroSandbox availability check failed: {e}")
            return False
            
    async def execute_with_session(self, session_id: str, code: str, timeout: int = 30) -> Dict[str, Any]:
        """在会话中执行代码 - 支持回退"""
        
        # 首先尝试MicroSandbox（如果可用）
        if not self.use_local_fallback:
            microsandbox_available = await self.ensure_microsandbox_available()
            if microsandbox_available:
                try:
                    # TODO: 实现真正的MicroSandbox会话执行
                    pass
                except Exception as e:
                    logger.warning(f"MicroSandbox execution failed: {e}")
        
        # 使用本地会话管理器
        logger.info(f"Using local session manager for session: {session_id}")
        return await self.local_manager.execute_code(session_id, code, timeout)
        
    def list_sessions(self) -> Dict[str, Any]:
        """列出所有会话"""
        sessions = self.local_manager.list_sessions()
        return {
            "sessions": sessions,
            "total_count": len(sessions)
        }
        
    def close_session(self, session_id: str) -> Dict[str, Any]:
        """关闭会话"""
        success = self.local_manager.close_session(session_id)
        if success:
            return {
                "success": True,
                "message": f"Session {session_id} closed successfully"
            }
        else:
            return {
                "success": False,
                "error_message": f"会话不存在: {session_id}",
                "error_type": "SessionNotFound"
            }
            
    def cleanup_expired_sessions(self, max_age: int = None) -> Dict[str, Any]:
        """清理过期会话"""
        cleaned_sessions = self.local_manager.cleanup_expired_sessions(max_age)
        return {
            "cleaned_sessions": cleaned_sessions,
            "count": len(cleaned_sessions)
        }