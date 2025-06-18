"""
Enhanced Sandbox Python Executor
增强的沙箱Python执行器 - 集成MicroSandbox理念的改进版实现

特性:
1. 改进的沙箱隔离环境
2. 语法错误预检查
3. 支持pip依赖安装
4. 多轮debug会话支持
5. 变量状态跟踪
"""

import asyncio
import ast
import logging
import os
import sys
import tempfile
import time
import uuid
import json
import subprocess
import traceback
import re
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, asdict
from pathlib import Path
import threading
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core.utils.path_utils import get_python_execution_dir

# MicroSandbox imports
try:
    from microsandbox import PythonSandbox
    from microsandbox.types import SandboxRunResult, SandboxOutput
except ImportError:
    # 如果MicroSandbox未安装，定义占位符类型
    class PythonSandbox:
        @classmethod
        async def create(cls, **kwargs):
            raise ImportError("microsandbox library not installed")
    
    class SandboxRunResult:
        async def output(self):
            raise ImportError("microsandbox library not installed")
    
    class SandboxOutput:
        exit_code = -1
        stdout = ""
        stderr = ""

logger = logging.getLogger(__name__)

@dataclass
class SyntaxErrorInfo:
    line: int
    column: int
    message: str
    error_type: str

@dataclass
class SyntaxResult:
    is_valid: bool
    errors: List[SyntaxErrorInfo]
    warnings: List[str]
    suggestions: List[str]

@dataclass
class ExecutionResult:
    success: bool
    stdout: str
    stderr: str
    return_code: int
    execution_time: float
    session_id: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    suggestions: Optional[List[str]] = None
    syntax_check: Optional[SyntaxResult] = None

@dataclass
class DebugSession:
    session_id: str
    created_at: float
    last_accessed: float
    working_dir: str
    installed_packages: Set[str]
    variables_cache: Dict[str, Any]
    execution_history: List[Dict[str, Any]]
    sandbox: Optional[Any] = None # 存储MicroSandbox实例，使用Any避免类型错误

class SyntaxAnalyzer:
    """语法分析器"""
    
    def analyze_syntax(self, code: str) -> SyntaxResult:
        """分析代码语法"""
        errors = []
        warnings = []
        suggestions = []
        
        try:
            # 尝试解析AST
            tree = ast.parse(code)
            
            # 静态分析检查
            warnings.extend(self._check_best_practices(tree))
            warnings.extend(self._check_security_issues(tree))
            
        except SyntaxError as e:
            errors.append(SyntaxErrorInfo(
                line=e.lineno or 0,
                column=e.offset or 0,
                message=e.msg,
                error_type="SyntaxError"
            ))
            suggestions.extend(self._suggest_syntax_fixes(e))
        
        except Exception as e:
            errors.append(SyntaxErrorInfo(
                line=0,
                column=0,
                message=str(e),
                error_type="ParseError"
            ))
        
        return SyntaxResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions
        )
    
    def _check_best_practices(self, tree: ast.AST) -> List[str]:
        """检查最佳实践"""
        warnings = []
        
        for node in ast.walk(tree):
            # 检查裸露的except语句
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                warnings.append(f"行{node.lineno}: 建议指定具体的异常类型而不是使用裸露的except")
            
            # 检查过长的行
            if hasattr(node, 'lineno'):
                # 这里简化处理，实际中需要访问源码
                pass
        
        return warnings
    
    def _check_security_issues(self, tree: ast.AST) -> List[str]:
        """检查安全问题"""
        warnings = []
        dangerous_functions = {'eval', 'exec', '__import__'}
        dangerous_modules = {'os', 'subprocess', 'sys'}
        
        for node in ast.walk(tree):
            # 检查危险函数调用
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in dangerous_functions:
                    warnings.append(f"行{node.lineno}: 使用了潜在危险的函数 '{node.func.id}'")
            
            # 检查危险模块导入
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in dangerous_modules:
                        warnings.append(f"行{node.lineno}: 导入了潜在危险的模块 '{alias.name}'")
        
        return warnings
    
    def _suggest_syntax_fixes(self, error: SyntaxError) -> List[str]:
        """根据语法错误提供修复建议"""
        suggestions = []
        msg = error.msg.lower()
        
        if "invalid syntax" in msg:
            if "(" in str(error.text or ""):
                suggestions.append("🔍 检查括号是否匹配")
            if ":" in msg:
                suggestions.append("📝 检查冒号是否缺失（如if、for、def语句）")
        elif "indent" in msg:
            suggestions.append("📏 检查缩进是否正确（Python使用4个空格）")
        elif "quote" in msg or "string" in msg:
            suggestions.append("📄 检查引号是否匹配")
        elif "eof" in msg:
            suggestions.append("📋 代码可能不完整，检查是否缺少结束符")
        
        return suggestions

class PackageManager:
    """包管理器"""
    
    def __init__(self, sandbox: Any):
        self.sandbox = sandbox
        self.installed_packages: Set[str] = set()
    
    async def install_package(self, package_name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """安装Python包"""
        try:
            # 验证包名安全性
            if not self._is_safe_package_name(package_name):
                return {
                    "success": False,
                    "error": f"Invalid or potentially unsafe package name: {package_name}"
                }
            
            # 构造安装命令
            install_cmd = ["pip", "install"]
            if version:
                install_cmd.append(f"{package_name}=={version}")
            else:
                install_cmd.append(package_name)
            
            # 在MicroSandbox中执行安装
            result = await self.sandbox.run(" ".join(install_cmd))
            output = await result.output()
            
            if output.exit_code == 0:
                self.installed_packages.add(package_name)
                return {
                    "success": True,
                    "package": package_name,
                    "version": version,
                    "message": f"Successfully installed {package_name}",
                    "stdout": output.stdout
                }
            else:
                return {
                    "success": False,
                    "package": package_name,
                    "error": output.stderr,
                    "stdout": output.stdout
                }
        
        except Exception as e:
            return {
                "success": False,
                "package": package_name,
                "error": str(e)
            }
    
    def _is_safe_package_name(self, package_name: str) -> bool:
        """验证包名是否安全"""
        # 基本的包名验证
        if not re.match(r'^[a-zA-Z0-9_-]+([.][a-zA-Z0-9_-]+)*$', package_name):
            return False
        
        # 检查是否包含危险字符
        dangerous_chars = ['&', '|', ';', '`', '$', '(', ')', '{', '}', '<', '>']
        if any(char in package_name for char in dangerous_chars):
            return False
        
        # 检查黑名单包
        blacklist = ['malware', 'virus', 'hack']
        if any(bad in package_name.lower() for bad in blacklist):
            return False
            
        return True
    
    async def check_package_availability(self, package_name: str) -> bool:
        """检查包是否可用"""
        try:
            # 在MicroSandbox中尝试导入包
            result = await self.sandbox.run(f"import {package_name}")
            output = await result.output()
            return output.exit_code == 0
        except:
            return False

class SessionManager:
    """会话管理器"""
    
    def __init__(self):
        self.active_sessions: Dict[str, DebugSession] = {}
        self.session_timeout = 3600  # 1小时超时
    
    async def create_session(self, session_id: Optional[str] = None) -> str:
        """创建新会话"""
        if not session_id:
            session_id = str(uuid.uuid4())
        
        # 创建会话工作目录 (MicroSandbox内部管理，这里可以简化)
        # working_dir = tempfile.mkdtemp(prefix=f"session_{session_id}_") # 不再需要外部工作目录
        
        # 创建MicroSandbox实例
        try:
            # 检查MicroSandbox是否可用
            if hasattr(PythonSandbox, 'create') and callable(getattr(PythonSandbox, 'create')):
                sandbox = await PythonSandbox.create(url="ws://localhost:8765") # 假设MicroSandbox服务器运行在8765端口
            else:
                logger.warning("MicroSandbox not available, using None placeholder")
                sandbox = None
        except Exception as e:
            logger.error(f"Failed to create MicroSandbox instance: {e}")
            sandbox = None
            
        session = DebugSession(
            session_id=session_id,
            created_at=time.time(),
            last_accessed=time.time(),
            working_dir="", # 不再需要外部工作目录
            installed_packages=set(),
            variables_cache={},
            execution_history=[],
            sandbox=sandbox # 存储沙箱实例
        )
        
        self.active_sessions[session_id] = session
        return session_id
    
    def get_session(self, session_id: str) -> Optional[DebugSession]:
        """获取会话"""
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            session.last_accessed = time.time()
            return session
        return None
    
    async def close_session(self, session_id: str) -> bool:
        """关闭会话"""
        if session_id not in self.active_sessions:
            return False
        
        session = self.active_sessions[session_id]
        
        # 关闭MicroSandbox实例
        if session.sandbox:
            try:
                await session.sandbox.close()
            except Exception as e:
                logger.warning(f"Failed to close MicroSandbox instance for session {session_id}: {e}")
        
        # 清理工作目录 (如果之前有创建的话，现在应该不需要了)
        # try:
        #     import shutil
        #     if os.path.exists(session.working_dir):
        #         shutil.rmtree(session.working_dir)
        # except Exception as e:
        #     logger.warning(f"Failed to cleanup session directory: {e}")
        
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
            await self.close_session(session_id) # 使用await调用close_session
            logger.info(f"Cleaned up expired session: {session_id}")

class EnhancedSandboxExecutor:
    """增强的沙箱Python执行器"""
    
    def __init__(self):
        self.output_dir = get_python_execution_dir()
        self.syntax_analyzer = SyntaxAnalyzer()
        self.session_manager = SessionManager()
        
        # 启动清理线程
        self._start_cleanup_thread()
    
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
        start_time = time.time()
        
        # 语法检查
        syntax_result = self.syntax_analyzer.analyze_syntax(code)
        if not syntax_result.is_valid:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="Syntax errors detected",
                return_code=-1,
                execution_time=time.time() - start_time,
                session_id=session_id,
                syntax_check=syntax_result,
                suggestions=syntax_result.suggestions
            )
        
        # 获取或创建会话
        current_session: Optional[DebugSession] = None
        if session_id:
            current_session = self.session_manager.get_session(session_id)
            if not current_session:
                session_id = await self.session_manager.create_session(session_id)
                current_session = self.session_manager.get_session(session_id)
        else:
            # 一次性执行，创建临时会话
            session_id = await self.session_manager.create_session()
            current_session = self.session_manager.get_session(session_id)
        
        if not current_session:
            # 如果会话创建失败，直接返回错误
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="Failed to create or retrieve session.",
                return_code=-1,
                execution_time=time.time() - start_time,
                session_id=session_id,
                syntax_check=syntax_result,
                suggestions=["无法创建或获取会话，请检查MicroSandbox服务器状态。"]
            )

        try:
            # 执行代码
            result = await self._execute_in_session(code, current_session, timeout)
            
            # 获取变量状态（如果启用调试）
            variables = None
            if enable_debug and result["success"]:
                variables = await self._get_session_variables(current_session)
                current_session.variables_cache = variables
            
            # 记录执行历史
            current_session.execution_history.append({
                "code": code,
                "timestamp": time.time(),
                "success": result["success"],
                "stdout": result["stdout"],
                "stderr": result["stderr"]
            })
            
            # 生成建议
            suggestions = self._generate_suggestions(code, result, syntax_result)
            
            execution_time = time.time() - start_time
            
            return ExecutionResult(
                success=result["success"],
                stdout=result["stdout"],
                stderr=result["stderr"],
                return_code=result["return_code"],
                execution_time=execution_time,
                session_id=session_id,
                variables=variables,
                suggestions=suggestions,
                syntax_check=syntax_result
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
                suggestions=["检查代码语法和执行环境"],
                syntax_check=syntax_result
            )
    
    async def install_package(self,
                             package_name: str,
                             session_id: str,
                             version: Optional[str] = None) -> ExecutionResult:
        """在会话中安装Python包"""
        session = self.session_manager.get_session(session_id)
        if not session:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="Session not found",
                return_code=-1,
                execution_time=0
            )
        
        # 使用会话中的MicroSandbox实例创建PackageManager
        if not session.sandbox:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="MicroSandbox instance not available for session",
                return_code=-1,
                execution_time=0
            )
        
        package_manager = PackageManager(session.sandbox) # 传入sandbox实例
        result = await package_manager.install_package(package_name, version)
        
        if result["success"]:
            session.installed_packages.add(package_name)
        
        return ExecutionResult(
            success=result["success"],
            stdout=result.get("stdout", ""),
            stderr=result.get("error", ""),
            return_code=0 if result["success"] else 1,
            execution_time=0,  # TODO: 实际计算时间
            session_id=session_id
        )
    
    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话信息"""
        session = self.session_manager.get_session(session_id)
        if not session:
            return None
        
        return {
            "session_id": session_id,
            "created_at": session.created_at,
            "last_accessed": session.last_accessed,
            "uptime": time.time() - session.created_at,
            "installed_packages": list(session.installed_packages),
            "variables_count": len(session.variables_cache),
            "execution_count": len(session.execution_history)
        }
    
    async def close_session(self, session_id: str) -> bool:
        """关闭会话"""
        return await self.session_manager.close_session(session_id) # 使用await
    
    # 私有方法
    async def _execute_in_session(self, code: str, session: DebugSession, timeout: int) -> Dict[str, Any]:
        """在会话中执行代码"""
        if not session.sandbox:
            return {
                "success": False,
                "stdout": "",
                "stderr": "MicroSandbox instance not available for session",
                "return_code": -1
            }
        
        try:
            # 准备执行代码，包含会话上下文
            exec_code = self._prepare_execution_code(code, session)
            
            # 在MicroSandbox中执行代码
            run_result = await session.sandbox.run(exec_code, timeout=timeout)
            output = await run_result.output()
            
            return {
                "success": output.exit_code == 0,
                "stdout": output.stdout,
                "stderr": output.stderr,
                "return_code": output.exit_code
            }
            
        except asyncio.TimeoutError:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Code execution timeout after {timeout} seconds",
                "return_code": -1
            }
        except Exception as e:
            logger.error(f"MicroSandbox execution failed: {e}")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"MicroSandbox execution error: {str(e)}",
                "return_code": -1
            }
    
    def _prepare_execution_code(self, code: str, session: DebugSession) -> str:
        """准备执行代码，包含会话上下文"""
        # 注入之前会话的变量状态
        variable_injection_code = ""
        if session.variables_cache:
            for var_name, var_value in session.variables_cache.items():
                # 只注入可JSON序列化的基本类型，避免repr()的复杂性
                if isinstance(var_value, (int, float, str, bool, list, dict, type(None))):
                    variable_injection_code += f"{var_name} = {json.dumps(var_value)}\n"
                else:
                    # 对于其他类型，不进行注入，或者可以考虑更复杂的序列化机制
                    logger.warning(f"Skipping non-serializable variable '{var_name}' of type {type(var_value)}")
            variable_injection_code += "\n"
    
    # 将用户代码和变量注入代码合并
    return variable_injection_code + code
    
    async def _get_session_variables(self, session: DebugSession) -> Dict[str, Any]:
        """获取会话中的变量状态"""
        if not session.sandbox:
            logger.warning("Cannot get session variables: MicroSandbox instance not available.")
            return {}
            
        var_script = """
import json
import sys
import types
 
def safe_serialize(obj):
    try:
        # 尝试JSON序列化
        json.dumps(obj)
        return obj
    except:
        # 如果无法序列化，返回字符串表示
        return str(obj)
 
# 获取全局变量
variables = {}
for name, value in globals().items():
    if not name.startswith('_') and name not in ['json', 'sys', 'types', 'safe_serialize']:
        # 跳过模块和函数
        if not isinstance(value, (types.ModuleType, types.FunctionType)):
            variables[name] = safe_serialize(value)
 
print(json.dumps(variables, indent=2))
"""
        
        try:
            # 直接在MicroSandbox中执行获取变量的脚本
            run_result: SandboxRunResult = await session.sandbox.run(var_script, timeout=5)
            output: SandboxOutput = await run_result.output()

            if output.exit_code == 0:
                return json.loads(output.stdout.strip())
            else:
                logger.warning(f"Failed to get session variables from sandbox. Stderr: {output.stderr}")
        except Exception as e:
            logger.warning(f"Failed to get session variables: {e}")
        
        return {}
    
    def _generate_suggestions(self, code: str, result: Dict[str, Any], syntax_result: SyntaxResult) -> List[str]:
        """生成改进建议"""
        suggestions = []
        
        # 添加语法建议
        suggestions.extend(syntax_result.suggestions)
        
        # 基于执行结果的建议
        if not result["success"]:
            stderr = result["stderr"].lower()
            
            if "nameerror" in stderr:
                suggestions.append("🔍 检查变量名是否正确定义")
            elif "typeerror" in stderr:
                suggestions.append("🔢 检查数据类型是否匹配")
            elif "keyerror" in stderr:
                suggestions.append("🔑 检查字典键是否存在")
            elif "indexerror" in stderr:
                suggestions.append("📋 检查列表索引是否越界")
            elif "modulenotfounderror" in stderr:
                suggestions.append("📦 尝试安装缺失的包")
            elif "timeout" in stderr:
                suggestions.append("⏱️ 代码执行超时，检查是否有无限循环")
            elif "microsandbox execution error" in stderr:
                suggestions.append("⚠️ MicroSandbox执行错误，请检查MicroSandbox服务器状态或代码兼容性。")
            else:
                suggestions.append("📖 查看错误信息并根据提示修改代码")
        
        # 添加警告建议
        for warning in syntax_result.warnings:
            suggestions.append(f"⚠️ {warning}")
        
        return suggestions
    
    def _start_cleanup_thread(self):
        """启动清理线程"""
        def cleanup_worker():
            while True:
                try:
                    # 在新的事件循环中运行异步清理任务
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.session_manager.cleanup_expired_sessions())
                    loop.close()
                    time.sleep(300)  # 每5分钟清理一次
                except Exception as e:
                    logger.error(f"Cleanup thread error: {e}")
                    time.sleep(60)  # 出错后等待1分钟再试
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()

# 创建全局实例
enhanced_executor = EnhancedSandboxExecutor()

# 测试函数
async def test_enhanced_executor():
    """测试增强执行器"""
    print("🧪 测试增强沙箱执行器...")
    
    # 测试1: 基础执行
    print("\n📝 测试基础代码执行...")
    result = await enhanced_executor.execute_code("print('Hello from Enhanced Sandbox!')")
    print(f"结果: {result.success}")
    print(f"输出: {result.stdout.strip()}")
    print(f"建议: {result.suggestions}")
    
    # 测试2: 语法错误
    print("\n📝 测试语法错误检查...")
    result = await enhanced_executor.execute_code("print('missing quote)")
    # 确保syntax_check不是None
    if result.syntax_check:
        print(f"语法有效: {result.syntax_check.is_valid}")
        print(f"错误: {[asdict(err) for err in result.syntax_check.errors]}")
    else:
        print("语法检查结果为None")
    print(f"建议: {result.suggestions}")
    
    # 测试3: 会话执行
    print("\n📝 测试会话执行...")
    session_id = str(uuid.uuid4())
    
    result1 = await enhanced_executor.execute_code("x = 42", session_id=session_id, enable_debug=True)
    print(f"设置变量: {result1.success}")
    print(f"变量: {result1.variables}")
    
    result2 = await enhanced_executor.execute_code("print(f'x = {x}')", session_id=session_id, enable_debug=True)
    print(f"读取变量: {result2.success}")
    print(f"输出: {result2.stdout.strip()}")
    print(f"变量: {result2.variables}")
    
    # 测试4: 会话信息
    session_info = await enhanced_executor.get_session_info(session_id)
    print(f"会话信息: {session_info}")
    
    # 清理
    await enhanced_executor.close_session(session_id)
    print(f"✅ 会话 {session_id} 已关闭")

if __name__ == "__main__":
    asyncio.run(test_enhanced_executor())