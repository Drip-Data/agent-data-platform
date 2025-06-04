"""
State definitions for Deep Research module
定义深度研究模块的状态管理
"""

from __future__ import annotations
import operator
from dataclasses import dataclass, field
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import add_messages
from typing_extensions import Annotated


class OverallState(TypedDict):
    """整体研究状态"""
    messages: Annotated[list, add_messages]
    search_query: Annotated[list, operator.add]
    web_research_result: Annotated[list, operator.add]
    sources_gathered: Annotated[list, operator.add]
    initial_search_query_count: int
    max_research_loops: int
    research_loop_count: int
    reasoning_model: str


class ReflectionState(TypedDict):
    """反思状态 - 用于评估研究充分性"""
    is_sufficient: bool
    knowledge_gap: str
    follow_up_queries: Annotated[list, operator.add]
    research_loop_count: int
    number_of_ran_queries: int


class Query(TypedDict):
    """单个查询定义"""
    query: str
    rationale: str


class QueryGenerationState(TypedDict):
    """查询生成状态"""
    query_list: List[Query]


class WebSearchState(TypedDict):
    """网络搜索状态"""
    search_query: str
    id: str


@dataclass(kw_only=True)
class SearchStateOutput:
    """搜索输出状态"""
    running_summary: str = field(default=None)  # Final report


class ResearchConfiguration:
    """研究配置类"""
    def __init__(self, 
                 initial_search_query_count: int = 3,
                 max_research_loops: int = 3,
                 reasoning_model: str = "gemini-2.0-flash-exp",
                 query_generator_model: str = "gemini-2.0-flash-exp"):
        self.initial_search_query_count = initial_search_query_count
        self.max_research_loops = max_research_loops
        self.reasoning_model = reasoning_model
        self.query_generator_model = query_generator_model
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'ResearchConfiguration':
        """从字典创建配置对象"""
        return cls(
            initial_search_query_count=config_dict.get('initial_search_query_count', 3),
            max_research_loops=config_dict.get('max_research_loops', 3),
            reasoning_model=config_dict.get('reasoning_model', "gemini-2.0-flash-exp"),
            query_generator_model=config_dict.get('query_generator_model', "gemini-2.0-flash-exp")
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'initial_search_query_count': self.initial_search_query_count,
            'max_research_loops': self.max_research_loops,
            'reasoning_model': self.reasoning_model,
            'query_generator_model': self.query_generator_model
        }