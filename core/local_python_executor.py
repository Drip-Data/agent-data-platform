#!/usr/bin/env python3
"""
本地Python执行器，作为WebSocket连接失败时的备用方案
"""

import subprocess
import tempfile
import os
import logging
from typing import Dict, Any
import asyncio

logger = logging.getLogger(__name__)

class LocalPythonExecutor:
    """本地Python代码执行器"""
    
    def __init__(self):
        self.timeout = 30  # 默认超时30秒
        
    async def execute_python_code(self, code: str, timeout: int = None) -> Dict[str, Any]:
        """执行Python代码并返回结果"""
        if timeout is None:
            timeout = self.timeout
            
        try:
            logger.info(f"🐍 本地执行Python代码: {code[:100]}...")
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_file = f.name
            
            try:
                # 执行Python代码
                result = await asyncio.create_subprocess_exec(
                    'python', temp_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await asyncio.wait_for(
                    result.communicate(), 
                    timeout=timeout
                )
                
                stdout_str = stdout.decode('utf-8') if stdout else ''
                stderr_str = stderr.decode('utf-8') if stderr else ''
                
                return_code = result.returncode
                
                logger.info(f"✅ Python代码执行完成，返回码: {return_code}")
                if stdout_str:
                    logger.info(f"📤 输出: {stdout_str[:200]}...")
                if stderr_str:
                    logger.warning(f"⚠️ 错误输出: {stderr_str[:200]}...")
                
                return {
                    "success": return_code == 0,
                    "data": {
                        "stdout": stdout_str,
                        "stderr": stderr_str,
                        "return_code": return_code
                    },
                    "error_message": stderr_str if return_code != 0 else None,
                    "execution_time": 0.0  # 简化实现，不计算确切时间
                }
                
            finally:
                # 清理临时文件
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass
                    
        except asyncio.TimeoutError:
            logger.error(f"❌ Python代码执行超时 ({timeout}秒)")
            return {
                "success": False,
                "data": None,
                "error_message": f"Python代码执行超时 ({timeout}秒)",
                "execution_time": timeout
            }
        except Exception as e:
            logger.error(f"❌ Python代码执行异常: {e}")
            return {
                "success": False,
                "data": None,
                "error_message": str(e),
                "execution_time": 0.0
            }