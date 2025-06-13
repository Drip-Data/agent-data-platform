"""
Tools package for Reasoning Runtime
"""

from .python_executor_tool import PythonExecutorTool

# 延迟导入BrowserTool，避免playwright依赖问题
def get_browser_tool_class():
    """延迟导入BrowserTool类"""
    try:
        from .browser_tool import BrowserTool
        return BrowserTool
    except ImportError as e:
        print(f"Warning: Cannot import BrowserTool: {e}")
        return None

# 延迟初始化全局实例，避免在导入时创建
def get_browser_tool():
    """获取浏览器工具实例，延迟初始化"""
    if not hasattr(get_browser_tool, '_instance'):
        try:
            from .browser_tool import browser_tool
            get_browser_tool._instance = browser_tool
        except ImportError:
            get_browser_tool._instance = None
    return get_browser_tool._instance

def get_python_executor_tool():
    """获取Python执行器工具实例，延迟初始化"""
    if not hasattr(get_python_executor_tool, '_instance'):
        from .python_executor_tool import python_executor_tool
        get_python_executor_tool._instance = python_executor_tool
    return get_python_executor_tool._instance

# 尝试导入BrowserTool，如果失败则为None
try:
    from .browser_tool import BrowserTool
    __all__ = [
        'BrowserTool',
        'PythonExecutorTool',
        'get_browser_tool',
        'get_python_executor_tool',
        'get_browser_tool_class'
    ]
except ImportError:
    BrowserTool = None
    __all__ = [
        'PythonExecutorTool',
        'get_browser_tool',
        'get_python_executor_tool',
        'get_browser_tool_class'
    ]
