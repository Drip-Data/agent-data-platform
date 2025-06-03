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

try:
    from .trigger_synthesis import SynthesisTrigger
except ImportError:
    SynthesisTrigger = None

try:
    from .view_synthesis_db import view_essences, view_generated_tasks, view_statistics
except ImportError:
    view_essences = view_generated_tasks = view_statistics = None

from .synthesis_plugin import main as run_synthesis_plugin
from .init_synthesis_db import init_synthesis_database as init_database
from .generate_tasks import generate_tasks

__all__ = [
    'SimpleSynthesizer',
    'TaskEssence',
    'synthesis_api',
    'SynthesisTrigger',
    'view_essences',
    'view_generated_tasks',
    'view_statistics',
    'run_synthesis_plugin',
    'init_database',
    'generate_tasks'
] 