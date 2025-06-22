"""
Browser-Use MCP Server
基于browser-use的AI浏览器自动化服务，支持自然语言任务执行
"""

# 避免循环导入和模块冲突
import sys
import os

# 确保模块路径正确
current_dir = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(current_dir, '../..')))

# 延迟导入避免RuntimeWarning
def get_browser_use_server():
    from .main import BrowserUseMCPServer
    return BrowserUseMCPServer

__all__ = ['get_browser_use_server']