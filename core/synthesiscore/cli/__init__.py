"""
Synthesis CLI Package
命令行工具入口点
"""

from .trigger import main as trigger_main
from .view import main as view_main
from .init_db import main as init_db_main
from .generate import main as generate_main

__all__ = ['trigger_main', 'view_main', 'init_db_main', 'generate_main'] 