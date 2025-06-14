"""
运行时模块 - 已简化为仅包含enhanced-reasoning-runtime

注意：历史运行时(sandbox, web_navigator)已被移除
所有功能已迁移至MCP服务器，通过enhanced-reasoning-runtime + toolscore调用
迁移日期: 2025-06-14
"""

# 只保留推理运行时，其他功能通过MCP服务器提供
from .reasoning.enhanced_runtime import EnhancedReasoningRuntime

__all__ = [
    'EnhancedReasoningRuntime'
]