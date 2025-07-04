#!/usr/bin/env python3
"""
Synthesis Prompts 模块
专门管理所有 Synthesis 相关的 Prompt 模板
"""

from .base import PromptTemplate, PromptManager
from .task_generation import TaskGenerationPrompts
from .task_validation import TaskValidationPrompts
from .task_synthesis import TaskSynthesisPrompts

# 创建全局 Prompt 管理器实例
prompt_manager = PromptManager()

# 注册所有 Prompt 模板
prompt_manager.register_module('task_generation', TaskGenerationPrompts)
prompt_manager.register_module('task_validation', TaskValidationPrompts)
prompt_manager.register_module('task_synthesis', TaskSynthesisPrompts)

__all__ = [
    'PromptTemplate',
    'PromptManager',
    'TaskGenerationPrompts',
    'TaskValidationPrompts', 
    'TaskSynthesisPrompts',
    'prompt_manager'
]