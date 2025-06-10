"""
Deep Research module for Reasoning Runtime
基于 Gemini DeepResearch 的智能搜索研究模块

这个模块将原始的 Gemini DeepResearch 功能完整集成到 Reasoning Runtime 中，
提供智能的多轮网络搜索和研究能力。

主要功能:
- 🔍 智能查询生成
- 🌐 并行网络搜索
- 🤔 反思式评估
- 📊 迭代优化研究
- 📝 综合报告生成

使用示例:
    from deep_research import create_research_graph, quick_research
    
    # 快速研究
    result = await quick_research("人工智能的发展趋势")
    
    # 自定义配置
    graph = create_research_graph({"max_research_loops": 5})
    result = await graph.ainvoke({"messages": [{"type": "human", "content": "查询"}]})
"""

# 核心组件
from .graph import create_research_graph, DeepResearchGraph, quick_research
from .state import (
    OverallState,
    QueryGenerationState,
    ReflectionState,
    WebSearchState,
    ResearchConfiguration
)
from .nodes import (
    generate_query,
    web_research,
    reflection,
    finalize_answer,
    continue_to_web_research,
    evaluate_research
)

# 工具和配置
from .config import (
    DeepResearchConfig,
    ConfigTemplates,
    load_config,
    default_config
)
from .utils import (
    get_citations,
    get_research_topic,
    insert_citation_markers,
    resolve_urls,
    get_current_date,
    CitationManager
)

# 提示词管理
from .prompts import (
    get_query_generation_prompt,
    get_web_search_prompt,
    get_reflection_prompt,
    get_answer_prompt,
    PromptManager
)

# 版本信息
__version__ = "1.0.0"
__author__ = "Agent Data Platform Team"
__description__ = "Gemini DeepResearch integration for Reasoning Runtime"

# 公开接口
__all__ = [
    # 核心类和函数
    'create_research_graph',
    'DeepResearchGraph',
    'quick_research',
    
    # 状态类
    'OverallState',
    'QueryGenerationState',
    'ReflectionState',
    'WebSearchState',
    'ResearchConfiguration',
    
    # 节点函数
    'generate_query',
    'web_research',
    'reflection',
    'finalize_answer',
    'continue_to_web_research',
    'evaluate_research',
    
    # 配置管理
    'DeepResearchConfig',
    'ConfigTemplates',
    'load_config',
    'default_config',
    
    # 工具函数
    'get_citations',
    'get_research_topic',
    'insert_citation_markers',
    'resolve_urls',
    'get_current_date',
    'CitationManager',
    
    # 提示词管理
    'get_query_generation_prompt',
    'get_web_search_prompt',
    'get_reflection_prompt',
    'get_answer_prompt',
    'PromptManager',
    
    # 元信息
    '__version__',
    '__author__',
    '__description__'
]

# 模块级别的便捷函数
def get_version_info():
    """获取模块版本信息"""
    return {
        "version": __version__,
        "author": __author__,
        "description": __description__,
        "components": len(__all__)
    }

def get_capabilities():
    """获取模块能力描述"""
    return {
        "name": "deep_research",
        "version": __version__,
        "description": "智能深度研究模块",
        "features": [
            "多角度查询生成",
            "并行网络搜索",
            "智能反思评估",
            "迭代研究优化",
            "结构化报告生成"
        ],
        "supported_models": [
            "gemini-2.0-flash-exp",
            "gemini-1.5-pro",
            "gemini-1.5-flash"
        ],
        "configuration_templates": [
            "development",
            "production",
            "high_quality",
            "fast"
        ]
    }

# 模块初始化检查
def _check_environment():
    """检查环境依赖"""
    import os
    import warnings
    
    if not os.getenv("GEMINI_API_KEY"):
        warnings.warn(
            "GEMINI_API_KEY 环境变量未设置，深度研究功能可能无法正常工作",
            UserWarning
        )

# 执行环境检查
_check_environment()