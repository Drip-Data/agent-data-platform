#!/usr/bin/env python3
"""
Corpus Ingestor - 语料导入器
基于TaskCraft算法，实现主动语料采样和轨迹处理
"""

import asyncio
import json
import logging
import os
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

from core.interfaces import TrajectoryResult, ExecutionStep, ActionType
from core.toolscore.mcp_client import MCPToolClient
from .enhanced_interfaces import CorpusContent, ContentType, EnhancedSynthesisConfig

logger = logging.getLogger(__name__)


class TrajectoryCorpusExtractor:
    """轨迹语料提取器"""
    
    def __init__(self):
        self.config = EnhancedSynthesisConfig()
    
    async def extract_from_trajectories(self, trajectories: List[TrajectoryResult]) -> List[CorpusContent]:
        """从轨迹中提取原子语料"""
        corpus_contents = []
        
        for trajectory in trajectories:
            try:
                # 提取轨迹级别的语料
                trajectory_corpus = await self._extract_trajectory_corpus(trajectory)
                if trajectory_corpus:
                    corpus_contents.append(trajectory_corpus)
                
                # 提取步骤级别的语料
                step_corpus_list = await self._extract_step_corpus(trajectory)
                corpus_contents.extend(step_corpus_list)
                
            except Exception as e:
                # 增强日志记录，包含导致错误的轨迹对象
                logger.error(f"❌ 提取轨迹语料失败 {trajectory.task_id}: {e}")
                try:
                    # 尝试将轨迹对象序列化为JSON进行记录
                    trajectory_dump = json.dumps(trajectory.to_dict() if hasattr(trajectory, 'to_dict') else trajectory.__dict__, indent=2, ensure_ascii=False)
                    logger.error(f" problematic_trajectory: {trajectory_dump}")
                except Exception as dump_error:
                    logger.error(f"无法序列化轨迹对象: {dump_error}")
                continue
        
        logger.info(f"✅ 从 {len(trajectories)} 个轨迹中提取了 {len(corpus_contents)} 个语料")
        return corpus_contents
    
    async def _extract_trajectory_corpus(self, trajectory: TrajectoryResult) -> Optional[CorpusContent]:
        """提取轨迹级别的语料"""
        if not trajectory.final_result or len(trajectory.final_result.strip()) < 30:
            return None
        
        return CorpusContent(
            source=f"trajectory_{trajectory.task_id}",
            content_type=ContentType.TRAJECTORY,
            text_content=trajectory.final_result,
            metadata={
                "task_id": trajectory.task_id,
                "task_description": trajectory.task_description,
                "runtime_id": trajectory.runtime_id,
                "success": trajectory.success,
                "total_duration": trajectory.total_duration,
                "steps_count": len(trajectory.steps)
            }
        )
    
    async def _extract_step_corpus(self, trajectory: TrajectoryResult) -> List[CorpusContent]:
        """提取步骤级别的语料"""
        corpus_contents = []
        
        for step in trajectory.steps:
            try:
                if step.action_type == ActionType.TOOL_CALL:
                    tool_id = step.action_params.get('tool_id', '')
                    extracted_content = None
                    
                    if 'browser' in tool_id.lower():
                        # 从浏览器工具的输出中提取网页内容
                        extracted_content = await self._extract_web_content(step)
                    
                    elif 'python' in tool_id.lower() or 'code' in tool_id.lower():
                        # 从代码执行结果中提取数据
                        extracted_content = await self._extract_code_results(step)
                    
                    elif 'search' in tool_id.lower():
                        # 从搜索结果中提取内容
                        extracted_content = await self._extract_search_results(step)
                    
                    # 如果没有匹配特定工具类型，尝试通用提取
                    if not extracted_content and step.observation and len(step.observation.strip()) > 30:
                        extracted_content = await self._extract_generic_tool_output(step)
                    
                    if extracted_content:
                        corpus_contents.append(extracted_content)
                
            except Exception as e:
                logger.warning(f"⚠️ 提取步骤语料失败 {trajectory.task_id}#{step.step_id}: {e}")
                try:
                    # 尝试将步骤对象序列化为JSON进行记录
                    step_dump = json.dumps(step.to_dict() if hasattr(step, 'to_dict') else step.__dict__, indent=2, ensure_ascii=False)
                    logger.warning(f"  problematic_step: {step_dump}")
                except Exception as dump_error:
                    logger.warning(f"  无法序列化步骤对象: {dump_error}")
                continue
        
        return corpus_contents
    
    async def _extract_web_content(self, step: ExecutionStep) -> Optional[CorpusContent]:
        """提取网页内容"""
        if not step.observation or len(step.observation.strip()) < 50:
            return None
        
        # 清理和结构化网页内容
        cleaned_content = self._clean_web_content(step.observation)
        if len(cleaned_content) < 100:
            return None
        
        return CorpusContent(
            source=f"web_step_{step.step_id}",
            content_type=ContentType.WEB,
            text_content=cleaned_content,
            metadata={
                "url": step.action_params.get('url', ''),
                "action": step.action_params.get('action', ''),
                "step_id": step.step_id,
                "success": step.success,
                "thinking": step.thinking
            }
        )
    
    async def _extract_code_results(self, step: ExecutionStep) -> Optional[CorpusContent]:
        """提取代码执行结果"""
        if not step.observation or not step.success:
            return None
        
        # 提取有价值的代码输出
        code_output = self._extract_valuable_code_output(step.observation)
        if not code_output:
            return None
        
        return CorpusContent(
            source=f"code_step_{step.step_id}",
            content_type=ContentType.CODE_OUTPUT,
            text_content=code_output,
            metadata={
                "code": step.action_params.get('code', ''),
                "execution_time": step.duration,
                "step_id": step.step_id,
                "thinking": step.thinking
            }
        )
    
    async def _extract_search_results(self, step: ExecutionStep) -> Optional[CorpusContent]:
        """提取搜索结果"""
        if not step.observation:
            return None
        
        try:
            observation = step.observation
            
            # 处理"工具执行成功: "前缀
            if observation.startswith("工具执行成功: "):
                observation = observation[len("工具执行成功: "):]
            
            # 处理单引号格式（转换为有效JSON）
            if observation.strip().startswith("{") and "'" in observation:
                observation = observation.replace("'", '"')
            
            # 尝试解析搜索结果JSON
            search_data = json.loads(observation) if isinstance(observation, str) else observation
            
            if not isinstance(search_data, dict):
                return None
            
            # 提取有价值内容（支持多种格式）
            valuable_content = None
            
            # 尝试从'answer'字段提取（新格式）
            if 'answer' in search_data and search_data['answer']:
                valuable_content = search_data['answer']
            
            # 尝试从'results'字段提取（旧格式）
            elif 'results' in search_data:
                valuable_content = self._extract_search_valuable_content(search_data)
            
            # 尝试从'search_results'字段提取
            elif 'search_results' in search_data:
                valuable_content = str(search_data['search_results'])[:1000]
            
            if not valuable_content or len(valuable_content.strip()) < 30:
                return None
            
            return CorpusContent(
                source=f"search_step_{step.step_id}",
                content_type=ContentType.WEB,
                text_content=valuable_content,
                metadata={
                    "query": step.action_params.get('query', ''),
                    "step_id": step.step_id,
                    "thinking": step.thinking
                }
            )
        except (json.JSONDecodeError, Exception) as e:
            logger.debug(f"搜索结果解析失败，尝试直接提取: {e}")
            # 如果JSON解析失败，直接使用观察结果
            if len(step.observation.strip()) > 50:
                return CorpusContent(
                    source=f"search_step_{step.step_id}",
                    content_type=ContentType.WEB,
                    text_content=step.observation[:1000],
                    metadata={
                        "query": step.action_params.get('query', ''),
                        "step_id": step.step_id,
                        "thinking": step.thinking,
                        "extraction_method": "direct"
                    }
                )
            return None
    
    def _clean_web_content(self, raw_content: str) -> str:
        """清理网页内容"""
        # 移除HTML标签
        content = re.sub(r'<[^>]+>', '', raw_content)
        
        # 移除多余的空白
        content = re.sub(r'\s+', ' ', content)
        
        # 移除特殊字符
        content = re.sub(r'[^\w\s\.\,\!\?\;\:\-\(\)]', '', content)
        
        return content.strip()
    
    def _extract_valuable_code_output(self, output: str) -> Optional[str]:
        """提取有价值的代码输出"""
        # 基本长度检查
        if len(output.strip()) < 30:
            return None
        
        # 只有在输出主要是错误信息时才过滤（而不是包含错误关键词）
        error_indicators = ['traceback', 'exception occurred', 'error:']
        if any(indicator in output.lower() for indicator in error_indicators):
            # 检查是否有有用的信息与错误信息混合
            if len([line for line in output.split('\n') if line.strip() and not any(err in line.lower() for err in error_indicators)]) < 3:
                return None
        
        # 提取数值结果、表格数据等
        valuable_patterns = [
            r'\d+\.\d+',  # 浮点数
            r'\d+',       # 整数
            r'[A-Z][a-z]+:\s*\d+',  # 标签:数值
            r'\w+\s*\|\s*\w+',      # 表格格式
        ]
        
        valuable_parts = []
        for pattern in valuable_patterns:
            matches = re.findall(pattern, output)
            valuable_parts.extend(matches)
        
        if valuable_parts:
            return ' '.join(valuable_parts[:20])  # 限制提取数量
        
        # 返回有意义的内容（扩大长度限制）
        return output[:1000] if len(output) > 50 else output
    
    def _extract_search_valuable_content(self, search_data: dict) -> Optional[str]:
        """提取搜索结果中的有价值内容"""
        valuable_content = []
        
        for result in search_data.get('results', [])[:5]:  # 只取前5个结果
            title = result.get('title', '')
            snippet = result.get('snippet', '')
            
            if title:
                valuable_content.append(f"标题: {title}")
            if snippet:
                valuable_content.append(f"摘要: {snippet}")
        
        return '\n'.join(valuable_content) if valuable_content else None
    
    async def _extract_generic_tool_output(self, step: ExecutionStep) -> Optional[CorpusContent]:
        """提取通用工具输出"""
        if not step.observation or len(step.observation.strip()) < 30:
            return None
        
        # 清理输出内容
        cleaned_output = step.observation.strip()
        
        # 处理"工具执行成功: "前缀
        if cleaned_output.startswith("工具执行成功: "):
            cleaned_output = cleaned_output[len("工具执行成功: "):]
        
        # 限制长度
        if len(cleaned_output) > 2000:
            cleaned_output = cleaned_output[:2000] + "..."
        
        return CorpusContent(
            source=f"generic_tool_step_{step.step_id}",
            content_type=ContentType.CODE_OUTPUT,
            text_content=cleaned_output,
            metadata={
                "tool_id": step.action_params.get('tool_id', 'unknown'),
                "step_id": step.step_id,
                "thinking": step.thinking,
                "extraction_method": "generic"
            }
        )


class ExternalCorpusLoader:
    """外部语料加载器"""
    
    def __init__(self, mcp_client: Optional[MCPToolClient] = None):
        self.mcp_client = mcp_client
        self.config = EnhancedSynthesisConfig()
    
    async def active_corpus_sampling(self, domains: List[str]) -> List[CorpusContent]:
        """主动语料采样"""
        if not self.mcp_client:
            logger.warning("⚠️ MCP客户端未配置，无法进行主动语料采样")
            return []
        
        corpus_contents = []
        
        for domain in domains:
            try:
                logger.info(f"🔍 开始采样领域: {domain}")
                
                # 生成领域相关的搜索查询
                search_queries = await self._generate_domain_queries(domain)
                
                for query in search_queries:
                    # 使用搜索工具获取内容
                    search_results = await self._search_domain_content(query)
                    
                    # 处理搜索结果
                    for result in search_results:
                        content = await self._fetch_content_from_url(result['url'])
                        if content:
                            corpus_content = CorpusContent(
                                source=f"active_sampling_{domain}",
                                content_type=ContentType.WEB,
                                text_content=content,
                                metadata={
                                    "domain": domain,
                                    "search_query": query,
                                    "url": result['url'],
                                    "title": result.get('title', ''),
                                    "snippet": result.get('snippet', '')
                                }
                            )
                            corpus_contents.append(corpus_content)
                
                logger.info(f"✅ 领域 {domain} 采样完成，获得 {len([c for c in corpus_contents if c.metadata.get('domain') == domain])} 个语料")
                
            except Exception as e:
                logger.error(f"❌ 领域 {domain} 采样失败: {e}")
                continue
        
        return corpus_contents
    
    async def _generate_domain_queries(self, domain: str) -> List[str]:
        """生成领域相关的搜索查询"""
        domain_query_templates = {
            "algorithm": [
                "算法实现教程",
                "数据结构与算法",
                "编程算法题解",
                "算法复杂度分析"
            ],
            "data_analysis": [
                "数据分析方法",
                "Python数据分析",
                "统计分析实例",
                "数据可视化教程"
            ],
            "web_automation": [
                "网页自动化工具",
                "爬虫技术教程",
                "浏览器自动化",
                "Web测试自动化"
            ],
            "research": [
                "学术研究方法",
                "论文写作指南",
                "研究数据收集",
                "文献综述方法"
            ],
            "machine_learning": [
                "机器学习算法",
                "深度学习教程",
                "AI模型训练",
                "神经网络实现"
            ]
        }
        
        return domain_query_templates.get(domain, [f"{domain} 教程", f"{domain} 实例"])
    
    async def _search_domain_content(self, query: str) -> List[Dict]:
        """搜索领域内容"""
        try:
            search_result = await self.mcp_client.call_tool("deepsearch", {
                "query": query,
                "max_results": 5
            })
            
            if search_result and 'results' in search_result:
                return search_result['results']
                
        except Exception as e:
            logger.error(f"❌ 搜索失败 '{query}': {e}")
        
        return []
    
    async def _fetch_content_from_url(self, url: str) -> Optional[str]:
        """从URL获取内容"""
        try:
            content_result = await self.mcp_client.call_tool("browser_navigator", {
                "action": "navigate",
                "url": url
            })
            
            if content_result and 'page_text' in content_result:
                page_text = content_result['page_text']
                # 清理和限制内容长度
                cleaned_text = self._clean_web_content(page_text)
                return cleaned_text[:2000] if len(cleaned_text) > 2000 else cleaned_text
                
        except Exception as e:
            logger.error(f"❌ 获取URL内容失败 {url}: {e}")
        
        return None
    
    def _clean_web_content(self, content: str) -> str:
        """清理网页内容（复用TrajectoryCorpusExtractor的方法）"""
        extractor = TrajectoryCorpusExtractor()
        return extractor._clean_web_content(content)


class ContentProcessor:
    """内容预处理器"""
    
    def __init__(self):
        self.config = EnhancedSynthesisConfig()
    
    async def preprocess_corpus_batch(self, corpus_contents: List[CorpusContent]) -> List[CorpusContent]:
        """批量预处理语料"""
        processed_contents = []
        
        for corpus in corpus_contents:
            try:
                processed_corpus = await self._preprocess_single_corpus(corpus)
                if processed_corpus:
                    processed_contents.append(processed_corpus)
            except Exception as e:
                logger.error(f"❌ 预处理语料失败 {corpus.corpus_id}: {e}")
                continue
        
        logger.info(f"✅ 预处理完成: {len(processed_contents)}/{len(corpus_contents)} 个语料")
        return processed_contents
    
    async def _preprocess_single_corpus(self, corpus: CorpusContent) -> Optional[CorpusContent]:
        """预处理单个语料"""
        # 1. 内容长度检查
        if len(corpus.text_content.strip()) < 50:
            logger.debug(f"⏩ 跳过过短内容: {corpus.corpus_id}")
            return None
        
        # 2. 内容质量检查
        if not self._is_quality_content(corpus.text_content):
            logger.debug(f"⏩ 跳过低质量内容: {corpus.corpus_id}")
            return None
        
        # 3. 内容清理和标准化
        cleaned_content = self._clean_and_normalize_content(corpus.text_content)
        
        # 4. 更新语料内容
        corpus.text_content = cleaned_content
        corpus.processing_status = "completed"
        
        # 5. 增强元数据
        corpus.metadata.update({
            "content_length": len(cleaned_content),
            "estimated_reading_time": len(cleaned_content) // 200,  # 假设每分钟200字
            "content_quality_score": self._calculate_content_quality_score(cleaned_content)
        })
        
        return corpus
    
    def _is_quality_content(self, content: str) -> bool:
        """检查内容质量"""
        # 检查是否包含太多重复内容（放宽标准）
        words = content.split()
        if len(words) > 10 and len(set(words)) / len(words) < 0.2:  # 词汇多样性低于20%，且仅对较长内容检查
            return False
        
        # 检查是否包含有意义的信息
        meaningful_patterns = [
            r'\d+',           # 数字
            r'[A-Z][a-z]+',   # 专有名词
            r'https?://',     # URL
            r'\w+@\w+\.\w+',  # 邮箱
        ]
        
        meaningful_count = 0
        for pattern in meaningful_patterns:
            if re.search(pattern, content):
                meaningful_count += 1
        
        return meaningful_count >= 2  # 至少包含2种有意义的信息
    
    def _clean_and_normalize_content(self, content: str) -> str:
        """清理和标准化内容"""
        # 1. 移除多余的空白
        content = re.sub(r'\s+', ' ', content)
        
        # 2. 标准化标点符号
        content = re.sub(r'[，。！？；：]', lambda m: {'，': ',', '。': '.', '！': '!', '？': '?', '；': ';', '：': ':'}[m.group()], content)
        
        # 3. 移除特殊字符但保留基本标点
        content = re.sub(r'[^\w\s\.\,\!\?\;\:\-\(\)\[\]\"\'\/]', '', content)
        
        # 4. 首尾去空格
        return content.strip()
    
    def _calculate_content_quality_score(self, content: str) -> float:
        """计算内容质量分数"""
        score = 0.0
        
        # 长度分数 (0.3权重)
        length_score = min(len(content) / 1000, 1.0) * 0.3
        score += length_score
        
        # 词汇多样性分数 (0.3权重)
        words = content.split()
        if words:
            diversity_score = len(set(words)) / len(words) * 0.3
            score += diversity_score
        
        # 信息密度分数 (0.4权重)
        info_patterns = [
            r'\d+\.\d+',      # 小数
            r'\d+%',          # 百分比
            r'\d{4}',         # 年份
            r'[A-Z][a-z]+',   # 专有名词
        ]
        
        info_count = 0
        for pattern in info_patterns:
            info_count += len(re.findall(pattern, content))
        
        info_density = min(info_count / 10, 1.0) * 0.4
        score += info_density
        
        return score


class CorpusIngestor:
    """统一语料导入器"""
    
    def __init__(self, mcp_client: Optional[MCPToolClient] = None):
        self.trajectory_extractor = TrajectoryCorpusExtractor()
        self.external_loader = ExternalCorpusLoader(mcp_client)
        self.content_processor = ContentProcessor()
        self.config = EnhancedSynthesisConfig()
    
    async def ingest_from_trajectories(self, trajectories: List[TrajectoryResult]) -> List[CorpusContent]:
        """从轨迹中导入语料"""
        logger.info(f"🔄 开始从 {len(trajectories)} 个轨迹中提取语料")
        
        # 1. 提取原始语料
        raw_corpus = await self.trajectory_extractor.extract_from_trajectories(trajectories)
        
        # 2. 预处理语料
        processed_corpus = await self.content_processor.preprocess_corpus_batch(raw_corpus)
        
        logger.info(f"✅ 轨迹语料导入完成: {len(processed_corpus)} 个高质量语料")
        return processed_corpus
    
    async def ingest_external_corpus(self, domains: List[str]) -> List[CorpusContent]:
        """导入外部语料"""
        logger.info(f"🔄 开始主动采样外部语料: {domains}")
        
        # 1. 主动采样
        raw_corpus = await self.external_loader.active_corpus_sampling(domains)
        
        # 2. 预处理语料
        processed_corpus = await self.content_processor.preprocess_corpus_batch(raw_corpus)
        
        logger.info(f"✅ 外部语料导入完成: {len(processed_corpus)} 个高质量语料")
        return processed_corpus
    
    async def ingest_mixed_corpus(self, trajectories: List[TrajectoryResult], domains: List[str]) -> List[CorpusContent]:
        """混合导入语料"""
        logger.info(f"🔄 开始混合语料导入: {len(trajectories)} 个轨迹 + {len(domains)} 个外部领域")
        
        # 并行处理轨迹和外部语料
        tasks = [
            self.ingest_from_trajectories(trajectories),
            self.ingest_external_corpus(domains)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_corpus = []
        for result in results:
            if isinstance(result, list):
                all_corpus.extend(result)
            else:
                logger.error(f"❌ 语料导入任务失败: {result}")
        
        logger.info(f"✅ 混合语料导入完成: 总计 {len(all_corpus)} 个高质量语料")
        return all_corpus