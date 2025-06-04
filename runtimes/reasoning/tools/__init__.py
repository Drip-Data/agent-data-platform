"""
Tools package for Reasoning Runtime
"""

from .python_executor_tool import PythonExecutorTool
from .deep_research_tool import DeepResearchTool, deep_research_tool # Import the class as well

# 延迟初始化全局实例，避免在导入时创建
def get_python_executor_tool():
    """获取Python执行器工具实例，延迟初始化"""
    if not hasattr(get_python_executor_tool, '_instance'):
        from .python_executor_tool import python_executor_tool
        get_python_executor_tool._instance = python_executor_tool
    return get_python_executor_tool._instance

__all__ = [
    'PythonExecutorTool',
    'DeepResearchTool', # Export the class
    'deep_research_tool',
    'get_python_executor_tool'
]
