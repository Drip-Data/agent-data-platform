import ast
import asyncio
import io
import logging
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr
from typing import Dict, Any, Optional
import os # Added import for os

try:
    from core.interfaces import LocalToolInterface, LocalToolSpec
except ImportError: # Fallback for direct execution or different structure
    # This assumes 'core' is a sibling directory or in PYTHONPATH
    # Adjust based on your actual project structure if this fallback is hit
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    from core.interfaces import LocalToolInterface, LocalToolSpec


logger = logging.getLogger(__name__)

class RestrictedPythonExecutor:
    """受限Python执行器，提供安全的代码执行环境"""

    def __init__(self, timeout: int = 5):
        self.timeout = timeout
        self.allowed_builtins = {
            'abs', 'all', 'any', 'ascii', 'bin', 'bool', 'bytearray', 'bytes', 'callable',
            'chr', 'classmethod', 'complex', 'delattr', 'dict', 'dir', 'divmod', 'enumerate',
            'filter', 'float', 'format', 'frozenset', 'getattr', 'globals', 'hasattr',
            'hash', 'help', 'hex', 'id', 'input', 'int', 'isinstance', 'issubclass', 'iter',
            'len', 'list', 'locals', 'map', 'max', 'memoryview', 'min', 'next', 'object',
            'oct', 'open', 'ord', 'pow', 'print', 'property', 'range', 'repr', 'reversed',
            'round', 'set', 'setattr', 'slice', 'sorted', 'staticmethod', 'str', 'sum',
            'super', 'tuple', 'type', 'vars', 'zip', '__import__', # Note: __import__ is powerful
        }
        # More restrictive set of allowed modules
        self.allowed_modules = {
            'math', 'random', 'time', 'datetime', 're', 'json', 'collections',
            'itertools', 'functools', 'operator', 'string', 'copy', 'decimal', 'fractions',
            'statistics', 'hashlib', 'base64', 'struct', 'array', 'heapq', 'bisect',
            'queue', 'enum', 'typing', 'dataclasses', 'pathlib', 'urllib.parse'
        }
        # Disallow specific dangerous builtins even if they are in the general list
        self.disallowed_builtins = {'eval', 'exec', 'compile', 'open', 'input', '__import__', 'globals', 'locals', 'vars', 'dir'}


    def _validate_ast(self, tree: ast.AST) -> bool:
        """验证AST语法树，检查不安全的操作"""
        for node in ast.walk(tree):
            # Disallow import *
            if isinstance(node, ast.ImportFrom) and node.module is None and any(alias.name == '*' for alias in node.names):
                raise ValueError("不允许使用 'from ... import *'")

            # Check import statements
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module_name_to_check = None
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_name_to_check = alias.name.split('.')[0]
                        if module_name_to_check not in self.allowed_modules:
                            raise ValueError(f"不允许导入模块: {module_name_to_check}")
                else:  # ImportFrom
                    if node.module: # Relative imports (level > 0) are tricky, disallow for now or handle carefully
                        if node.level > 0:
                            raise ValueError("不允许相对导入")
                        module_name_to_check = node.module.split('.')[0]
                        if module_name_to_check not in self.allowed_modules:
                            raise ValueError(f"不允许从模块导入: {module_name_to_check}")
                    # Allow importing names from allowed modules, e.g. `from math import sqrt`

            # Check function calls
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                func_name = node.func.id
                if func_name in self.disallowed_builtins:
                    raise ValueError(f"不允许使用内置函数: {func_name}")
                # Further checks for specific function arguments if needed

            # Check attribute access for dunder methods
            elif isinstance(node, ast.Attribute):
                if node.attr.startswith('__') and node.attr.endswith('__'):
                    # A very basic whitelist for dunder methods. This needs to be comprehensive.
                    allowed_dunders = {'__init__', '__str__', '__repr__', '__add__', '__sub__',
                                       '__mul__', '__div__', '__eq__', '__lt__', '__gt__',
                                       '__len__', '__getitem__', '__setitem__', '__iter__', '__next__',
                                       '__call__', '__enter__', '__exit__', '__name__', '__doc__'}
                    if node.attr not in allowed_dunders:
                        raise ValueError(f"不允许访问受限的双下划线属性: {node.attr}")
            # Disallow `del` statement for now, can be too powerful
            elif isinstance(node, ast.Delete):
                raise ValueError("不允许使用 'del' 语句")
            # Disallow `with` statement if it could open files or network connections without control
            # This is too broad, `with` itself is fine. Control what can be used with `with`.
            # elif isinstance(node, ast.With):
            #     raise ValueError("不允许使用 'with' 语句 (for now, to be refined)")


        return True

    async def execute(self, code: str, globals_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Prepare execution environment
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        # Prepare globals
        if globals_dict is None:
            globals_dict = {}

        # Filter builtins
        safe_builtins = {name: func for name, func in __builtins__.items() # type: ignore
                         if name in self.allowed_builtins and name not in self.disallowed_builtins}
        globals_dict['__builtins__'] = safe_builtins

        # Pre-import allowed modules into the globals_dict
        for module_name in self.allowed_modules:
            try:
                globals_dict[module_name] = __import__(module_name)
            except ImportError:
                logger.warning(f"无法预导入允许的模块: {module_name}")


        # Parse code to AST
        try:
            tree = ast.parse(code, mode='exec')
        except SyntaxError as e:
            return {"success": False, "error": f"语法错误: {str(e)}", "line": e.lineno, "offset": e.offset}

        # Validate AST
        try:
            self._validate_ast(tree)
        except ValueError as e:
            return {"success": False, "error": f"安全限制: {str(e)}"}


        # Execute code
        try:
            async def execute_code_timed():
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, self._execute_in_thread, code, globals_dict, stdout_capture, stderr_capture)

            result_dict = await asyncio.wait_for(execute_code_timed(), timeout=self.timeout)
            return result_dict
        except asyncio.TimeoutError:
            return {"success": False, "error": f"执行超时（限制{self.timeout}秒）", "stdout": stdout_capture.getvalue(), "stderr": stderr_capture.getvalue()}
        except Exception as e: # Catch-all for unexpected errors during execution logic
            logger.error(f"执行Python代码时发生意外错误: {e}", exc_info=True)
            return {"success": False, "error": f"意外执行错误: {str(e)}", "stdout": stdout_capture.getvalue(), "stderr": stderr_capture.getvalue()}

    def _execute_in_thread(self, code: str, globals_dict: Dict[str, Any], stdout_capture: io.StringIO, stderr_capture: io.StringIO) -> Dict[str, Any]:
        """Synchronous execution part, run in a thread."""
        exec_result = None
        # Create a fresh locals dict for each execution
        locals_dict: Dict[str, Any] = {}

        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                compiled_code = compile(code, '<string>', 'exec')
                exec(compiled_code, globals_dict, locals_dict) # Execute in the prepared globals and fresh locals

                # Try to get a result if one was assigned to a conventional name
                if 'result' in locals_dict:
                    exec_result = locals_dict['result']
                elif '__result__' in locals_dict: # Another convention
                    exec_result = locals_dict['__result__']
                # If no specific result variable, consider the value of the last expression if possible (more complex)

        except Exception as e:
            # Capture traceback within the sandboxed execution
            exc_type, exc_value, tb = sys.exc_info()
            tb_text = "".join(traceback.format_exception(exc_type, exc_value, tb))
            # Filter out system paths from traceback for security/clarity
            # This is a simple filter, might need refinement
            filtered_tb_text = "\n".join(line for line in tb_text.splitlines() if "<string>" in line or "File \"<string>\"" in line)

            return {"success": False, "error": f"执行时异常: {str(e)}", "traceback": filtered_tb_text, "stdout": stdout_capture.getvalue(), "stderr": stderr_capture.getvalue()}

        # Prepare locals for output, stringifying complex objects
        output_locals = {}
        for k, v in locals_dict.items():
            if not k.startswith("__"): # Exclude dunder names from locals output
                try:
                    output_locals[k] = repr(v) # Use repr for a more debug-friendly representation
                except Exception:
                    output_locals[k] = f"<unrepresentable object of type {type(v).__name__}>"


        return {"success": True, "result": exec_result, "stdout": stdout_capture.getvalue(), "stderr": stderr_capture.getvalue(), "locals": output_locals}


class PythonExecutorTool(LocalToolInterface):
    """Python代码执行工具"""

    def __init__(self, timeout: int = 5):
        self.executor = RestrictedPythonExecutor(timeout=timeout)
        self._tool_spec = LocalToolSpec(
            tool_id="python_executor",
            name="Python代码执行器",
            description="在安全的沙箱环境中执行Python代码",
            version="1.0.0",
            actions=[{
                "name": "execute_code",
                "description": "执行Python代码",
                "parameters": {
                    "code": {"type": "string", "description": "要执行的Python代码", "required": True},
                    "timeout": {"type": "integer", "description": "执行超时时间（秒）", "default": 5, "required": False}
                }
            }],
            type="function", # This tool is used like a function by the agent
            metadata={"category": "development", "icon": "python", "requires_sandbox": True}
        )

    @property
    def tool_spec(self) -> LocalToolSpec:
        return self._tool_spec

    async def execute(self, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        if action != "execute_code":
            return {"success": False, "error": f"不支持的动作: {action}"}

        code = parameters.get("code")
        if not code:
            return {"success": False, "error": "代码不能为空"}

        timeout = parameters.get("timeout", self.executor.timeout) # Use tool's default if not provided
        # Update executor's timeout if a new one is provided for this specific call
        # This assumes the executor instance can have its timeout updated per call,
        # or a new executor is instantiated/configured. For simplicity, let's update.
        original_timeout = self.executor.timeout
        if timeout != original_timeout:
            self.executor.timeout = timeout

        result = await self.executor.execute(str(code)) # Ensure code is string

        # Restore original timeout if it was changed for this call
        if timeout != original_timeout:
            self.executor.timeout = original_timeout

        return result

    async def shutdown(self):
        # No specific shutdown actions needed for this tool itself
        logger.info("PythonExecutorTool shutdown (no-op).")
        pass