# MCP Servers Package
# 
# 为避免在导入 `mcp_servers` 包时就立即执行各子服务器的 main 模块，
# 这里不再主动 `import` 具体实现文件。这样可以消除如下 RuntimeWarning：
#   RuntimeWarning: 'mcp_servers.browser_navigator_server.main' found in sys.modules after import of package 'mcp_servers.browser_navigator_server', but prior to execution of 'mcp_servers.browser_navigator_server.main'; this may result in unpredictable behaviour
# 类似警告同样会出现在 `python_executor_server.main`。
# 如果在其他代码中需要使用具体的 Server 类，请显式按需导入，例如：
#     from mcp_servers.browser_navigator_server.main import BrowserNavigatorMCPServer
#     from mcp_servers.python_executor_server.main import PythonExecutorMCPServer
#
# 为了让 `from mcp_servers import BrowserNavigatorMCPServer` 这类写法仍然可用，
# 我们提供一个按需加载（lazy import）的实现。

from importlib import import_module
from types import ModuleType
from typing import Any, Dict

__all__ = [
    "BrowserNavigatorMCPServer",
    "PythonExecutorMCPServer",
]

# 缓存已加载的对象，避免重复导入
_lazy_objects: Dict[str, Any] = {}


def __getattr__(name: str) -> Any:  # type: ignore
    """在首次访问属性时才加载对应的 Server 类。"""
    if name in _lazy_objects:
        return _lazy_objects[name]

    if name == "BrowserNavigatorMCPServer":
        module = import_module("mcp_servers.browser_navigator_server.main")
        obj = getattr(module, name)
    elif name == "PythonExecutorMCPServer":
        module = import_module("mcp_servers.python_executor_server.main")
        obj = getattr(module, name)
    else:
        raise AttributeError(f"module 'mcp_servers' has no attribute '{name}'")

    _lazy_objects[name] = obj
    return obj