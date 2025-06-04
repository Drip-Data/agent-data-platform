"""
Deep Research Tool for Reasoning Runtime
深度研究工具 - 将 Gemini DeepResearch 功能集成到 reasoning runtime
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Union
from ..deep_research.graph import create_research_graph, DeepResearchGraph
from ..deep_research.state import ResearchConfiguration

logger = logging.getLogger(__name__)


class DeepResearchTool:
    """
    深度研究工具类
    
    将完整的 LangGraph deep research 能力封装为工具，
    供 reasoning runtime 在任务流程中调用。
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化深度研究工具
        
        Args:
            config: 可选的研究配置字典
        """
        self.default_config = ResearchConfiguration.from_dict(config or {})
        self._research_graph: Optional[DeepResearchGraph] = None
        self._initialized = False
    
    def _ensure_initialized(self):
        """确保研究图已初始化"""
        if not self._initialized:
            try:
                self._research_graph = create_research_graph(self.default_config.to_dict())
                self._initialized = True
                logger.info("深度研究工具初始化完成")
            except Exception as e:
                logger.error(f"深度研究工具初始化失败: {str(e)}")
                raise
    
    async def execute(self, query: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行深度研究，返回完整的研究结果字典
        
        Args:
            query: 用户的初始研究问题
            config: 可选的研究配置，包含：
                - initial_search_query_count: 初始搜索查询数量（默认3）
                - max_research_loops: 最大研究循环次数（默认3）
                - reasoning_model: 推理模型名称（默认gemini-2.0-flash-exp）
                - query_generator_model: 查询生成模型名称（默认gemini-2.0-flash-exp）
                
        Returns:
            包含研究结果的字典，主要字段：
            - messages: 包含最终答案的消息列表
            - final_answer: 最终研究答案文本
            - sources_gathered: 收集到的信息源列表
            - web_research_result: 网络研究结果列表
            - search_query: 使用的搜索查询列表
        """
        try:
            # 确保工具已初始化
            self._ensure_initialized()
            
            # 验证输入
            if not query or not isinstance(query, str):
                raise ValueError("查询参数必须是非空字符串")
            
            # 合并配置
            merged_config = self.default_config.to_dict()
            if config:
                merged_config.update(config)
            
            # 准备输入数据
            payload = {
                "messages": [{"type": "human", "content": query.strip()}]
            }
            
            logger.info(f"开始执行深度研究 - 查询: {query[:100]}...")
            
            # 执行研究
            result = await self._research_graph.ainvoke(payload, merged_config)
            
            # 处理结果
            processed_result = self._process_result(result)
            
            logger.info(f"深度研究完成 - 答案长度: {len(processed_result.get('final_answer', ''))} 字符")
            
            return processed_result
            
        except Exception as e:
            logger.error(f"深度研究执行失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "error_type": "DEEP_RESEARCH_ERROR",
                "final_answer": f"深度研究过程中发生错误: {str(e)}",
                "messages": [{"type": "ai", "content": f"研究失败: {str(e)}"}],
                "sources_gathered": [],
                "web_research_result": [],
                "search_query": []
            }
    
    def _process_result(self, raw_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理原始研究结果，提取关键信息
        
        Args:
            raw_result: LangGraph 返回的原始结果
            
        Returns:
            处理后的结果字典
        """
        try:
            # 提取最终答案
            final_answer = ""
            messages = raw_result.get("messages", [])
            
            if messages:
                # 获取最后一条消息作为最终答案
                last_message = messages[-1]
                if isinstance(last_message, dict):
                    final_answer = last_message.get("content", "")
                else:
                    final_answer = getattr(last_message, "content", "")
            
            # 如果没有从messages中获取到答案，尝试直接获取
            if not final_answer:
                final_answer = raw_result.get("final_answer", "")
            
            # 处理源文档
            sources_gathered = raw_result.get("sources_gathered", [])
            processed_sources = []
            
            for source in sources_gathered:
                if isinstance(source, dict):
                    processed_sources.append({
                        "title": source.get("title", "未知来源"),
                        "url": source.get("value", source.get("short_url", "")),
                        "short_url": source.get("short_url", "")
                    })
            
            # 构建处理后的结果
            processed_result = {
                "success": True,
                "final_answer": final_answer,
                "messages": messages,
                "sources_gathered": processed_sources,
                "web_research_result": raw_result.get("web_research_result", []),
                "search_query": raw_result.get("search_query", []),
                "research_loop_count": raw_result.get("research_loop_count", 0),
                "metadata": {
                    "total_sources": len(processed_sources),
                    "total_queries": len(raw_result.get("search_query", [])),
                    "research_loops": raw_result.get("research_loop_count", 0)
                }
            }
            
            return processed_result
            
        except Exception as e:
            logger.error(f"结果处理失败: {str(e)}")
            return {
                "success": False,
                "error": f"结果处理失败: {str(e)}",
                "final_answer": "结果处理过程中发生错误",
                "messages": [],
                "sources_gathered": [],
                "web_research_result": [],
                "search_query": []
            }
    
    def execute_sync(self, query: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        同步执行深度研究（内部使用异步实现）
        
        Args:
            query: 研究查询
            config: 可选配置
            
        Returns:
            研究结果字典
        """
        try:
            # 检查是否在事件循环中
            loop = asyncio.get_running_loop()
            if loop.is_running():
                # 在现有循环中运行
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.execute(query, config))
                    return future.result()
            else:
                return asyncio.run(self.execute(query, config))
        except RuntimeError:
            # 没有事件循环
            return asyncio.run(self.execute(query, config))
    
    def get_capabilities(self) -> Dict[str, Any]:
        """获取工具能力描述"""
        return {
            "name": "deep_research",
            "description": "执行深度网络研究，生成全面的研究报告",
            "parameters": {
                "query": "研究主题或问题",
                "config": {
                    "initial_search_query_count": "初始搜索查询数量（1-10，默认3）",
                    "max_research_loops": "最大研究循环次数（1-10，默认3）",
                    "reasoning_model": "推理模型名称（默认gemini-2.0-flash-exp）",
                    "query_generator_model": "查询生成模型名称（默认gemini-2.0-flash-exp）"
                }
            },
            "outputs": {
                "final_answer": "最终研究答案",
                "sources_gathered": "信息源列表",
                "web_research_result": "网络研究结果",
                "search_query": "使用的搜索查询"
            }
        }
    
    def cleanup(self):
        """清理资源"""
        if self._research_graph:
            self._research_graph = None
        self._initialized = False
        logger.info("深度研究工具资源已清理")


# 全局单例工具实例
deep_research_tool = DeepResearchTool()