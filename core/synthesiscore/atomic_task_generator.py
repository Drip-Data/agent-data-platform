#!/usr/bin/env python3
"""
Atomic Task Generator - 原子任务生成器
基于TaskCraft算法，实现从语料到原子任务的自动生成
"""

import asyncio
import json
import logging
import re
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import asdict

from core.interfaces import TrajectoryResult
from core.llm_client import LLMClient
from core.toolscore.mcp_client import MCPToolClient
from .enhanced_interfaces import (
    CorpusContent, AtomicTask, TaskConclusion, TaskDifficulty, 
    TaskType, EnhancedSynthesisConfig, generate_task_id
)

logger = logging.getLogger(__name__)


class ConclusionExtractor:
    """结论提取器 - 从语料中提取原子结论"""
    
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.config = EnhancedSynthesisConfig()
    
    async def extract_conclusions_from_corpus(self, corpus_content: CorpusContent) -> List[TaskConclusion]:
        """从语料中提取结论"""
        logger.debug(f"🔍 开始从语料中提取结论: {corpus_content.corpus_id}")
        
        try:
            # 构建结论提取提示词
            extraction_prompt = self._build_conclusion_extraction_prompt(corpus_content)
            
            # 调用LLM进行结论提取
            response = await self.llm_client.generate_reasoning(
                task_description=extraction_prompt,
                available_tools=[]
            )
            
            # 解析LLM响应
            conclusions = self._parse_conclusion_response(response, corpus_content)
            
            logger.info(f"✅ 从语料 {corpus_content.corpus_id} 中提取了 {len(conclusions)} 个结论")
            return conclusions
            
        except Exception as e:
            logger.error(f"❌ 结论提取失败 {corpus_content.corpus_id}: {e}")
            return []
    
    def _build_conclusion_extraction_prompt(self, corpus_content: CorpusContent) -> str:
        """构建结论提取提示词"""
        
        content_preview = corpus_content.text_content[:1000] + "..." if len(corpus_content.text_content) > 1000 else corpus_content.text_content
        
        return f"""
请从以下内容中提取可以形成原子任务的关键结论。每个结论必须满足：
1. 包含具体、可验证的事实（数值、时间、名称等）
2. 具有明确的关系描述
3. 可以转换为一个不可再分的问题

内容类型: {corpus_content.content_type.value}
内容来源: {corpus_content.source}
内容片段:
{content_preview}

请以JSON格式返回结论列表，每个结论包含：
- conclusion: 结论内容
- relationship: 关系描述 (例如："X属于Y", "X的值是Y", "X发生在Y时间")
- content_identifier: 内容标识符
- confidence: 提取置信度 (0.0-1.0)

示例格式:
{{
    "conclusions": [
        {{
            "conclusion": "苹果公司的股价在2023年12月15日收盘价为198.11美元",
            "relationship": "股价-公司-时间-数值",
            "content_identifier": "stock_price_apple_20231215",
            "confidence": 0.95
        }}
    ]
}}

要求：
- 最多提取{self.config.ATOMIC_GENERATION_CONFIG['max_conclusions_per_corpus']}个结论
- 只提取具有高置信度(>0.7)的结论
- 避免重复或相似的结论
"""
    
    def _parse_conclusion_response(self, response: Dict[str, Any], corpus_content: CorpusContent) -> List[TaskConclusion]:
        """解析结论提取响应"""
        try:
            thinking = response.get('thinking', '{}')
            
            # 尝试解析JSON响应
            if thinking.strip().startswith('{'):
                conclusion_data = json.loads(thinking)
            else:
                # 如果不是JSON格式，尝试从文本中提取
                json_match = re.search(r'\{.*\}', thinking, re.DOTALL)
                if json_match:
                    conclusion_data = json.loads(json_match.group())
                else:
                    logger.warning(f"⚠️ 无法解析结论响应: {corpus_content.corpus_id}")
                    return []
            
            conclusions = []
            for item in conclusion_data.get('conclusions', []):
                if item.get('confidence', 0.0) >= self.config.ATOMIC_GENERATION_CONFIG['conclusion_extraction_confidence']:
                    conclusion = TaskConclusion(
                        conclusion=item['conclusion'],
                        relationship=item['relationship'],
                        content_identifier=item['content_identifier'],
                        extraction_confidence=item['confidence'],
                        verifiability=self._assess_verifiability(item['conclusion'])
                    )
                    conclusions.append(conclusion)
            
            return conclusions
            
        except (json.JSONDecodeError, KeyError, Exception) as e:
            logger.error(f"❌ 解析结论响应失败: {e}")
            return []
    
    def _assess_verifiability(self, conclusion: str) -> bool:
        """评估结论的可验证性"""
        # 检查是否包含具体的数值、时间、名称等可验证元素
        verifiable_patterns = [
            r'\d+\.?\d*',              # 数值
            r'\d{4}[-/]\d{1,2}[-/]\d{1,2}',  # 日期
            r'\d{1,2}:\d{2}',          # 时间
            r'[A-Z][a-z]+ [A-Z][a-z]+',  # 专有名词
            r'https?://\S+',           # URL
            r'\$\d+',                  # 货币
            r'\d+%',                   # 百分比
        ]
        
        verification_count = sum(1 for pattern in verifiable_patterns if re.search(pattern, conclusion))
        return verification_count >= 2


class QuestionGenerator:
    """问题生成器 - 将结论转换为问题"""
    
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.config = EnhancedSynthesisConfig()
    
    async def generate_questions_from_conclusions(self, conclusions: List[TaskConclusion]) -> List[Dict[str, Any]]:
        """从结论生成候选问题"""
        logger.debug(f"🔄 开始从 {len(conclusions)} 个结论生成问题")
        
        candidate_questions = []
        
        for conclusion in conclusions:
            try:
                questions = await self._generate_questions_for_conclusion(conclusion)
                candidate_questions.extend(questions)
                
            except Exception as e:
                logger.error(f"❌ 从结论生成问题失败: {e}")
                continue
        
        logger.info(f"✅ 生成了 {len(candidate_questions)} 个候选问题")
        return candidate_questions
    
    async def _generate_questions_for_conclusion(self, conclusion: TaskConclusion) -> List[Dict[str, Any]]:
        """为单个结论生成问题"""
        
        question_prompt = f"""
基于以下结论，生成相应的原子任务问题：

结论: {conclusion.conclusion}
关系: {conclusion.relationship}
内容标识符: {conclusion.content_identifier}

要求：
1. 问题必须是原子性的（不可再分的单一问题）
2. 答案应该是结论中的具体事实
3. 问题应该需要工具调用才能回答（而不是纯LLM推理）
4. 避免是非题，优先选择具体数值、名称、时间等

请生成2-3个不同角度的问题，以JSON格式返回：
{{
    "questions": [
        {{
            "question": "问题内容",
            "answer": "预期答案",
            "required_tools": ["工具1", "工具2"],
            "reasoning": "为什么这个问题是原子性的"
        }}
    ]
}}
"""
        
        try:
            response = await self.llm_client.generate_reasoning(
                task_description=question_prompt,
                available_tools=[]
            )
            
            return self._parse_question_response(response, conclusion)
            
        except Exception as e:
            logger.error(f"❌ 问题生成失败: {e}")
            return []
    
    def _parse_question_response(self, response: Dict[str, Any], conclusion: TaskConclusion) -> List[Dict[str, Any]]:
        """解析问题生成响应"""
        try:
            thinking = response.get('thinking', '{}')
            
            if thinking.strip().startswith('{'):
                question_data = json.loads(thinking)
            else:
                json_match = re.search(r'\{.*\}', thinking, re.DOTALL)
                if json_match:
                    question_data = json.loads(json_match.group())
                else:
                    return []
            
            questions = []
            for item in question_data.get('questions', []):
                question_info = {
                    "question": item['question'],
                    "answer": item['answer'],
                    "required_tools": item.get('required_tools', []),
                    "reasoning": item.get('reasoning', ''),
                    "source_conclusion": conclusion,
                    "content_identifier": conclusion.content_identifier
                }
                questions.append(question_info)
            
            return questions
            
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"❌ 解析问题响应失败: {e}")
            return []


class AtomicityVerifier:
    """原子性验证器 - 验证任务的原子性"""
    
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.config = EnhancedSynthesisConfig()
    
    async def verify_atomic_questions(self, candidate_questions: List[Dict[str, Any]]) -> List[AtomicTask]:
        """验证候选问题的原子性"""
        logger.debug(f"🔍 开始验证 {len(candidate_questions)} 个候选问题的原子性")
        
        atomic_tasks = []
        
        # 使用并发处理提高效率
        semaphore = asyncio.Semaphore(self.config.ATOMIC_GENERATION_CONFIG['parallel_workers'])
        
        async def verify_single_question(question_info):
            async with semaphore:
                return await self._verify_single_question_atomicity(question_info)
        
        verification_results = await asyncio.gather(
            *[verify_single_question(q) for q in candidate_questions],
            return_exceptions=True
        )
        
        for i, result in enumerate(verification_results):
            if isinstance(result, AtomicTask):
                atomic_tasks.append(result)
            elif isinstance(result, Exception):
                logger.error(f"❌ 问题验证异常: {candidate_questions[i].get('question', 'Unknown')}: {result}")
        
        logger.info(f"✅ 验证完成，得到 {len(atomic_tasks)} 个原子任务")
        return atomic_tasks
    
    async def _verify_single_question_atomicity(self, question_info: Dict[str, Any]) -> Optional[AtomicTask]:
        """验证单个问题的原子性"""
        
        atomicity_prompt = f"""
请严格评估以下问题是否符合原子任务的标准：

问题: {question_info['question']}
预期答案: {question_info['answer']}
所需工具: {question_info.get('required_tools', [])}

原子任务标准:
1. 不可再分：问题不能被拆分为多个独立的子问题
2. 答案唯一：有明确、唯一的正确答案
3. 工具依赖：需要使用工具才能回答，纯LLM无法解答
4. 可验证性：答案包含具体的数值、时间、名称等可验证信息

请返回JSON格式的评估结果：
{{
    "is_atomic": true/false,
    "atomicity_score": 0.0-1.0,
    "meets_criteria": {{
        "indivisible": true/false,
        "unique_answer": true/false, 
        "tool_dependent": true/false,
        "verifiable": true/false
    }},
    "reasoning": "详细评估理由",
    "suggested_improvements": ["改进建议1", "改进建议2"]
}}
"""
        
        try:
            response = await self.llm_client.generate_reasoning(
                task_description=atomicity_prompt,
                available_tools=[]
            )
            
            verification_result = self._parse_atomicity_response(response)
            
            if (verification_result.get('is_atomic', False) and 
                verification_result.get('atomicity_score', 0.0) >= self.config.ATOMIC_GENERATION_CONFIG['atomicity_verification_threshold']):
                
                # 创建原子任务
                atomic_task = AtomicTask(
                    task_id=generate_task_id(TaskType.ATOMIC, question_info['content_identifier']),
                    question=question_info['question'],
                    golden_answer=question_info['answer'],
                    content_identifier=question_info['content_identifier'],
                    source_corpus=question_info.get('source_conclusion').content_identifier if question_info.get('source_conclusion') else '',
                    verification_score=verification_result.get('atomicity_score', 0.0),
                    required_tools=question_info.get('required_tools', []),
                    difficulty_level=self._determine_difficulty_level(question_info),
                    atomicity_verified=True
                )
                
                return atomic_task
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 原子性验证失败: {e}")
            return None
    
    def _parse_atomicity_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """解析原子性验证响应"""
        try:
            thinking = response.get('thinking', '{}')
            
            if thinking.strip().startswith('{'):
                return json.loads(thinking)
            else:
                json_match = re.search(r'\{.*\}', thinking, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                else:
                    return {"is_atomic": False, "atomicity_score": 0.0}
                    
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"❌ 解析原子性验证响应失败: {e}")
            return {"is_atomic": False, "atomicity_score": 0.0}
    
    def _determine_difficulty_level(self, question_info: Dict[str, Any]) -> TaskDifficulty:
        """确定任务难度级别"""
        required_tools = question_info.get('required_tools', [])
        question_complexity = len(question_info['question'].split())
        
        if len(required_tools) <= 1 and question_complexity <= 15:
            return TaskDifficulty.SIMPLE
        elif len(required_tools) <= 2 and question_complexity <= 25:
            return TaskDifficulty.MEDIUM
        else:
            return TaskDifficulty.COMPLEX


class AtomicTaskGenerator:
    """原子任务生成器 - 统一的原子任务生成接口"""
    
    def __init__(self, llm_client: LLMClient, mcp_client: Optional[MCPToolClient] = None):
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.conclusion_extractor = ConclusionExtractor(llm_client)
        self.question_generator = QuestionGenerator(llm_client)
        self.atomicity_verifier = AtomicityVerifier(llm_client)
        self.config = EnhancedSynthesisConfig()
    
    async def generate_atomic_tasks_from_corpus(self, corpus_contents: List[CorpusContent]) -> List[AtomicTask]:
        """从语料批量生成原子任务"""
        logger.info(f"🚀 开始从 {len(corpus_contents)} 个语料生成原子任务")
        
        all_atomic_tasks = []
        
        for corpus in corpus_contents:
            try:
                tasks = await self._generate_atomic_tasks_for_single_corpus(corpus)
                all_atomic_tasks.extend(tasks)
                
            except Exception as e:
                logger.error(f"❌ 处理语料失败 {corpus.corpus_id}: {e}")
                continue
        
        logger.info(f"✅ 原子任务生成完成，总计生成 {len(all_atomic_tasks)} 个原子任务")
        return all_atomic_tasks
    
    async def _generate_atomic_tasks_for_single_corpus(self, corpus_content: CorpusContent) -> List[AtomicTask]:
        """为单个语料生成原子任务"""
        logger.debug(f"🔄 处理语料: {corpus_content.corpus_id}")
        
        start_time = time.time()
        
        try:
            # 1. 结论提取
            conclusions = await self.conclusion_extractor.extract_conclusions_from_corpus(corpus_content)
            if not conclusions:
                logger.warning(f"⚠️ 语料 {corpus_content.corpus_id} 未提取到结论")
                return []
            
            # 2. 问题生成
            candidate_questions = await self.question_generator.generate_questions_from_conclusions(conclusions)
            if not candidate_questions:
                logger.warning(f"⚠️ 语料 {corpus_content.corpus_id} 未生成候选问题")
                return []
            
            # 3. 原子性验证
            atomic_tasks = await self.atomicity_verifier.verify_atomic_questions(candidate_questions)
            
            processing_time = time.time() - start_time
            logger.info(f"✅ 语料 {corpus_content.corpus_id} 处理完成: {len(atomic_tasks)} 个原子任务 (用时 {processing_time:.2f}s)")
            
            return atomic_tasks
            
        except Exception as e:
            logger.error(f"❌ 语料处理失败 {corpus_content.corpus_id}: {e}")
            return []
    
    async def generate_atomic_tasks_from_trajectories(self, trajectories: List[TrajectoryResult]) -> List[AtomicTask]:
        """从轨迹直接生成原子任务（集成语料提取）"""
        logger.info(f"🔄 开始从 {len(trajectories)} 个轨迹生成原子任务")
        
        # 首先需要从轨迹中提取语料
        from .corpus_ingestor import CorpusIngestor
        corpus_ingestor = CorpusIngestor(self.mcp_client)
        
        # 提取语料
        corpus_contents = await corpus_ingestor.ingest_from_trajectories(trajectories)
        
        # 生成原子任务
        atomic_tasks = await self.generate_atomic_tasks_from_corpus(corpus_contents)
        
        logger.info(f"✅ 从轨迹生成原子任务完成: {len(atomic_tasks)} 个任务")
        return atomic_tasks
    
    async def validate_and_execute_atomic_task(self, atomic_task: AtomicTask) -> Dict[str, Any]:
        """验证和执行原子任务（用于质量检查）"""
        if not self.mcp_client:
            logger.warning(f"⚠️ MCP客户端未配置，无法执行任务验证: {atomic_task.task_id}")
            return {"success": False, "error": "MCP客户端未配置"}
        
        try:
            # 使用验证引擎执行任务
            from .verification_agent import TaskExecutor
            task_executor = TaskExecutor(self.llm_client, self.mcp_client)
            
            execution_result = await task_executor.execute_task_with_tools(
                atomic_task.question,
                atomic_task.golden_answer,
                timeout=self.config.VERIFICATION_CONFIG['execution_timeout_seconds']
            )
            
            # 更新任务的可执行性验证状态
            if execution_result.get('success', False) and execution_result.get('answer_correct', False):
                atomic_task.executability_verified = True
            
            return execution_result
            
        except Exception as e:
            logger.error(f"❌ 原子任务执行验证失败 {atomic_task.task_id}: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_generation_statistics(self, atomic_tasks: List[AtomicTask]) -> Dict[str, Any]:
        """获取生成统计信息"""
        if not atomic_tasks:
            return {"total_tasks": 0}
        
        # 按难度级别统计
        difficulty_stats = {
            TaskDifficulty.SIMPLE.value: 0,
            TaskDifficulty.MEDIUM.value: 0,
            TaskDifficulty.COMPLEX.value: 0
        }
        
        # 按工具使用统计
        tool_usage = {}
        verification_scores = []
        
        for task in atomic_tasks:
            difficulty_stats[task.difficulty_level.value] += 1
            verification_scores.append(task.verification_score)
            
            for tool in task.required_tools:
                tool_usage[tool] = tool_usage.get(tool, 0) + 1
        
        return {
            "total_tasks": len(atomic_tasks),
            "difficulty_distribution": difficulty_stats,
            "tool_usage": tool_usage,
            "average_verification_score": sum(verification_scores) / len(verification_scores) if verification_scores else 0.0,
            "atomicity_verified_count": sum(1 for task in atomic_tasks if task.atomicity_verified),
            "executability_verified_count": sum(1 for task in atomic_tasks if task.executability_verified),
            "unique_content_identifiers": len(set(task.content_identifier for task in atomic_tasks)),
            "unique_source_corpus": len(set(task.source_corpus for task in atomic_tasks if task.source_corpus))
        }