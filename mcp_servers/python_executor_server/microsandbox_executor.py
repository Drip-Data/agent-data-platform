"""
MicroSandbox增强Python执行器 - 示例实现
集成MicroSandbox提供硬件级隔离的代码执行环境
"""

import asyncio
import logging
import uuid
import time
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict

# MicroSandbox依赖 (需要先安装: pip install microsandbox)
try:
    from microsandbox import PythonSandbox
    MICROSANDBOX_AVAILABLE = True
except ImportError:
    MICROSANDBOX_AVAILABLE = False
    print("⚠️ MicroSandbox not available. Install with: pip install microsandbox")

logger = logging.getLogger(__name__)

@dataclass
class ExecutionResult:
    """代码执行结果"""
    success: bool
    stdout: str
    stderr: str
    return_code: int
    execution_time: float
    session_id: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    suggestions: Optional[List[str]] = None

@dataclass
class SandboxSession:
    """沙箱会话"""
    session_id: str
    created_at: float
    last_accessed: float
    sandbox: Optional[Any] = None  # PythonSandbox实例

class MicroSandboxExecutor:
    """基于MicroSandbox的增强Python执行器"""
    
    def __init__(self, microsandbox_url: str = "ws://localhost:8765"):
        self.microsandbox_url = microsandbox_url
        self.active_sessions: Dict[str, SandboxSession] = {}
        self.session_timeout = 3600  # 1小时会话超时
        
        if not MICROSANDBOX_AVAILABLE:
            logger.warning("MicroSandbox not available, falling back to basic execution")
    
    async def execute_code(self, 
                          code: str, 
                          session_id: Optional[str] = None,
                          timeout: int = 30,
                          enable_debug: bool = False) -> ExecutionResult:
        """
        执行Python代码
        
        Args:
            code: 要执行的Python代码
            session_id: 会话ID，用于多轮执行
            timeout: 超时时间（秒）
            enable_debug: 是否启用调试模式（获取变量状态）
        """
        if not MICROSANDBOX_AVAILABLE:
            return await self._fallback_execution(code, timeout)
        
        start_time = time.time()
        
        try:
            # 获取或创建沙箱
            sandbox = await self._get_or_create_sandbox(session_id)
            
            # 执行代码
            result = await sandbox.run(code, timeout=timeout)
            output = await result.output()
            
            execution_time = time.time() - start_time
            
            # 获取变量状态（如果启用调试）
            variables = None
            if enable_debug and output.exit_code == 0:
                variables = await self._get_variables(sandbox)
            
            # 生成建议
            suggestions = self._generate_suggestions(code, output)
            
            return ExecutionResult(
                success=output.exit_code == 0,
                stdout=output.stdout,
                stderr=output.stderr,
                return_code=output.exit_code,
                execution_time=execution_time,
                session_id=session_id,
                variables=variables,
                suggestions=suggestions
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Code execution failed: {e}")
            
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                execution_time=execution_time,
                session_id=session_id,
                suggestions=["检查代码语法和沙箱连接状态"]
            )
    
    async def install_package(self, 
                             package_name: str, 
                             session_id: Optional[str] = None,
                             version: Optional[str] = None) -> ExecutionResult:
        """
        在沙箱中安装Python包
        
        Args:
            package_name: 包名
            session_id: 会话ID
            version: 指定版本
        """
        if not MICROSANDBOX_AVAILABLE:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="MicroSandbox not available",
                return_code=-1,
                execution_time=0
            )
        
        # 构造安装命令
        install_cmd = f"import subprocess; subprocess.run(['pip', 'install', '{package_name}"
        if version:
            install_cmd += f"=={version}"
        install_cmd += "'], capture_output=True, text=True)"
        
        return await self.execute_code(install_cmd, session_id, timeout=120)
    
    async def check_syntax(self, code: str) -> Dict[str, Any]:
        """
        检查代码语法
        
        Args:
            code: 要检查的代码
            
        Returns:
            语法检查结果
        """
        try:
            import ast
            ast.parse(code)
            return {
                "valid": True,
                "errors": [],
                "warnings": [],
                "suggestions": []
            }
        except SyntaxError as e:
            return {
                "valid": False,
                "errors": [{
                    "line": e.lineno or 0,
                    "column": e.offset or 0,
                    "message": e.msg,
                    "type": "SyntaxError"
                }],
                "warnings": [],
                "suggestions": self._suggest_syntax_fixes(e)
            }
        except Exception as e:
            return {
                "valid": False,
                "errors": [{
                    "line": 0,
                    "column": 0,
                    "message": str(e),
                    "type": "ParseError"
                }],
                "warnings": [],
                "suggestions": ["检查代码格式和编码"]
            }
    
    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话信息"""
        if session_id not in self.active_sessions:
            return None
        
        session = self.active_sessions[session_id]
        return {
            "session_id": session_id,
            "created_at": session.created_at,
            "last_accessed": session.last_accessed,
            "active": session.sandbox is not None,
            "uptime": time.time() - session.created_at
        }
    
    async def close_session(self, session_id: str) -> bool:
        """关闭会话"""
        if session_id not in self.active_sessions:
            return False
        
        session = self.active_sessions[session_id]
        if session.sandbox:
            try:
                await session.sandbox.close()
            except Exception as e:
                logger.warning(f"Error closing sandbox: {e}")
        
        del self.active_sessions[session_id]
        return True
    
    async def cleanup_expired_sessions(self):
        """清理过期会话"""
        current_time = time.time()
        expired_sessions = []
        
        for session_id, session in self.active_sessions.items():
            if current_time - session.last_accessed > self.session_timeout:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            await self.close_session(session_id)
            logger.info(f"Cleaned up expired session: {session_id}")
    
    # 私有方法
    async def _get_or_create_sandbox(self, session_id: Optional[str]) -> 'PythonSandbox':
        """获取或创建沙箱实例"""
        if not session_id:
            # 一次性执行，创建临时沙箱
            return await PythonSandbox.create(
                url=self.microsandbox_url,
                memory_mb=512,
                cpus=1.0
            )
        
        # 检查会话是否存在
        if session_id not in self.active_sessions:
            # 创建新会话
            session = SandboxSession(
                session_id=session_id,
                created_at=time.time(),
                last_accessed=time.time()
            )
            session.sandbox = await PythonSandbox.create(
                url=self.microsandbox_url,
                memory_mb=1024,
                cpus=2.0
            )
            self.active_sessions[session_id] = session
        else:
            # 更新访问时间
            self.active_sessions[session_id].last_accessed = time.time()
        
        return self.active_sessions[session_id].sandbox
    
    async def _get_variables(self, sandbox: 'PythonSandbox') -> Dict[str, Any]:
        """获取沙箱中的变量状态"""
        try:
            var_code = """
import json
import sys

def safe_repr(obj):
    try:
        # 尝试JSON序列化
        json.dumps(obj)
        return obj
    except:
        return str(obj)

vars_dict = {}
for name, value in globals().items():
    if not name.startswith('_') and name not in ['json', 'sys', 'safe_repr']:
        vars_dict[name] = safe_repr(value)

print(json.dumps(vars_dict, indent=2))
"""
            result = await sandbox.run(var_code, timeout=5)
            output = await result.output()
            
            if output.exit_code == 0:
                return json.loads(output.stdout.strip())
        except Exception as e:
            logger.warning(f"Failed to get variables: {e}")
        
        return {}
    
    def _generate_suggestions(self, code: str, output: Any) -> List[str]:
        """基于执行结果生成改进建议"""
        suggestions = []
        
        if hasattr(output, 'exit_code') and output.exit_code != 0:
            stderr = output.stderr.lower()
            
            if "nameerror" in stderr:
                suggestions.append("🔍 检查变量名是否正确定义")
            elif "syntaxerror" in stderr:
                suggestions.append("📝 检查代码语法是否正确")
            elif "indentationerror" in stderr:
                suggestions.append("📏 检查代码缩进是否正确")
            elif "typeerror" in stderr:
                suggestions.append("🔢 检查数据类型是否匹配")
            elif "keyerror" in stderr:
                suggestions.append("🔑 检查字典键是否存在")
            elif "indexerror" in stderr:
                suggestions.append("📋 检查列表索引是否越界")
            elif "modulenotfounderror" in stderr:
                suggestions.append("📦 尝试安装缺失的包")
            else:
                suggestions.append("📖 查看错误信息并根据提示修改代码")
        
        return suggestions
    
    def _suggest_syntax_fixes(self, error: SyntaxError) -> List[str]:
        """根据语法错误提供修复建议"""
        suggestions = []
        msg = error.msg.lower()
        
        if "invalid syntax" in msg:
            if "(" in msg:
                suggestions.append("🔍 检查括号是否匹配")
            if ":" in msg:
                suggestions.append("📝 检查冒号是否缺失（如if、for、def语句）")
        elif "indent" in msg:
            suggestions.append("📏 检查缩进是否正确（Python使用4个空格）")
        elif "quote" in msg:
            suggestions.append("📄 检查引号是否匹配")
        
        return suggestions
    
    async def _fallback_execution(self, code: str, timeout: int) -> ExecutionResult:
        """当MicroSandbox不可用时的降级执行"""
        start_time = time.time()
        
        try:
            # 简单的安全检查
            if any(danger in code for danger in ['import os', 'subprocess', 'eval', 'exec']):
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr="Potentially unsafe code detected",
                    return_code=-1,
                    execution_time=0,
                    suggestions=["请使用安全的代码，避免系统调用"]
                )
            
            # 使用exec执行（仅用于演示，生产环境不推荐）
            import io
            from contextlib import redirect_stdout, redirect_stderr
            
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()
            
            try:
                with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                    exec(code)
                
                return ExecutionResult(
                    success=True,
                    stdout=stdout_capture.getvalue(),
                    stderr=stderr_capture.getvalue(),
                    return_code=0,
                    execution_time=time.time() - start_time,
                    suggestions=["建议使用MicroSandbox获得更好的安全性"]
                )
            except Exception as e:
                return ExecutionResult(
                    success=False,
                    stdout=stdout_capture.getvalue(),
                    stderr=str(e),
                    return_code=1,
                    execution_time=time.time() - start_time,
                    suggestions=["检查代码语法和逻辑错误"]
                )
                
        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                execution_time=time.time() - start_time
            )

# 测试函数
async def test_microsandbox_executor():
    """测试MicroSandbox执行器"""
    executor = MicroSandboxExecutor()
    
    print("🧪 测试基础代码执行...")
    result = await executor.execute_code("print('Hello from MicroSandbox!')")
    print(f"结果: {result.success}, 输出: {result.stdout.strip()}")
    
    print("\n🧪 测试语法检查...")
    syntax_check = await executor.check_syntax("print('valid code')")
    print(f"语法有效: {syntax_check['valid']}")
    
    syntax_check = await executor.check_syntax("print('missing quote)")
    print(f"语法有效: {syntax_check['valid']}, 错误: {syntax_check['errors']}")
    
    print("\n🧪 测试会话执行...")
    session_id = str(uuid.uuid4())
    result1 = await executor.execute_code("x = 42", session_id=session_id, enable_debug=True)
    print(f"设置变量: {result1.success}")
    
    result2 = await executor.execute_code("print(f'x = {x}')", session_id=session_id, enable_debug=True)
    print(f"读取变量: {result2.success}, 输出: {result2.stdout.strip()}")
    print(f"变量状态: {result2.variables}")
    
    # 清理
    await executor.close_session(session_id)
    print(f"\n✅ 会话 {session_id} 已关闭")

if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_microsandbox_executor())