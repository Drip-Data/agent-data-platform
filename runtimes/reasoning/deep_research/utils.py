"""
Utility functions for Deep Research module
深度研究模块的工具函数
"""

import re
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)


def get_current_date() -> str:
    """获取当前日期字符串"""
    return datetime.now().strftime("%Y-%m-%d")


def get_research_topic(messages: List[Dict[str, Any]]) -> str:
    """从消息列表中提取研究主题"""
    if not messages:
        return "研究主题未定义"
    
    # 获取最后一条用户消息作为研究主题
    for message in reversed(messages):
        if isinstance(message, dict):
            if message.get('type') == 'human' or message.get('role') == 'user':
                return message.get('content', '研究主题未定义')
        elif hasattr(message, 'content'):
            return message.content
    
    return "研究主题未定义"


def resolve_urls(grounding_chunks: List[Dict], query_id: int) -> Dict[str, str]:
    """
    将长URL解析为短URL映射
    
    Args:
        grounding_chunks: Gemini API返回的grounding chunks
        query_id: 查询ID用于生成唯一短URL
        
    Returns:
        Dict mapping short_url to original_url
    """
    url_mapping = {}
    
    if not grounding_chunks:
        return url_mapping
    
    for idx, chunk in enumerate(grounding_chunks):
        if 'web' in chunk and 'uri' in chunk['web']:
            original_url = chunk['web']['uri']
            short_url = f"[{query_id}-{idx}]"
            url_mapping[short_url] = original_url
    
    return url_mapping


def get_citations(response, resolved_urls: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    从响应中提取引用信息
    
    Args:
        response: Gemini API响应对象
        resolved_urls: URL映射字典
        
    Returns:
        List of citation dictionaries
    """
    citations = []
    
    if not hasattr(response, 'candidates') or not response.candidates:
        return citations
    
    candidate = response.candidates[0]
    if not hasattr(candidate, 'grounding_metadata'):
        return citations
    
    grounding_metadata = candidate.grounding_metadata
    if not hasattr(grounding_metadata, 'grounding_chunks'):
        return citations
    
    for idx, chunk in enumerate(grounding_metadata.grounding_chunks):
        if 'web' in chunk and 'uri' in chunk['web']:
            original_url = chunk['web']['uri']
            title = chunk['web'].get('title', '未知标题')
            
            # 找到对应的短URL
            short_url = None
            for short, orig in resolved_urls.items():
                if orig == original_url:
                    short_url = short
                    break
            
            if short_url:
                citations.append({
                    'segments': [{
                        'short_url': short_url,
                        'value': original_url,
                        'title': title
                    }]
                })
    
    return citations


def insert_citation_markers(text: str, citations: List[Dict[str, Any]]) -> str:
    """
    在文本中插入引用标记
    
    Args:
        text: 原始文本
        citations: 引用列表
        
    Returns:
        插入引用标记后的文本
    """
    if not citations:
        return text
    
    modified_text = text
    
    # 为每个引用在文本末尾添加引用标记
    for citation in citations:
        for segment in citation['segments']:
            short_url = segment['short_url']
            # 简单地在文本末尾添加引用
            if short_url not in modified_text:
                modified_text += f" {short_url}"
    
    return modified_text


def extract_domain(url: str) -> str:
    """提取URL的域名"""
    try:
        parsed = urlparse(url)
        return parsed.netloc
    except Exception:
        return "unknown"


def truncate_text(text: str, max_length: int = 1000) -> str:
    """截断文本到指定长度"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def generate_search_id() -> str:
    """生成搜索会话ID"""
    return str(uuid.uuid4())[:8]


def format_sources(sources: List[Dict[str, Any]]) -> str:
    """格式化源文档列表为可读文本"""
    if not sources:
        return "无可用源文档"
    
    formatted = []
    for idx, source in enumerate(sources, 1):
        title = source.get('title', '未知标题')
        url = source.get('value', source.get('short_url', '无URL'))
        formatted.append(f"{idx}. {title}\n   {url}")
    
    return "\n\n".join(formatted)


def sanitize_query(query: str) -> str:
    """清理和标准化搜索查询"""
    # 移除多余的空格
    query = re.sub(r'\s+', ' ', query.strip())
    
    # 移除特殊字符但保留基本标点
    query = re.sub(r'[^\w\s\-.,?!()"]', '', query)
    
    return query


def validate_search_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """验证和标准化搜索配置"""
    default_config = {
        'initial_search_query_count': 3,
        'max_research_loops': 3,
        'reasoning_model': 'gemini-2.0-flash-exp',
        'query_generator_model': 'gemini-2.0-flash-exp'
    }
    
    # 合并配置，使用默认值填充缺失项
    validated_config = {**default_config, **config}
    
    # 验证数值范围
    validated_config['initial_search_query_count'] = max(1, min(10, validated_config['initial_search_query_count']))
    validated_config['max_research_loops'] = max(1, min(10, validated_config['max_research_loops']))
    
    return validated_config


class CitationManager:
    """引用管理器"""
    
    def __init__(self):
        self.citations = {}
        self.counter = 0
    
    def add_citation(self, url: str, title: str = "") -> str:
        """添加引用并返回引用标记"""
        if url in self.citations:
            return self.citations[url]['marker']
        
        self.counter += 1
        marker = f"[{self.counter}]"
        self.citations[url] = {
            'marker': marker,
            'title': title or f"Source {self.counter}",
            'url': url
        }
        return marker
    
    def get_citations_list(self) -> List[Dict[str, str]]:
        """获取所有引用的列表"""
        return [
            {
                'marker': info['marker'],
                'title': info['title'],
                'url': info['url']
            }
            for info in self.citations.values()
        ]
    
    def format_citations(self) -> str:
        """格式化引用列表为文本"""
        if not self.citations:
            return ""
        
        formatted = ["## 参考资料"]
        for info in self.citations.values():
            formatted.append(f"{info['marker']} {info['title']}: {info['url']}")
        
        return "\n".join(formatted)