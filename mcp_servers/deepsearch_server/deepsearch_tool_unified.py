#!/usr/bin/env python3
"""
Deepsearch Tool - Professional Research Agent (Unified LLM Client Version)
基于统一LLM客户端的专业级深度搜索工具，与系统架构一致
"""

import os
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

from core.llm_client import LLMClient
from .intelligent_cache import get_cache_instance, IntelligentCache
from .request_optimizer import OptimizedSearchMixin

logger = logging.getLogger(__name__)

class DeepSearchToolUnified(OptimizedSearchMixin):
    """专业级深度搜索工具，使用统一LLM客户端"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化深度搜索工具"""
        # 使用系统统一的LLM配置
        self.config = config or {}
        
        # 初始化统一LLM客户端
        try:
            self.llm_client = LLMClient(self.config)
            logger.info("DeepSearch tool initialized with unified LLM client")
        except Exception as e:
            logger.error(f"Failed to initialize LLM client: {e}")
            raise
        
        # 初始化智能缓存
        self.cache = get_cache_instance()
        self.cache_enabled = self.config.get("cache_enabled", True)
        self.cache_similarity_threshold = self.config.get("cache_similarity_threshold", 0.7)
        
        # 初始化优化mixin
        super().__init__()
        self._init_request_optimizer()
    
    def _extract_json_from_markdown(self, text: str) -> str:
        """从markdown格式的文本中提取JSON内容"""
        import re
        
        # 尝试匹配 ```json ... ``` 格式
        json_match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
        if json_match:
            return json_match.group(1).strip()
        
        # 尝试匹配 ``` ... ``` 格式（无json标识）
        json_match = re.search(r'```\s*\n(\{.*?\})\s*\n```', text, re.DOTALL)
        if json_match:
            return json_match.group(1).strip()
        
        # 尝试直接匹配JSON对象
        json_match = re.search(r'(\{.*\})', text, re.DOTALL)
        if json_match:
            return json_match.group(1).strip()
        
        # 如果都没找到，返回原文本（会导致JSON解析失败，由上层处理）
        return text
    
    async def research(self, question: str, **kwargs) -> Dict[str, Any]:
        """
        执行深度研究任务
        
        Args:
            question: 研究问题
            **kwargs: 可选参数
                - research_depth: "quick"|"standard"|"comprehensive"
                - max_iterations: 最大迭代次数
                
        Returns:
            Dict containing:
                - success: bool
                - output: research results
                - error_message: error message if failed
                - error_type: error type if failed
        """
        try:
            start_time = time.time()
            logger.info(f"Starting deep research for question: {question}")
            
            # 解析参数
            research_depth = kwargs.get("research_depth", "standard")
            max_iterations = kwargs.get("max_iterations", 2)
            
            # 检查缓存
            if self.cache_enabled:
                cached_result = await self.cache.get_cached_result(
                    question, 
                    research_depth, 
                    self.cache_similarity_threshold
                )
                if cached_result:
                    logger.info(f"Returning cached result for: {question[:50]}...")
                    return cached_result
            
            # 步骤1: 生成搜索查询
            queries = await self._generate_search_queries(question, research_depth)
            logger.info(f"Generated {len(queries)} search queries")
            
            # 步骤2: 并行执行搜索（性能优化）
            search_results = []
            sources = []
            
            # 并行执行所有搜索任务
            search_tasks = []
            for i, query in enumerate(queries):
                logger.info(f"Creating search task {i+1}/{len(queries)}: {query}")
                task = self._execute_search(query)
                search_tasks.append(task)
            
            # 并行等待所有搜索完成
            logger.info(f"Executing {len(search_tasks)} searches in parallel...")
            parallel_start = time.time()
            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            parallel_time = time.time() - parallel_start
            logger.info(f"Parallel search completed in {parallel_time:.2f}s")
            
            # 处理搜索结果和异常
            valid_results = []
            for i, result in enumerate(search_results):
                if isinstance(result, Exception):
                    logger.error(f"Search {i+1} failed: {result}")
                    # 创建失败结果的占位符
                    error_result = {
                        "query": queries[i] if i < len(queries) else f"query_{i}",
                        "content": f"搜索失败: {str(result)}",
                        "sources": [],
                        "timestamp": datetime.now().isoformat()
                    }
                    valid_results.append(error_result)
                else:
                    valid_results.append(result)
                    if result.get("sources"):
                        sources.extend(result["sources"])
            
            search_results = valid_results
            
            # 步骤3: 反思和补充搜索（如果需要）
            if max_iterations > 1:
                reflection = await self._reflect_on_results(question, search_results)
                if not reflection.get("is_sufficient", True) and reflection.get("follow_up_queries"):
                    logger.info("Conducting follow-up research based on reflection")
                    for follow_up_query in reflection["follow_up_queries"][:2]:  # 限制数量
                        result = await self._execute_search(follow_up_query)
                        search_results.append(result)
                        if result.get("sources"):
                            sources.extend(result["sources"])
            
            # 刷新待处理的优化请求并等待完成
            if hasattr(self, 'request_optimizer') and self.request_optimizer:
                await self.request_optimizer.wait_for_completion(timeout=120.0)
            
            # 步骤4: 综合分析并生成最终答案
            final_answer = await self._synthesize_answer(question, search_results)
            
            # 构建输出
            output = {
                "answer": final_answer,
                "sources": sources,
                "search_queries": queries,
                "query_count": len(queries),
                "research_loops": min(max_iterations, 2),
                "search_results": search_results,
                "timestamp": datetime.now().isoformat()
            }
            
            # 添加性能统计
            total_research_time = time.time() - start_time
            performance_stats = {
                "parallel_search_time": parallel_time,
                "total_research_time": total_research_time,
                "optimization_stats": self.get_optimization_stats() if hasattr(self, 'get_optimization_stats') else {}
            }
            
            logger.info(f"Research completed successfully. Query count: {output['query_count']}, Total time: {total_research_time:.2f}s")
            
            # 构建成功结果
            result = {
                "success": True,
                "output": output,
                "error_message": "",
                "error_type": "",
                "performance_stats": performance_stats
            }
            
            # 缓存结果
            if self.cache_enabled:
                await self.cache.cache_result(question, result, research_depth)
            
            return result
            
        except Exception as e:
            logger.error(f"Deep research failed: {str(e)}", exc_info=True)
            return {
                "success": False,
                "output": {},
                "error_message": str(e),
                "error_type": "DeepSearchError"
            }
    
    async def _generate_search_queries(self, question: str, research_depth: str) -> List[str]:
        """生成搜索查询"""
        try:
            # 根据研究深度确定查询数量
            query_counts = {
                "quick": 2,
                "standard": 3,
                "comprehensive": 5
            }
            num_queries = query_counts.get(research_depth, 3)
            
            prompt = f"""您是一个专业的搜索查询生成专家。请为以下研究问题生成{num_queries}个多样化的、高质量的搜索查询。

研究问题: {question}

要求：
1. 查询应该涵盖问题的不同方面
2. 确保查询的多样性，避免重复
3. 优先获取最新信息（2024-2025年）
4. 查询应该具体且可搜索

请以JSON格式返回查询列表：
{{
  "queries": ["查询1", "查询2", "查询3"],
  "rationale": "生成这些查询的理由"
}}

只返回JSON，不要其他文字："""

            # 使用优化的LLM调用生成查询
            response = await self._optimized_llm_call(prompt, task_type="query_generation", priority=1)
            
            # 解析响应 - 增强类型检查和错误处理
            try:
                # 确保response是字符串类型
                if not isinstance(response, str):
                    logger.warning(f"Expected string response, got {type(response)}. Converting to string.")
                    response_text = str(response)
                else:
                    response_text = response
                
                # 尝试解析JSON - 先处理可能的markdown格式
                json_content = self._extract_json_from_markdown(response_text)
                result = json.loads(json_content)
                
                # 检查结果是否为字典并包含queries字段
                if isinstance(result, dict) and "queries" in result:
                    queries = result.get("queries", [question])
                else:
                    logger.warning("Response does not contain expected 'queries' field, using original question")
                    queries = [question]
                    
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse query generation response as JSON: {e}, using original question")
                queries = [question]
            except Exception as e:
                logger.error(f"Unexpected error during response parsing: {e}, using original question")
                queries = [question]
            
            return queries[:num_queries]  # 确保不超过限制
            
        except Exception as e:
            logger.error(f"Query generation failed: {e}")
            return [question]  # 失败时返回原问题
    
    async def _execute_search(self, query: str) -> Dict[str, Any]:
        """执行搜索（模拟搜索结果）"""
        try:
            # 生成基于LLM的搜索结果摘要
            prompt = f"""请基于您的知识为以下搜索查询提供详细的研究信息。请提供准确、最新的信息。

搜索查询: {query}

请提供：
1. 相关的详细信息
2. 关键要点和趋势
3. 具体的技术细节（如果适用）
4. 最新发展（2024-2025年）

请以结构化的方式组织信息，包含具体的事实和数据。"""

            # 使用优化的LLM调用执行搜索
            response = await self._optimized_llm_call(prompt, task_type="search_execution", priority=1)
            
            # 确保response是字符串类型
            if not isinstance(response, str):
                logger.warning(f"Expected string response, got {type(response)}. Converting to string.")
                response_content = str(response)
            else:
                response_content = response
            
            # 模拟来源信息
            sources = [
                {"title": f"Research source for: {query[:50]}...", "url": f"https://example.com/research/{hash(query) % 1000}"},
                {"title": f"Technical analysis: {query[:40]}...", "url": f"https://tech.example.com/{hash(query) % 500}"}
            ]
            
            return {
                "query": query,
                "content": response_content,
                "sources": sources,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Search execution failed for query '{query}': {e}")
            return {
                "query": query,
                "content": f"搜索失败: {str(e)}",
                "sources": [],
                "timestamp": datetime.now().isoformat()
            }
    
    async def _reflect_on_results(self, original_question: str, search_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """反思搜索结果并确定是否需要补充搜索"""
        try:
            # 汇总搜索结果
            combined_content = "\n\n---\n\n".join([
                f"查询: {result['query']}\n内容: {result['content'][:500]}..."
                for result in search_results
            ])
            
            prompt = f"""请分析以下搜索结果是否充分回答了原始问题。

原始问题: {original_question}

搜索结果摘要:
{combined_content}

请评估：
1. 当前信息是否足够全面？
2. 是否存在信息空白？
3. 需要什么补充搜索？

请以JSON格式返回：
{{
  "is_sufficient": true/false,
  "knowledge_gap": "缺失信息描述",
  "follow_up_queries": ["补充查询1", "补充查询2"]
}}

只返回JSON："""

            # 使用优化的LLM调用进行反思
            response = await self._optimized_llm_call(prompt, task_type="reflection", priority=2)
            
            try:
                # 确保response是字符串类型
                if not isinstance(response, str):
                    logger.warning(f"Expected string response, got {type(response)}. Converting to string.")
                    response_text = str(response)
                else:
                    response_text = response
                
                # 尝试解析JSON - 先处理可能的markdown格式
                json_content = self._extract_json_from_markdown(response_text)
                result = json.loads(json_content)
                
                # 检查结果是否为字典
                if isinstance(result, dict):
                    return result
                else:
                    logger.warning("Response is not a dictionary, using default values")
                    return {"is_sufficient": True, "knowledge_gap": "", "follow_up_queries": []}
                    
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse reflection response as JSON: {e}")
                return {"is_sufficient": True, "knowledge_gap": "", "follow_up_queries": []}
            except Exception as e:
                logger.error(f"Unexpected error during reflection parsing: {e}")
                return {"is_sufficient": True, "knowledge_gap": "", "follow_up_queries": []}
                
        except Exception as e:
            logger.error(f"Reflection failed: {e}")
            return {"is_sufficient": True, "knowledge_gap": "", "follow_up_queries": []}
    
    async def _synthesize_answer(self, question: str, search_results: List[Dict[str, Any]]) -> str:
        """综合搜索结果生成最终答案"""
        try:
            # 汇总所有搜索内容
            combined_content = "\n\n".join([
                f"搜索查询: {result['query']}\n搜索结果: {result['content']}"
                for result in search_results
            ])
            
            prompt = f"""基于以下搜索结果，请为原始问题提供一个全面、专业的答案。

原始问题: {question}

搜索结果:
{combined_content}

要求：
1. 提供结构化的、详细的答案
2. 整合所有相关信息
3. 突出关键发现和趋势
4. 确保信息准确性
5. 包含具体的技术细节和最新发展

请提供专业级的深度分析报告："""

            # 使用优化的LLM调用进行答案综合
            response = await self._optimized_llm_call(prompt, task_type="synthesis", priority=1)
            
            # 确保response是字符串类型
            if not isinstance(response, str):
                logger.warning(f"Expected string response, got {type(response)}. Converting to string.")
                return str(response)
            else:
                return response
            
        except Exception as e:
            logger.error(f"Answer synthesis failed: {e}")
            return f"答案生成失败: {str(e)}"
    
    async def quick_research(self, question: str) -> Dict[str, Any]:
        """执行快速研究"""
        return await self.research(question, research_depth="quick", max_iterations=1)
    
    async def comprehensive_research(self, question: str, topic_focus: Optional[str] = None) -> Dict[str, Any]:
        """执行全面研究"""
        enhanced_question = question
        if topic_focus:
            enhanced_question = f"{question}\n\n特别关注: {topic_focus}"
        
        return await self.research(enhanced_question, research_depth="comprehensive", max_iterations=3)
    
    def get_capabilities(self) -> List[Dict[str, Any]]:
        """获取工具能力描述"""
        return [
            {
                "name": "research",
                "description": "执行专业级深度研究，获取详细调研信息",
                "parameters": {
                    "question": {
                        "type": "string",
                        "description": "要研究的问题或主题",
                        "required": True
                    },
                    "research_depth": {
                        "type": "string",
                        "description": "研究深度: quick/standard/comprehensive",
                        "required": False
                    },
                    "max_iterations": {
                        "type": "integer",
                        "description": "最大迭代次数",
                        "required": False
                    }
                }
            },
            {
                "name": "quick_research",
                "description": "执行快速研究，适用于需要快速获取基础信息的场景",
                "parameters": {
                    "question": {
                        "type": "string",
                        "description": "要研究的问题或主题",
                        "required": True
                    }
                }
            },
            {
                "name": "comprehensive_research",
                "description": "执行全面深度研究，适用于需要详细、专业级调研信息的场景",
                "parameters": {
                    "question": {
                        "type": "string",
                        "description": "要研究的问题或主题",
                        "required": True
                    },
                    "topic_focus": {
                        "type": "string",
                        "description": "可选的主题焦点，用于引导研究方向",
                        "required": False
                    }
                }
            },
            {
                "name": "get_health_status",
                "description": "获取系统健康状态和性能指标",
                "parameters": {}
            },
            {
                "name": "get_optimization_stats",
                "description": "获取请求优化统计信息",
                "parameters": {}
            }
        ]