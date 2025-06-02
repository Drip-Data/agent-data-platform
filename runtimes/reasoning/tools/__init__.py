"""
Tools package for Reasoning Runtime
"""

from .browser_tool import BrowserTool
from .python_executor_tool import PythonExecutorTool

# 延迟初始化全局实例，避免在导入时创建
def get_browser_tool():
    """获取浏览器工具实例，延迟初始化"""
    if not hasattr(get_browser_tool, '_instance'):
        from .browser_tool import browser_tool
        get_browser_tool._instance = browser_tool
    return get_browser_tool._instance

def get_python_executor_tool():
    """获取Python执行器工具实例，延迟初始化"""
    if not hasattr(get_python_executor_tool, '_instance'):
        from .python_executor_tool import python_executor_tool
        get_python_executor_tool._instance = python_executor_tool
    return get_python_executor_tool._instance

__all__ = [
    'BrowserTool',
    'PythonExecutorTool',
    'get_browser_tool',
    'get_python_executor_tool'
]
