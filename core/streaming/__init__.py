"""
Sequential Streaming 执行模块

提供多步骤XML流式执行能力，支持：
- Sequential工具调用序列
- 自动结果注入
- 状态管理和错误恢复
- 智能action选择
"""

from .sequential_executor import SequentialStreamingExecutor
from .state_manager import StreamingStateManager
from .result_injector import ResultInjector

__all__ = [
    'SequentialStreamingExecutor',
    'StreamingStateManager', 
    'ResultInjector'
]