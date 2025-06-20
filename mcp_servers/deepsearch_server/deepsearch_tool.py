#!/usr/bin/env python3
"""
Deepsearch Tool - Professional Research Agent
基于LangGraph的专业级深度搜索工具，用于获取详细的调研信息
"""

import os
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

# LangGraph and related imports
from langchain_core.messages import HumanMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from google.genai import Client

# Import the research agent components from the quickstart
import sys
from pathlib import Path

# 动态添加gemini-fullstack路径
project_root = Path(__file__).parent.parent.parent.parent
gemini_fullstack_src = project_root / 'gemini-fullstack-langgraph-quickstart' / 'backend' / 'src'
if gemini_fullstack_src.exists():
    sys.path.insert(0, str(gemini_fullstack_src))
else:
    raise ImportError(f"Gemini fullstack source not found at: {gemini_fullstack_src}")

from agent.graph import graph
from agent.configuration import Configuration
from agent.state import OverallState

logger = logging.getLogger(__name__)

class DeepSearchTool:
    """专业级深度搜索工具，基于LangGraph实现的研究代理"""
    
    def __init__(self):
        """初始化深度搜索工具"""
        # 确保环境变量已设置
        if not os.getenv("GEMINI_API_KEY"):
            raise ValueError("GEMINI_API_KEY environment variable is required")
            
        # 初始化Google GenAI客户端
        self.genai_client = Client(api_key=os.getenv("GEMINI_API_KEY"))
        
        # 默认配置，使用与原版一致的模型配置
        self.default_config = {
            "configurable": {
                "query_generator_model": "gemini-2.0-flash",
                "reflection_model": "gemini-2.5-flash", 
                "answer_model": "gemini-2.5-pro",
                "number_of_initial_queries": 3,
                "max_research_loops": 2
            }
        }
        
        # 验证依赖的图是否正确加载
        if not hasattr(graph, 'invoke'):
            raise ImportError("Failed to load LangGraph research agent")
            
        logger.info("DeepSearch tool initialized successfully")
    
    async def research(self, question: str, **kwargs) -> Dict[str, Any]:
        """
        执行深度研究任务
        
        Args:
            question: 研究问题
            **kwargs: 可选参数
                - initial_queries: 初始查询数量 (默认: 3)
                - max_loops: 最大研究循环次数 (默认: 2)
                - reasoning_model: 推理模型名称
                
        Returns:
            Dict containing:
                - success: bool
                - output: research results
                - error_message: error message if failed
                - error_type: error type if failed
        """
        try:
            logger.info(f"Starting deep research for question: {question}")
            
            # 构建配置
            config = self.default_config.copy()
            
            # 从kwargs更新配置
            if "initial_queries" in kwargs:
                config["configurable"]["number_of_initial_queries"] = min(max(kwargs["initial_queries"], 1), 10)  # 限制范围
            if "max_loops" in kwargs:
                config["configurable"]["max_research_loops"] = min(max(kwargs["max_loops"], 1), 5)  # 限制范围
            if "reasoning_model" in kwargs:
                # 验证模型名称
                valid_models = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"]
                if kwargs["reasoning_model"] in valid_models:
                    config["configurable"]["answer_model"] = kwargs["reasoning_model"]
                    config["configurable"]["reflection_model"] = kwargs["reasoning_model"]
                else:
                    logger.warning(f"Invalid model {kwargs['reasoning_model']}, using default")
            
            # 构建初始状态
            initial_state = {
                "messages": [HumanMessage(content=question)],
                "search_query": [],
                "web_research_result": [],
                "sources_gathered": [],
                "research_loop_count": 0,
                "initial_search_query_count": config["configurable"]["number_of_initial_queries"],
                "max_research_loops": config["configurable"]["max_research_loops"]
            }
            
            # 如果提供了推理模型，添加到状态中
            if "reasoning_model" in kwargs:
                initial_state["reasoning_model"] = kwargs["reasoning_model"]
            
            # 执行研究图
            logger.info("Executing research graph...")
            result = await asyncio.to_thread(
                graph.invoke, 
                initial_state, 
                config
            )
            
            # 处理结果
            final_answer = ""
            sources = []
            
            if result.get("messages"):
                # 获取最后一条AI消息作为答案
                ai_messages = [msg for msg in result["messages"] if isinstance(msg, AIMessage)]
                if ai_messages:
                    final_answer = ai_messages[-1].content
            
            if result.get("sources_gathered"):
                sources = result["sources_gathered"]
            
            # 构建输出，保持与原版格式一致
            output = {
                "answer": final_answer,
                "sources": sources,
                "search_queries": result.get("search_query", []),
                "query_count": len(result.get("search_query", [])),
                "research_loops": result.get("research_loop_count", 0),
                "web_research_results": result.get("web_research_result", []),
                "configuration": {
                    "initial_queries": config["configurable"]["number_of_initial_queries"],
                    "max_loops": config["configurable"]["max_research_loops"],
                    "models": {
                        "query_generator": config["configurable"]["query_generator_model"],
                        "reflection": config["configurable"]["reflection_model"],
                        "answer": config["configurable"]["answer_model"]
                    }
                },
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"Research completed successfully. Query count: {output['query_count']}, Loops: {output['research_loops']}")
            
            return {
                "success": True,
                "output": output,
                "error_message": "",
                "error_type": ""
            }
            
        except Exception as e:
            logger.error(f"Deep research failed: {str(e)}", exc_info=True)
            return {
                "success": False,
                "output": {},
                "error_message": str(e),
                "error_type": "DeepSearchError"
            }
    
    async def quick_research(self, question: str) -> Dict[str, Any]:
        """
        执行快速研究（单轮搜索）
        
        Args:
            question: 研究问题
            
        Returns:
            Dict containing research results
        """
        return await self.research(
            question=question,
            initial_queries=2,
            max_loops=1
        )
    
    async def comprehensive_research(self, question: str, topic_focus: Optional[str] = None) -> Dict[str, Any]:
        """
        执行全面研究（多轮深度搜索）
        
        Args:
            question: 研究问题
            topic_focus: 可选的主题焦点
            
        Returns:
            Dict containing comprehensive research results
        """
        # 如果提供了主题焦点，将其整合到问题中
        enhanced_question = question
        if topic_focus:
            enhanced_question = f"{question}\n\nPlease focus specifically on: {topic_focus}"
        
        return await self.research(
            question=enhanced_question,
            initial_queries=5,
            max_loops=3,
            reasoning_model="gemini-2.0-flash-exp"
        )
    
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
                    "initial_queries": {
                        "type": "integer",
                        "description": "初始搜索查询数量 (默认: 3)",
                        "required": False
                    },
                    "max_loops": {
                        "type": "integer", 
                        "description": "最大研究循环次数 (默认: 2)",
                        "required": False
                    },
                    "reasoning_model": {
                        "type": "string",
                        "description": "推理模型名称 (默认: gemini-2.0-flash-exp)",
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
            }
        ]