from .sandbox import LightweightSandboxRuntime, NSJailExecutor
from .reasoning import ReasoningRuntime

# 延迟导入web_navigator相关模块，避免playwright依赖问题
def get_web_navigator_classes():
    """延迟导入web navigator相关类"""
    try:
        from .web_navigator import MemoryControlledWebRuntime, BrowserManager
        return MemoryControlledWebRuntime, BrowserManager
    except ImportError as e:
        print(f"Warning: Cannot import web navigator classes: {e}")
        return None, None

# 为了向后兼容，尝试导入但不强制要求
try:
    from .web_navigator import MemoryControlledWebRuntime, BrowserManager
    __all__ = [
        'LightweightSandboxRuntime', 
        'NSJailExecutor',
        'MemoryControlledWebRuntime', 
        'BrowserManager',
        'ReasoningRuntime',
        'get_web_navigator_classes'
    ]
except ImportError:
    # 如果导入失败，不包含web navigator相关类
    MemoryControlledWebRuntime = None
    BrowserManager = None
    __all__ = [
        'LightweightSandboxRuntime', 
        'NSJailExecutor',
        'ReasoningRuntime',
        'get_web_navigator_classes'
    ]