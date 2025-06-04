"""
Node implementations for Deep Research LangGraph
深度研究 LangGraph 的节点实现
"""

import os
import json
import logging
from typing import Dict, Any, List, Union
from pydantic import BaseModel, Field

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.types import Send
from google.genai import Client
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch

from .state import (
    OverallState, 
    QueryGenerationState, 
    ReflectionState, 
    WebSearchState,
    ResearchConfiguration
)
from .prompts import (
    get_query_generation_prompt,
    get_web_search_prompt, 
    get_reflection_prompt,
    get_answer_prompt
)
from .utils import (
    get_current_date,
    get_research_topic,
    get_citations,
    insert_citation_markers,
    resolve_urls,
    sanitize_query
)

logger = logging.getLogger(__name__)

# Pydantic 模型用于结构化输出
class SearchQueryList(BaseModel):
    """搜索查询列表"""
    query: List[str] = Field(description="搜索查询列表")
    rationale: str = Field(description="查询生成的理由")


class Reflection(BaseModel):
    """反思结果"""
    is_sufficient: bool = Field(description="信息是否充分")
    knowledge_gap: str = Field(description="知识缺口描述")
    follow_up_queries: List[str] = Field(description="后续查询列表")


def get_gemini_client() -> Client:
    """获取 Gemini 客户端"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 环境变量未设置")
    return Client(api_key=api_key)


def get_gemini_llm(model: str = "gemini-2.0-flash-exp", temperature: float = 0.7) -> ChatGoogleGenerativeAI:
    """获取 Gemini LLM 实例"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 环境变量未设置")
    
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        max_retries=2,
        api_key=api_key,
    )


async def generate_query(state: OverallState, config: Dict[str, Any] = None) -> QueryGenerationState:
    """
    生成搜索查询的节点
    
    Args:
        state: 当前图状态
        config: 配置信息
        
    Returns:
        包含查询列表的状态更新
    """
    try:
        # 解析配置
        research_config = ResearchConfiguration.from_dict(config or {})
        
        # 检查是否已有初始查询数量
        if state.get("initial_search_query_count") is None:
            state["initial_search_query_count"] = research_config.initial_search_query_count
        
        # 初始化 LLM
        llm = get_gemini_llm(
            model=research_config.query_generator_model,
            temperature=1.0
        )
        structured_llm = llm.with_structured_output(SearchQueryList)
        
        # 生成提示词
        research_topic = get_research_topic(state["messages"])
        prompt = get_query_generation_prompt(
            research_topic,
            state["initial_search_query_count"]
        )
        
        logger.info(f"生成查询 - 主题: {research_topic}, 数量: {state['initial_search_query_count']}")
        
        # 调用 LLM 生成查询
        result = await structured_llm.ainvoke(prompt)
        
        # 清理和验证查询
        cleaned_queries = [sanitize_query(q) for q in result.query if q.strip()]
        
        logger.info(f"成功生成 {len(cleaned_queries)} 个查询")
        
        return {"query_list": cleaned_queries}
        
    except Exception as e:
        logger.error(f"查询生成失败: {str(e)}")
        # 返回默认查询
        research_topic = get_research_topic(state.get("messages", []))
        return {"query_list": [research_topic]}


def continue_to_web_research(state: QueryGenerationState) -> List[Send]:
    """
    继续到网络研究的路由节点
    
    为每个搜索查询创建一个网络研究任务
    """
    return [
        Send("web_research", {"search_query": search_query, "id": str(idx)})
        for idx, search_query in enumerate(state["query_list"])
    ]


async def web_research(state: WebSearchState, config: Dict[str, Any] = None) -> OverallState:
    """
    执行网络搜索研究的节点
    
    Args:
        state: 网络搜索状态
        config: 配置信息
        
    Returns:
        包含搜索结果的状态更新
    """
    try:
        # 解析配置
        research_config = ResearchConfiguration.from_dict(config or {})
        
        # 获取 Gemini 客户端
        genai_client = get_gemini_client()
        
        # 生成搜索提示词
        prompt = get_web_search_prompt(state["search_query"])
        
        logger.info(f"执行网络搜索 - 查询: {state['search_query']}")
        
        # 使用 Gemini 2.0 新的 Google Search API 格式
        google_search_tool = Tool(google_search=GoogleSearch())
        
        response = genai_client.models.generate_content(
            model=research_config.query_generator_model,
            contents=prompt,
            config=GenerateContentConfig(
                tools=[google_search_tool],
                response_modalities=["TEXT"],
                temperature=0,
            ),
        )
        
        # 处理搜索结果
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            
            # 获取引用信息
            resolved_urls = {}
            citations = []
            sources_gathered = []
            
            if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                grounding_metadata = candidate.grounding_metadata
                
                # 优先使用Gemini 2.0的search_entry_point (新方式)
                if hasattr(grounding_metadata, 'search_entry_point') and grounding_metadata.search_entry_point:
                    search_entry = grounding_metadata.search_entry_point
                    if hasattr(search_entry, 'rendered_content') and search_entry.rendered_content:
                        rendered_content = search_entry.rendered_content
                        logger.info(f"使用search_entry_point - 内容长度: {len(rendered_content)}")
                        
                        # 将rendered_content作为搜索结果
                        sources_gathered = [{
                            "content": rendered_content,
                            "source": "google_search_entry_point",
                            "search_query": state["search_query"]
                        }]
                        
                        # 也检查是否有grounding_chunks用于引用
                        grounding_chunks = getattr(grounding_metadata, 'grounding_chunks', None)
                        if grounding_chunks:
                            try:
                                resolved_urls = resolve_urls(grounding_chunks, int(state["id"]))
                                citations = get_citations(response, resolved_urls)
                                chunk_sources = [
                                    item for citation in citations
                                    for item in citation.get("segments", [])
                                    if citation.get("segments")
                                ]
                                sources_gathered.extend(chunk_sources)
                            except Exception as e:
                                logger.warning(f"处理grounding_chunks时出错: {e}")
                    else:
                        logger.warning("search_entry_point存在但rendered_content为空")
                        sources_gathered = []
                else:
                    # 回退到旧方式：使用grounding_chunks
                    grounding_chunks = getattr(grounding_metadata, 'grounding_chunks', None)
                    if grounding_chunks is not None:
                        logger.info(f"使用grounding_chunks回退方式 - 数量: {len(grounding_chunks) if grounding_chunks else 0}")
                        resolved_urls = resolve_urls(grounding_chunks, int(state["id"]))
                        citations = get_citations(response, resolved_urls)
                        sources_gathered = [
                            item for citation in citations
                            for item in citation.get("segments", [])
                            if citation.get("segments")
                        ]
                    else:
                        logger.warning("grounding_chunks为空，无法提取引用信息")
                        sources_gathered = []
            
            # 插入引用标记
            modified_text = insert_citation_markers(response.text, citations)
            
            logger.info(f"搜索完成 - 找到 {len(sources_gathered)} 个源")
            
            return {
                "sources_gathered": sources_gathered,
                "search_query": [state["search_query"]],
                "web_research_result": [modified_text],
            }
        else:
            logger.warning(f"搜索无结果: {state['search_query']}")
            return {
                "sources_gathered": [],
                "search_query": [state["search_query"]],
                "web_research_result": [f"关于 '{state['search_query']}' 的搜索未找到有效结果。"],
            }
            
    except Exception as e:
        logger.error(f"网络搜索失败: {str(e)}")
        return {
            "sources_gathered": [],
            "search_query": [state["search_query"]],
            "web_research_result": [f"搜索 '{state['search_query']}' 时发生错误: {str(e)}"],
        }


async def reflection(state: OverallState, config: Dict[str, Any] = None) -> ReflectionState:
    """
    反思评估节点 - 判断信息是否充分
    
    Args:
        state: 当前状态
        config: 配置信息
        
    Returns:
        反思结果状态
    """
    try:
        # 解析配置
        research_config = ResearchConfiguration.from_dict(config or {})
        
        # 增加研究循环计数
        state["research_loop_count"] = state.get("research_loop_count", 0) + 1
        reasoning_model = state.get("reasoning_model") or research_config.reasoning_model
        
        # 初始化 LLM
        llm = get_gemini_llm(model=reasoning_model, temperature=1.0)
        structured_llm = llm.with_structured_output(Reflection)
        
        # 生成反思提示词
        research_topic = get_research_topic(state["messages"])
        summaries = "\n\n---\n\n".join(state.get("web_research_result", []))
        prompt = get_reflection_prompt(research_topic, summaries)
        
        logger.info(f"执行反思评估 - 循环 {state['research_loop_count']}")
        
        # 调用 LLM 进行反思
        result = await structured_llm.ainvoke(prompt)
        
        # 清理后续查询
        follow_up_queries = [
            sanitize_query(q) for q in result.follow_up_queries 
            if q.strip()
        ]
        
        logger.info(f"反思完成 - 充分性: {result.is_sufficient}, 后续查询: {len(follow_up_queries)}")
        
        return {
            "is_sufficient": result.is_sufficient,
            "knowledge_gap": result.knowledge_gap,
            "follow_up_queries": follow_up_queries,
            "research_loop_count": state["research_loop_count"],
            "number_of_ran_queries": len(state.get("search_query", [])),
        }
        
    except Exception as e:
        logger.error(f"反思评估失败: {str(e)}")
        # 返回保守的结果，倾向于认为信息不足
        return {
            "is_sufficient": False,
            "knowledge_gap": f"评估过程中发生错误: {str(e)}",
            "follow_up_queries": [],
            "research_loop_count": state.get("research_loop_count", 0) + 1,
            "number_of_ran_queries": len(state.get("search_query", [])),
        }


def evaluate_research(state: ReflectionState, config: Dict[str, Any] = None) -> Union[str, List[Send]]:
    """
    评估研究进度的路由节点
    
    决定是继续研究还是生成最终答案
    
    Args:
        state: 反思状态
        config: 配置信息
        
    Returns:
        下一个节点名称或任务列表
    """
    try:
        # 解析配置
        research_config = ResearchConfiguration.from_dict(config or {})
        
        max_research_loops = (
            state.get("max_research_loops")
            if state.get("max_research_loops") is not None
            else research_config.max_research_loops
        )
        
        logger.info(f"评估研究进度 - 循环: {state['research_loop_count']}/{max_research_loops}, 充分性: {state['is_sufficient']}")
        
        # 检查是否应该结束研究
        if state["is_sufficient"] or state["research_loop_count"] >= max_research_loops:
            logger.info("研究完成，生成最终答案")
            return "finalize_answer"
        else:
            # 继续研究，创建后续查询任务
            follow_up_queries = state.get("follow_up_queries", [])
            if not follow_up_queries:
                logger.warning("没有后续查询，强制结束研究")
                return "finalize_answer"
            
            logger.info(f"继续研究 - 生成 {len(follow_up_queries)} 个后续查询")
            return [
                Send(
                    "web_research",
                    {
                        "search_query": follow_up_query,
                        "id": str(state["number_of_ran_queries"] + idx),
                    },
                )
                for idx, follow_up_query in enumerate(follow_up_queries)
            ]
            
    except Exception as e:
        logger.error(f"研究评估失败: {str(e)}")
        return "finalize_answer"


async def finalize_answer(state: OverallState, config: Dict[str, Any] = None) -> OverallState:
    """
    生成最终答案的节点
    
    Args:
        state: 当前状态
        config: 配置信息
        
    Returns:
        包含最终答案的状态更新
    """
    try:
        # 解析配置
        research_config = ResearchConfiguration.from_dict(config or {})
        reasoning_model = state.get("reasoning_model") or research_config.reasoning_model
        
        # 初始化 LLM
        llm = get_gemini_llm(model=reasoning_model, temperature=0)
        
        # 生成最终答案提示词
        research_topic = get_research_topic(state["messages"])
        summaries = "\n---\n\n".join(state.get("web_research_result", []))
        prompt = get_answer_prompt(research_topic, summaries)
        
        logger.info(f"生成最终答案 - 主题: {research_topic}")
        
        # 调用 LLM 生成答案
        result = await llm.ainvoke(prompt)
        
        # 处理源文档引用
        unique_sources = []
        sources_gathered = state.get("sources_gathered", [])
        
        for source in sources_gathered:
            if source.get("short_url") and source["short_url"] in result.content:
                # 替换短链接为完整链接
                result.content = result.content.replace(
                    source["short_url"], source.get("value", source["short_url"])
                )
                unique_sources.append(source)
        
        logger.info(f"最终答案生成完成 - 使用了 {len(unique_sources)} 个源")
        
        return {
            "messages": [AIMessage(content=result.content)],
            "sources_gathered": unique_sources,
            "final_answer": result.content
        }
        
    except Exception as e:
        logger.error(f"最终答案生成失败: {str(e)}")
        
        # 生成错误回退答案
        research_topic = get_research_topic(state.get("messages", []))
        fallback_answer = f"抱歉，在生成关于 '{research_topic}' 的最终答案时遇到了问题。请稍后重试。错误信息: {str(e)}"
        
        return {
            "messages": [AIMessage(content=fallback_answer)],
            "sources_gathered": [],
            "final_answer": fallback_answer
        }