#!/usr/bin/env python3
"""
SynthesisCore v2.0 - 增强任务合成模块
基于TaskCraft算法的完整任务生成和验证系统

主要功能:
- 原子任务生成 (Atomic Task Generation)
- 深度优先扩展 (Depth-based Extension) 
- 宽度优先扩展 (Width-based Extension)
- 多维度质量验证 (Multi-dimensional Verification)
- 自适应提示词管理 (Adaptive Prompt Management)
- Redis队列管理 (Redis Queue Management)
"""

__version__ = "2.0.0"
__author__ = "TaskCraft Enhanced Team"

# 保持向后兼容
from .synthesis import SynthesisService, TaskEssence

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

# === SynthesisCore v2.0 Enhanced Components ===

# 核心数据结构
from .enhanced_interfaces import (
    # 基础数据类型
    TaskDifficulty,
    TaskType,
    ContentType,
    
    # 语料和任务数据结构
    CorpusContent,
    TaskConclusion,
    AtomicTask,
    SupersetInfo,
    ExtendedTask,
    CompositeTask,
    
    # 验证和指标
    VerificationResult,
    GenerationMetrics,
    PromptTemplate,
    FewShotExample,
    
    # 类型别名
    TaskUnion,
    ProcessingResult,
    QualityMetrics,
    
    # 配置和工具函数
    EnhancedSynthesisConfig,
    generate_task_id,
    calculate_complexity_score,
    get_task_difficulty_from_score
)

# 语料处理
from .corpus_ingestor import (
    TrajectoryCorpusExtractor,
    ExternalCorpusLoader,
    ContentProcessor,
    CorpusIngestor
)

# 原子任务生成
from .atomic_task_generator import (
    ConclusionExtractor,
    QuestionGenerator,
    AtomicityVerifier,
    AtomicTaskGenerator
)

# 深度扩展
from .depth_extender import (
    SupersetSearcher,
    IntermediateTaskGenerator,
    TaskMerger,
    DepthExtender
)

# 宽度扩展
from .width_extender import (
    SemanticGrouper,
    TaskFuser,
    DecompositionValidator,
    WidthExtender
)

# 验证系统
from .verification_agent import (
    TaskExecutor,
    AtomicityVerifier as VerificationAtomicityVerifier,
    QualityAssessor,
    EnhancedVerificationEngine
)

# Redis管理
from .enhanced_redis_manager import (
    EnhancedRedisManager,
    CorpusQueueManager,
    TaskQueueManager,
    VerificationQueueManager,
    MetricsManager,
    PromptVersionManager,
    EnhancedSynthesisRedisManager
)

# 核心引擎
from .enhanced_synthesis_engine import (
    EnhancedSynthesisEngine,
    SynthesisCoreV2
)

# 导出主要接口
__all__ = [
    # === 向后兼容 ===
    'SynthesisService',
    'TaskEssence',
    'synthesis_api',
    'SynthesisManager',
    
    # === 核心接口 ===
    "SynthesisCoreV2",
    "EnhancedSynthesisEngine",
    
    # === 数据结构 ===
    "TaskDifficulty",
    "TaskType", 
    "ContentType",
    "CorpusContent",
    "AtomicTask",
    "ExtendedTask",
    "CompositeTask",
    "VerificationResult",
    "GenerationMetrics",
    "TaskUnion",
    "EnhancedSynthesisConfig",
    
    # === 核心组件 ===
    "CorpusIngestor",
    "AtomicTaskGenerator",
    "DepthExtender", 
    "WidthExtender",
    "EnhancedVerificationEngine",
    "EnhancedSynthesisRedisManager",
    
    # === 工具函数 ===
    "generate_task_id",
    "calculate_complexity_score",
    "get_task_difficulty_from_score",
]

# 版本信息
VERSION_INFO = {
    "version": __version__,
    "features": {
        "atomic_generation": True,
        "depth_extension": True,
        "width_extension": True, 
        "adaptive_prompts": True,
        "quality_verification": True,
        "redis_queues": True,
        "metrics_tracking": True
    },
    "algorithms": {
        "taskcraft_atomic": "结论提取 + 问题生成 + 原子性验证",
        "taskcraft_depth": "超集搜索 + 中间任务生成 + 任务合并",
        "taskcraft_width": "语义分组 + 任务融合 + 分解验证"
    },
    "compatibility": {
        "min_python_version": "3.8",
        "required_dependencies": ["asyncio", "redis", "dataclasses", "typing"],
        "optional_dependencies": ["numpy", "scikit-learn"]
    }
}


def get_version_info():
    """获取版本信息"""
    return VERSION_INFO


def get_default_config():
    """获取默认配置"""
    return EnhancedSynthesisConfig()


# 快速开始示例
QUICK_START_EXAMPLE = """
# SynthesisCore v2.0 快速开始示例

from core.llm_client import LLMClient
from core.toolscore.mcp_client import MCPToolClient
from core.synthesiscore import SynthesisCoreV2

async def quick_start():
    # 1. 初始化客户端
    llm_client = LLMClient()
    mcp_client = MCPToolClient()
    
    # 2. 创建SynthesisCore v2.0实例
    synthesis_core = SynthesisCoreV2(
        llm_client=llm_client,
        mcp_client=mcp_client,
        redis_url="redis://localhost:6379"
    )
    
    # 3. 初始化
    await synthesis_core.initialize()
    
    try:
        # 4. 从轨迹合成任务
        result = await synthesis_core.synthesize_tasks(
            trajectories=your_trajectories,
            mode="full",  # full/atomic_only/depth_only/width_only
            verify_quality=True
        )
        
        # 5. 获取结果
        atomic_tasks = result["atomic_tasks"]
        extended_tasks = result["extended_tasks"] 
        composite_tasks = result["composite_tasks"]
        verification_results = result["verification_results"]
        
        print(f"生成任务: 原子 {len(atomic_tasks)}, 深度扩展 {len(extended_tasks)}, 宽度扩展 {len(composite_tasks)}")
        
        # 6. 获取指标
        metrics = await synthesis_core.get_metrics("session")
        print(f"生成效率: {metrics['generation_efficiency']:.2f}")
        
    finally:
        # 7. 关闭
        await synthesis_core.close()
"""


def print_quick_start():
    """打印快速开始示例"""
    print(QUICK_START_EXAMPLE)


# 模块初始化日志
import logging
logger = logging.getLogger(__name__)
logger.info(f"✅ SynthesisCore v{__version__} 模块加载完成")
logger.info(f"🔧 支持功能: {', '.join(f for f, enabled in VERSION_INFO['features'].items() if enabled)}")