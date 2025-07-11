#!/usr/bin/env python3
"""
TaskCraft Synthesis Core - 统一任务合成模块
严格实现 TaskCraft 算法的单一、清晰架构

核心功能：
1. 原子任务生成：iT → C → (a, R) → q
2. 深度扩展：超集搜索 + 中间任务生成
3. 宽度扩展：多任务合并
4. 智能验证：区分工具任务 vs 推理任务
5. 分类存储：工具任务和推理任务分开存储
"""

__version__ = "3.0.0"
__author__ = "Synthesis Team"
__description__ = "Synthesis Algorithm Implementation - Unified & Simplified"

# === 核心引擎 ===
from .synthesis_engine import SynthesisEngine

# === 数据结构 ===
from .interfaces import (
    # 核心数据类型
    TaskType,
    TaskComplexity,
    
    # Synthesis 核心要素
    SynthesisInput,
    SynthesisContent,
    SynthesisAnswer,
    SynthesisRelation,
    
    # 任务类型
    AtomicTask,
    DepthExtendedTask,
    WidthExtendedTask,
    TaskUnion,
    
    # 验证和结果
    TaskValidationResult,
    SynthesisResult,
    
    # 工具函数
    generate_task_id,
    get_task_type_from_complexity
)

# === 核心组件 ===
# from .atomic_task_generator import AtomicTaskGenerator  # 暂时注释，直接在引擎中实现
# from .depth_extender import DepthExtender  # 暂时注释，直接在引擎中实现  
# from .width_extender import WidthExtender  # 暂时注释，直接在引擎中实现
from .task_validator import TaskValidator
from .task_storage import TaskStorage

# === 支持组件 ===
# from .corpus_ingestor import CorpusIngestor  # 暂时注释，有类型依赖问题
from .trajectory_monitor import SimpleTrajectoryMonitor as TrajectoryMonitor

# === API接口 ===
try:
    from .synthesis_api import app as synthesis_api
except ImportError:
    synthesis_api = None

# === 向后兼容（废弃） ===
try:
    from .synthesis_legacy import SynthesisService
except ImportError:
    SynthesisService = None

# === 主要导出接口 ===
__all__ = [
    # === 核心引擎 ===
    "TaskCraftSynthesisEngine",
    
    # === 数据类型 ===
    "TaskType",
    "TaskComplexity",
    "SynthesisInput",
    "SynthesisContent", 
    "SynthesisAnswer",
    "SynthesisRelation",
    "AtomicTask",
    "DepthExtendedTask",
    "WidthExtendedTask",
    "TaskUnion",
    "TaskValidationResult",
    "SynthesisResult",
    
    # === 核心组件 ===
    # "AtomicTaskGenerator",  # 暂时注释，集成在引擎中
    # "DepthExtender",  # 暂时注释，集成在引擎中
    # "WidthExtender",  # 暂时注释，集成在引擎中
    "TaskValidator",
    "TaskStorage",
    
    # === 支持组件 ===
    # "CorpusIngestor",  # 暂时注释，有依赖问题
    "TrajectoryMonitor",
    
    # === API ===
    "synthesis_api",
    
    # === 工具函数 ===
    "generate_task_id",
    "get_task_type_from_complexity",
    
    # === 向后兼容 ===
    "SynthesisService",
]


def get_version() -> str:
    """获取版本信息"""
    return __version__


def get_capabilities() -> dict:
    """获取功能特性"""
    return {
        "version": __version__,
        "algorithm": "TaskCraft",
        "architecture": "unified_single_implementation",
        "features": {
            "atomic_task_generation": True,
            "depth_extension": True,
            "width_extension": True,
            "intelligent_validation": True,
            "tool_vs_reasoning_classification": True,
            "simplified_storage": True,
            "trajectory_monitoring": True,
            "http_api": synthesis_api is not None
        },
        "task_flow": [
            "1. 原子任务生成：从轨迹提取 iT → C → (a, R) → q",
            "2. 深度扩展：超集搜索 + 中间任务生成",
            "3. 宽度扩展：多任务并行合并",
            "4. 智能验证：区分工具任务 vs 推理任务",
            "5. 分类存储：按任务类型和复杂度分别存储"
        ],
        "storage_structure": {
            "tool_tasks": [
                "tool_atomic_tasks.jsonl",
                "tool_depth_extended_tasks.jsonl", 
                "tool_width_extended_tasks.jsonl"
            ],
            "reasoning_tasks": [
                "reasoning_atomic_tasks.jsonl",
                "reasoning_depth_extended_tasks.jsonl",
                "reasoning_width_extended_tasks.jsonl"
            ],
            "metadata": [
                "validation_results.jsonl",
                "synthesis_sessions.jsonl",
                "task_statistics.json"
            ]
        }
    }


def create_synthesis_engine(llm_client, mcp_client=None, **kwargs) -> SynthesisEngine:
    """
    创建 Synthesis 合成引擎的便捷方法
    
    Args:
        llm_client: LLM客户端
        mcp_client: MCP客户端（可选）
        **kwargs: 其他配置参数
    
    Returns:
        SynthesisEngine: 配置好的合成引擎
    """
    return SynthesisEngine(
        llm_client=llm_client,
        mcp_client=mcp_client,
        **kwargs
    )


# === 快速开始示例 ===
QUICK_START_EXAMPLE = '''
# TaskCraft Synthesis Core 快速开始

from core.synthesiscore import SynthesisEngine, create_synthesis_engine
from core.llm_client import LLMClient

async def example_usage():
    # 1. 创建LLM客户端
    llm_client = LLMClient(config={'provider': 'gemini'})
    
    # 2. 创建合成引擎
    engine = create_synthesis_engine(
        llm_client=llm_client,
        storage_dir="output",
        enable_strict_validation=True
    )
    
    # 3. 准备轨迹数据
    trajectories = [
        {
            "task_id": "example_1",
            "task_description": "查询今天的天气信息",
            "steps": [...],
            "success": True
        }
    ]
    
    # 4. 执行Synthesis合成
    result = await engine.synthesize_from_trajectories(
        trajectories_data=trajectories,
        generate_depth_extensions=True,
        generate_width_extensions=True,
        max_atomic_tasks=10
    )
    
    # 5. 查看结果
    print(f"生成任务统计:")
    print(f"  原子任务: {len(result.atomic_tasks)}")
    print(f"  深度扩展: {len(result.depth_extended_tasks)}")
    print(f"  宽度扩展: {len(result.width_extended_tasks)}")
    print(f"  有效任务: {result.valid_tasks_count}/{result.total_tasks_generated}")
    print(f"  工具任务: {result.tool_required_count}")
    print(f"  推理任务: {result.reasoning_only_count}")

# 运行示例
# asyncio.run(example_usage())
'''


def print_quick_start():
    """打印快速开始示例"""
    print(QUICK_START_EXAMPLE)


def print_architecture_info():
    """打印架构信息"""
    print(f"""
=== Synthesis Core v{__version__} ===

🎯 核心设计理念：
- 单一实现：清理了三套混乱架构，只保留Synthesis标准实现
- 严格验证：精准区分工具任务 vs 推理任务
- 简化存储：原子任务和综合任务两个文件
- 完整流程：原子生成 → 深度扩展 → 宽度扩展 → 智能验证

🏗️ 架构组成：
├── SynthesisEngine             # 统一合成引擎（主入口）
├── AtomicTaskGenerator         # 原子任务生成：iT → C → (a,R) → q
├── DepthExtender              # 深度扩展：超集搜索 + 中间任务
├── WidthExtender              # 宽度扩展：多任务合并
├── TaskValidator              # 智能验证：工具 vs 推理
└── TaskStorage                # 简化存储：2个文件类型

📁 存储结构：
- 原子任务：atomic_tasks.jsonl
- 综合任务：composite_tasks.jsonl
- 验证结果：validation_results.jsonl
- 会话记录：synthesis_sessions.jsonl
- 统计信息：task_statistics.json

🚀 使用方式：
engine = create_synthesis_engine(llm_client)
result = await engine.synthesize_from_trajectories(trajectories)
""")


# 模块初始化日志
import logging
logger = logging.getLogger(__name__)
logger.info(f"✅ Synthesis Core v{__version__} 加载完成")
logger.info(f"🎯 架构: 统一实现 | 功能: 原子生成+深度扩展+宽度扩展+智能验证")


# === 向后兼容的TaskCraft名称 ===
# 为了保持向后兼容性，保留旧的TaskCraft命名别名
TaskCraftSynthesisEngine = SynthesisEngine
TaskCraftInput = SynthesisInput
TaskCraftContent = SynthesisContent
TaskCraftAnswer = SynthesisAnswer
TaskCraftRelation = SynthesisRelation