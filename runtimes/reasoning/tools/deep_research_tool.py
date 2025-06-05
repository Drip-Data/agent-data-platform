"""
Deep Research Tool for Reasoning Runtime
深度研究工具 - 将 Gemini DeepResearch 功能集成到 reasoning runtime
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Union
from ..deep_research.graph import create_research_graph, DeepResearchGraph
from ..deep_research.state import ResearchConfiguration
from ..deep_research.utils import truncate_text

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
                "error_type": "DEEP_RESEARCH_ERROR",                "final_answer": f"深度研究过程中发生错误: {str(e)}",
                "messages": [{"type": "ai", "content": f"研究失败: {str(e)}"}],
                "sources_gathered": [],
                "web_research_result": [],
                "search_query": []
            }
    
    def _process_result(self, raw_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理原始研究结果，提取关键信息并确保JSON可序列化
        
        Args:
            raw_result: LangGraph 返回的原始结果
            
        Returns:
            处理后的结果字典（JSON可序列化）        """
        try:
            # 处理messages，确保JSON可序列化
            messages = raw_result.get("messages", [])
            processed_messages = self._process_messages(messages)
            
            # 增强的 final_answer 提取逻辑
            final_answer = self._extract_final_answer(raw_result, processed_messages)
            
            # 处理源文档（完整内容，无长度限制）
            sources_gathered = raw_result.get("sources_gathered", [])
            processed_sources = self._process_sources(sources_gathered)
            
            # 提取所有可序列化的原始数据
            raw_data = self._extract_serializable_data(raw_result)
            
            # 构建处理后的结果（完全JSON可序列化）
            processed_result = {
                "success": True,
                "final_answer": str(final_answer),
                "summary": truncate_text(str(final_answer), 300),
                "messages": processed_messages,
                "sources_gathered": processed_sources,
                "web_research_result": [
                    truncate_text(str(item), 500)
                    for item in raw_result.get("web_research_result", [])
                ],
                "search_query": raw_result.get("search_query", []),
                "research_loop_count": raw_result.get("research_loop_count", 0),
                
                # 添加 deep research 轨迹数据
                "deep_research_trace": raw_result.get("deep_research_trace"),
                
                # 保留原始数据以确保完整性
                "raw_data": raw_data,
                
                "metadata": {
                    "total_sources": len(processed_sources),
                    "total_queries": len(raw_result.get("search_query", [])),
                    "research_loops": raw_result.get("research_loop_count", 0),
                    "messages_processed": len(processed_messages),
                    "final_answer_length": len(final_answer),
                    "total_content_length": sum(len(str(s.get("content", ""))) for s in processed_sources),
                    "has_complete_data": bool(final_answer and processed_sources),
                    "has_trace_data": bool(raw_result.get("deep_research_trace"))
                }
            }
            
            return processed_result
            
        except Exception as e:
            logger.error(f"结果处理失败: {str(e)}")
            return self._create_error_result(str(e))

    def _process_messages(self, messages: list) -> list:
        """处理消息列表，确保JSON可序列化"""
        processed_messages = []
        
        for msg in messages:
            if isinstance(msg, dict):
                # 已经是字典，直接使用
                processed_messages.append({
                    "type": msg.get("type", "unknown"),
                    "content": str(msg.get("content", ""))
                })
            else:
                # LangChain消息对象，提取属性
                msg_type = self._extract_message_type(msg)
                msg_content = self._extract_message_content(msg)
                
                processed_messages.append({
                    "type": msg_type,
                    "content": msg_content
                })
        
        return processed_messages
    
    def _extract_message_type(self, msg) -> str:
        """提取消息类型"""
        if hasattr(msg, '__class__'):
            class_name = msg.__class__.__name__
            if 'Human' in class_name:
                return "human"
            elif 'AI' in class_name:
                return "ai"
            elif 'System' in class_name:
                return "system"
        return "unknown"
    
    def _extract_message_content(self, msg) -> str:
        """提取消息内容"""
        if hasattr(msg, 'content'):
            return str(msg.content)
        else:
            return str(msg)
    
    def _extract_final_answer(self, raw_result: Dict[str, Any], processed_messages: list) -> str:
        """增强的最终答案提取逻辑"""
        # 按优先级尝试从不同字段提取最终答案
        answer_fields = [
            "final_answer", 
            "final_report", 
            "conclusion", 
            "summary", 
            "answer", 
            "result",
            "response"
        ]
        
        for field in answer_fields:
            if raw_result.get(field):
                answer = str(raw_result[field]).strip()
                if answer:
                    return answer
        
        # 从处理后的消息中提取最后一条AI消息
        for msg in reversed(processed_messages):
            if msg.get("type") == "ai" and msg.get("content"):
                content = str(msg["content"]).strip()
                if content:
                    return content
        
        # 最后尝试从任何消息中提取
        if processed_messages:
            last_content = processed_messages[-1].get("content", "")
            if last_content:
                return str(last_content)
        
        return "未能提取到完整的研究结论"
    
    def _process_sources(self, sources_gathered: list) -> list:
        """处理源文档，保留完整内容"""
        processed_sources = []
        
        for source in sources_gathered:
            if isinstance(source, dict):
                processed_sources.append({
                    "title": source.get("title", "未知来源"),
                    "url": source.get("value", source.get("url", source.get("short_url", ""))),
                    "short_url": source.get("short_url", ""),
                    # Truncate long content to keep trajectory concise
                    "content": truncate_text(source.get("content", ""), 1000),
                    "snippet": source.get("snippet", ""),
                    "metadata": {
                        key: value for key, value in source.items()
                        if key not in ["title", "url", "value", "short_url", "content", "snippet"]
                        and isinstance(value, (str, int, float, bool))
                    }
                })
        
        return processed_sources
    
    def _extract_serializable_data(self, raw_result: Dict[str, Any]) -> Dict[str, Any]:
        """提取所有可JSON序列化的原始数据"""
        serializable_data = {}
        
        for key, value in raw_result.items():
            # 跳过已经处理的字段
            if key in ["messages", "sources_gathered"]:
                continue
                
            # 只保留可序列化的数据类型
            if isinstance(value, (str, int, float, bool, list, dict, type(None))):
                try:
                    # 测试是否可以序列化
                    import json
                    json.dumps(value)
                    serializable_data[key] = value
                except (TypeError, ValueError):
                    # 如果不能序列化，转为字符串
                    serializable_data[key] = str(value)
        
        return serializable_data
    
    def _create_error_result(self, error_message: str) -> Dict[str, Any]:
        """创建错误结果"""
        return {
            "success": False,
            "error": f"结果处理失败: {error_message}",
            "error_type": "RESULT_PROCESSING_ERROR",
            "final_answer": "结果处理过程中发生错误",
            "messages": [],
            "sources_gathered": [],
            "web_research_result": [],
            "search_query": [],
            "raw_data": {},
            "metadata": {
                "total_sources": 0,
                "total_queries": 0,
                "research_loops": 0,
                "messages_processed": 0,
                "final_answer_length": 0,
                "total_content_length": 0,
                "has_complete_data": False
            }
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