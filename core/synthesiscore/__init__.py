"""
SynthesisCore - Task Synthesis Engine
智能任务合成引擎核心模块
"""

from .synthesis import SimpleSynthesizer, TaskEssence

# 可选导入，避免依赖问题
try:
    from .synthesis_api import app as synthesis_api
except ImportError:
    synthesis_api = None

# 新的统一管理器
try:
    from .synthesis_manager import SynthesisManager
except ImportError:
    SynthesisManager = None

try:
    from .docker_manager import DockerManager
except ImportError:
    DockerManager = None

from .init_synthesis_db import init_synthesis_database as init_database

__all__ = [
    'SimpleSynthesizer',
    'TaskEssence',
    'synthesis_api',
    'SynthesisManager',
    'DockerManager', 
    'init_database'
] 