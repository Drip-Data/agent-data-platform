"""
LangGraph implementation for Deep Research
深度研究的 LangGraph 实现
"""

import os
import logging
import time
from typing import Dict, Any, Optional

from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig

from .state import OverallState, ResearchConfiguration
from .tracker import ResearchTracker, create_tracker
from .utils import get_research_topic
from .nodes import (
    generate_query,
    continue_to_web_research,
    web_research,
    reflection,
    evaluate_research,
    finalize_answer
)

logger = logging.getLogger(__name__)


class DeepResearchGraph:
    """深度研究图类"""
    
    def __init__(self, config: Optional[ResearchConfiguration] = None):
        """
        初始化深度研究图
        
        Args:
            config: 研究配置，如果为None则使用默认配置
        """
        self.config = config or ResearchConfiguration()
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """构建 LangGraph"""
        # 创建状态图
        builder = StateGraph(OverallState)
        
        # 添加节点
        builder.add_node("generate_query", self._wrap_node(generate_query))
        builder.add_node("web_research", self._wrap_node(web_research))
        builder.add_node("reflection", self._wrap_node(reflection))
        builder.add_node("finalize_answer", self._wrap_node(finalize_answer))
        
        # 设置入口点
        builder.add_edge(START, "generate_query")
        
        # 添加条件边 - 从查询生成到网络研究
        builder.add_conditional_edges(
            "generate_query", 
            continue_to_web_research, 
            ["web_research"]
        )
        
        # 从网络研究到反思
        builder.add_edge("web_research", "reflection")
        
        # 添加条件边 - 评估是否继续研究
        builder.add_conditional_edges(
            "reflection", 
            self._wrap_router(evaluate_research), 
            ["web_research", "finalize_answer"]
        )
        
        # 结束边
        builder.add_edge("finalize_answer", END)
        
        # 编译图
        return builder.compile(name="deep-research-agent")
    
    def _wrap_node(self, node_func):
        """包装节点函数以传递配置"""
        async def wrapped_node(state, config=None):
            # 将研究配置传递给节点
            merged_config = self.config.to_dict()
            if config:
                merged_config.update(config)
            return await node_func(state, merged_config)
        
        return wrapped_node
    
    def _wrap_router(self, router_func):
        """包装路由函数以传递配置"""
        def wrapped_router(state, config=None):
            # 将研究配置传递给路由器
            merged_config = self.config.to_dict()
            if config:
                merged_config.update(config)
            return router_func(state, merged_config)
        
        return wrapped_router
    
    async def ainvoke(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        异步调用图执行
        
        Args:
            input_data: 输入数据，应包含 'messages' 字段
            config: 运行时配置
            
        Returns:
            图执行结果
        """
        try:
            # 验证输入
            if "messages" not in input_data:
                raise ValueError("输入数据必须包含 'messages' 字段")
            
            # 合并配置
            run_config = self.config.to_dict()
            if config:
                run_config.update(config)
            
            # 创建研究轨迹记录器
            research_topic = get_research_topic(input_data["messages"])
            tracker = create_tracker(research_topic)
            tracker.set_config(run_config)
            
            # 准备初始状态
            initial_state = {
                "messages": input_data["messages"],
                "search_query": [],
                "web_research_result": [],
                "sources_gathered": [],
                "initial_search_query_count": run_config.get("initial_search_query_count", 3),
                "max_research_loops": run_config.get("max_research_loops", 2),
                "max_total_queries": run_config.get("max_total_queries", 9),
                "research_loop_count": 0,
                "reasoning_model": run_config.get("reasoning_model", "gemini-2.0-flash-exp"),
                "research_tracker": tracker,
                "start_time": time.time(),
                "loop_start_time": time.time()  # 记录循环开始时间
            }
            
            # 添加额外的输入数据
            for key, value in input_data.items():
                if key not in initial_state:
                    initial_state[key] = value
            
            logger.info(f"开始深度研究 - 初始查询数: {initial_state['initial_search_query_count']}, 最大循环: {initial_state['max_research_loops']}")
            
            # 执行图
            result = await self.graph.ainvoke(initial_state, config=run_config)
            
            # 获取轨迹数据（不写入文件，交由 runtime.py 统一处理）
            if run_config.get("enable_research_tracking", True):
                tracker.log_progress()
                trace_data = tracker.get_trace_data()  # 获取轨迹数据而不写入文件
                result["deep_research_trace"] = trace_data  # 添加到返回结果中
                result["trace_summary"] = tracker.get_trace_summary()
            
            logger.info("深度研究完成")
            return result
            
        except Exception as e:
            logger.error(f"深度研究执行失败: {str(e)}")
            
            # 记录错误轨迹（但不保存文件，交由上层处理）
            if run_config.get("enable_research_tracking", True):
                tracker.record_error(str(e))
                # 不在这里保存文件，由 runtime.py 统一处理
            
            raise
    
    def invoke(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        同步调用图执行（内部使用异步实现）
        
        Args:
            input_data: 输入数据
            config: 运行时配置
            
        Returns:
            图执行结果
        """
        import asyncio
        
        # 检查是否在事件循环中
        try:
            loop = asyncio.get_running_loop()
            # 如果已经在事件循环中，创建新的任务
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.ainvoke(input_data, config))
                    return future.result()
            else:
                return asyncio.run(self.ainvoke(input_data, config))
        except RuntimeError:
            # 没有事件循环，直接运行
            return asyncio.run(self.ainvoke(input_data, config))
    
    def get_graph_structure(self) -> Dict[str, Any]:
        """获取图结构信息"""
        return {
            "nodes": ["generate_query", "web_research", "reflection", "finalize_answer"],
            "edges": [
                {"from": "START", "to": "generate_query"},
                {"from": "generate_query", "to": "web_research", "type": "conditional"},
                {"from": "web_research", "to": "reflection"},
                {"from": "reflection", "to": ["web_research", "finalize_answer"], "type": "conditional"},
                {"from": "finalize_answer", "to": "END"}
            ],
            "config": self.config.to_dict()
        }


def create_research_graph(config: Optional[Dict[str, Any]] = None) -> DeepResearchGraph:
    """
    创建深度研究图实例
    
    Args:
        config: 配置字典
        
    Returns:
        深度研究图实例
    """
    # 验证环境变量
    if not os.getenv("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY 环境变量未设置")
    
    # 创建配置
    research_config = None
    if config:
        research_config = ResearchConfiguration.from_dict(config)
    
    # 创建并返回图实例
    graph = DeepResearchGraph(research_config)
    
    logger.info("深度研究图创建完成")
    return graph


# 便捷函数，用于快速创建和使用
async def quick_research(query: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    快速执行深度研究
    
    Args:
        query: 研究查询
        config: 可选配置
        
    Returns:
        研究结果
    """
    graph = create_research_graph(config)
    
    input_data = {
        "messages": [{"type": "human", "content": query}]
    }
    
    return await graph.ainvoke(input_data)


# 用于测试的示例函数
async def test_research_graph():
    """测试研究图功能"""
    try:
        # 创建测试配置
        test_config = {
            "initial_search_query_count": 2,
            "max_research_loops": 2,
            "reasoning_model": "gemini-2.0-flash-exp"
        }
        
        # 执行测试查询
        result = await quick_research("什么是人工智能的最新发展趋势？", test_config)
        
        print("测试完成！")
        print(f"最终答案: {result.get('final_answer', '未生成答案')}")
        print(f"使用源数量: {len(result.get('sources_gathered', []))}")
        
        return result
        
    except Exception as e:
        print(f"测试失败: {str(e)}")
        return None


if __name__ == "__main__":
    # 运行测试
    import asyncio
    asyncio.run(test_research_graph())