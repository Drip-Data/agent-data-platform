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
from .tool_validator import ToolValidator

logger = logging.getLogger(__name__)


def clean_json_string(json_str: str) -> str:
    """清理JSON字符串，修复常见格式错误"""
    import re
    
    # 1. 移除重复的content_identifier键
    pattern = r'"content_identifier"\s*:\s*"[^"]*"'
    matches = list(re.finditer(pattern, json_str))
    
    if len(matches) > 1:
        # 如果有多个匹配，保留第一个，删除其他的
        offset = 0
        for i in range(1, len(matches)):
            match = matches[i]
            start = match.start() - offset
            end = match.end() - offset
            
            # 检查前面是否有逗号，如果有，一起删除
            check_start = max(0, start - 10)
            prefix = json_str[check_start:start]
            if ',' in prefix:
                comma_pos = prefix.rfind(',')
                start = check_start + comma_pos
            
            json_str = json_str[:start] + json_str[end:]
            offset += (end - start)
    
    # 2. 修复缺失逗号的问题
    # 查找 },\s*{} 或 },\s*\n\s*{} 这样的模式，并在}后添加逗号
    json_str = re.sub(r'(\})\s*(\{)', r'\1,\2', json_str)
    
    # 3. 修复 "key": "value"\n "key2" 这样缺失逗号的模式
    json_str = re.sub(r'("\w+":\s*"[^"]*")\s*\n\s*(")', r'\1,\n            \2', json_str)
    json_str = re.sub(r'("\w+":\s*[0-9.]+)\s*\n\s*(")', r'\1,\n            \2', json_str)
    
    # 4. 修复对象末尾多余逗号的问题
    json_str = re.sub(r',\s*\}', '}', json_str)
    json_str = re.sub(r',\s*\]', ']', json_str)
    
    return json_str


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
            
            # 使用LLM进行内容生成 - 通过summary方法获取原始响应
            raw_response = await self.llm_client.generate_task_summary(
                task_description=extraction_prompt,
                steps=[],
                final_outputs=[]
            )
            
            # 解析LLM响应
            conclusions = self._parse_raw_conclusion_response(raw_response, corpus_content)
            
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
    
    def _parse_raw_conclusion_response(self, raw_response: str, corpus_content: CorpusContent) -> List[TaskConclusion]:
        """解析原始结论提取响应"""
        try:
            logger.debug(f"🔍 开始解析响应: {raw_response[:200]}...")
            
            # 尝试直接解析JSON响应
            response_clean = raw_response.strip()
            
            # 首先尝试直接解析整个响应为JSON
            conclusion_data = None
            try:
                conclusion_data = json.loads(response_clean)
                if 'conclusions' in conclusion_data:
                    logger.debug("✅ 直接解析JSON成功")
                else:
                    conclusion_data = None
            except json.JSONDecodeError as e:
                logger.debug(f"❌ 直接JSON解析失败: {e}")
                pass
            
            # 如果直接解析失败，尝试从代码块中提取
            if not conclusion_data:
                # 尝试从markdown代码块提取
                pattern = r'```json\s*(\{.*?\})\s*```'
                match = re.search(pattern, response_clean, re.DOTALL)
                if match:
                    json_content = match.group(1)
                    logger.debug(f"📋 提取到JSON内容: {json_content[:200]}...")
                    
                    # 清理JSON字符串
                    json_content = clean_json_string(json_content)
                    logger.debug(f"🧹 清理后的JSON内容: {json_content[:200]}...")
                    
                    try:
                        conclusion_data = json.loads(json_content)
                        if 'conclusions' in conclusion_data:
                            logger.debug(f"✅ 使用markdown模式提取JSON成功")
                        else:
                            logger.warning(f"⚠️ JSON中没有conclusions字段")
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ Markdown JSON解析失败: {e}")
                        logger.error(f"失败的JSON内容: {json_content}")
                
                # 如果markdown失败，尝试普通代码块
                if not conclusion_data:
                    pattern = r'```\s*(\{.*?\})\s*```'
                    match = re.search(pattern, response_clean, re.DOTALL)
                    if match:
                        json_content = clean_json_string(match.group(1))
                        try:
                            conclusion_data = json.loads(json_content)
                            if 'conclusions' in conclusion_data:
                                logger.debug(f"✅ 使用普通代码块提取JSON成功")
                        except json.JSONDecodeError as e:
                            logger.error(f"❌ 普通代码块JSON解析失败: {e}")
            
            # 如果还是没有找到，尝试查找包含conclusions的任何JSON结构
            if not conclusion_data:
                # 查找包含"conclusions"关键字的位置，然后向前和向后寻找完整的JSON
                conclusions_pos = response_clean.find('"conclusions"')
                if conclusions_pos > 0:
                    # 向前找到最近的 {
                    start_pos = response_clean.rfind('{', 0, conclusions_pos)
                    if start_pos >= 0:
                        # 从这个位置开始尝试解析JSON
                        for end_pos in range(len(response_clean), start_pos, -1):
                            try:
                                json_candidate = response_clean[start_pos:end_pos]
                                conclusion_data = json.loads(json_candidate)
                                if 'conclusions' in conclusion_data:
                                    logger.debug("✅ 通过位置搜索找到JSON")
                                    break
                            except json.JSONDecodeError:
                                continue
            
            if not conclusion_data or 'conclusions' not in conclusion_data:
                logger.warning(f"⚠️ 无法解析结论响应: {corpus_content.corpus_id}")
                logger.debug(f"完整响应内容: {raw_response}")
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
            
            logger.debug(f"✅ 成功解析 {len(conclusions)} 个结论")
            return conclusions
            
        except (json.JSONDecodeError, KeyError, Exception) as e:
            logger.error(f"❌ 解析结论响应失败: {e}")
            logger.debug(f"失败的响应内容: {raw_response}")
            return []
    
    def _parse_conclusion_response(self, response: Dict[str, Any], corpus_content: CorpusContent) -> List[TaskConclusion]:
        """解析结论提取响应（向后兼容）"""
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
基于以下结论，生成需要真实工具调用的原子任务问题：

结论: {conclusion.conclusion}
关系: {conclusion.relationship}
内容标识符: {conclusion.content_identifier}

⚠️ 关键要求 - TaskCraft原则：
1. 问题必须是原子性的（不可再分的单一问题）
2. 问题必须需要多步骤工具调用（搜索+分析+验证等）
3. 不能是简单的事实查询，必须涉及推理和计算
4. 工具需求应该是现实存在的（如web_search, python_executor, deepsearch, browser_navigator等）
5. 任务应该测试Agent的工具组合使用能力

❌ 避免生成：
- 简单事实查询："X的名称是什么？"
- 过于具体的工具：["get_specific_database_name"]
- 直接答案问题：答案直接在内容中

✅ 应该生成类似：
- "分析并比较不同向量数据库的性能特点，推荐最适合长期记忆存储的解决方案"
- "编写代码验证特定技术方案的可行性，并生成测试报告"
- "搜索相关技术文档，提取关键信息并构建知识结构图"

请生成1-2个符合要求的问题，以JSON格式返回：
{{
    "questions": [
        {{
            "question": "需要多工具协作的复杂问题",
            "answer": "预期的分析结果或推荐方案",
            "required_tools": ["web_search", "python_executor", "deepsearch"],
            "reasoning": "为什么这个问题需要工具调用且具有挑战性",
            "complexity_score": 0.8
        }}
    ]
}}
"""
        
        try:
            # 使用LLM进行内容生成 - 通过summary方法获取原始响应
            raw_response = await self.llm_client.generate_task_summary(
                task_description=question_prompt,
                steps=[],
                final_outputs=[]
            )
            
            return self._parse_raw_question_response(raw_response, conclusion)
            
        except Exception as e:
            logger.error(f"❌ 问题生成失败: {e}")
            return []
    
    def _parse_raw_question_response(self, raw_response: str, conclusion: TaskConclusion) -> List[Dict[str, Any]]:
        """解析原始问题生成响应"""
        try:
            # 尝试直接解析JSON响应
            response_clean = raw_response.strip()
            
            # 尝试多种JSON提取方式
            json_patterns = [
                r'```json\s*(\{.*?\})\s*```',  # markdown代码块
                r'```\s*(\{.*?\})\s*```',      # 普通代码块  
                r'(\{.*?"questions".*?\})',    # 包含questions的JSON
                r'(\{.*?\})',                  # 任何JSON对象
            ]
            
            question_data = None
            for pattern in json_patterns:
                match = re.search(pattern, response_clean, re.DOTALL)
                if match:
                    try:
                        question_data = json.loads(match.group(1))
                        if 'questions' in question_data:
                            break
                    except json.JSONDecodeError:
                        continue
            
            if not question_data or 'questions' not in question_data:
                return []
            
            questions = []
            for item in question_data.get('questions', []):
                # 验证任务质量
                if self._validate_task_quality(item):
                    question_info = {
                        "question": item['question'],
                        "answer": item['answer'],
                        "required_tools": item.get('required_tools', []),
                        "reasoning": item.get('reasoning', ''),
                        "complexity_score": item.get('complexity_score', 0.5),
                        "source_conclusion": conclusion,
                        "content_identifier": conclusion.content_identifier
                    }
                    questions.append(question_info)
                else:
                    logger.debug(f"⚠️ 任务质量不符合要求，跳过: {item.get('question', '')}")
            
            return questions
            
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"❌ 解析问题响应失败: {e}")
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
    
    def _validate_task_quality(self, task_item: Dict[str, Any]) -> bool:
        """验证任务质量是否符合TaskCraft原则"""
        try:
            question = task_item.get('question', '')
            required_tools = task_item.get('required_tools', [])
            complexity_score = task_item.get('complexity_score', 0.0)
            
            # 检查1: 避免简单事实查询
            simple_patterns = [
                r'.*的名称是什么',
                r'什么是.*',
                r'.*叫什么',
                r'.*是什么.*',
                r'.*标识符是.*'
            ]
            
            for pattern in simple_patterns:
                if re.search(pattern, question, re.IGNORECASE):
                    logger.debug(f"❌ 拒绝简单事实查询: {question}")
                    return False
            
            # 检查2: 必须有现实的工具需求
            realistic_tools = {
                'web_search', 'python_executor', 'deepsearch', 'browser_navigator', 
                'browser_navigator', 'file_reader', 'data_processor',
                'search_engine', 'code_executor', 'document_analyzer'
            }
            
            if not any(tool in realistic_tools for tool in required_tools):
                logger.debug(f"❌ 工具需求不现实: {required_tools}")
                return False
            
            # 检查3: 复杂度要求
            if complexity_score < 0.6:
                logger.debug(f"❌ 复杂度不足: {complexity_score}")
                return False
            
            # 检查4: 需要多个工具协作
            if len(required_tools) < 2:
                logger.debug(f"❌ 工具数量不足: {len(required_tools)}")
                return False
            
            # 检查5: 问题长度合理
            if len(question) < 30:
                logger.debug(f"❌ 问题过短: {len(question)}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 任务质量验证失败: {e}")
            return False


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
请评估以下问题是否适合作为AI Agent任务：

问题: {question_info['question']}
预期答案: {question_info['answer']}
所需工具: {question_info.get('required_tools', [])}

评估标准（相对宽松）:
1. 核心焦点：问题有明确的核心目标
2. 工具需求：需要使用多个工具协作完成
3. 可执行性：Agent能够通过工具调用完成此任务
4. 结果导向：有明确的输出形式或目标

注意：分析类、比较类、设计类任务都是可接受的，只要它们需要工具协作且有明确目标。

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
    "reasoning": "评估理由",
    "suggested_improvements": ["改进建议"]
}}
"""
        
        try:
            # 使用LLM进行内容生成 - 通过summary方法获取原始响应
            raw_response = await self.llm_client.generate_task_summary(
                task_description=atomicity_prompt,
                steps=[],
                final_outputs=[]
            )
            
            verification_result = self._parse_raw_atomicity_response(raw_response)
            
            # 只依赖分数，不强制要求is_atomic为true（因为LLM对复杂任务过于保守）
            if verification_result.get('atomicity_score', 0.0) >= self.config.ATOMIC_GENERATION_CONFIG['atomicity_verification_threshold']:
                
                # 验证并修正工具列表
                suggested_tools = question_info.get('required_tools', [])
                validated_tools = await self.tool_validator.filter_available_tools(suggested_tools)
                
                # 创建原子任务
                atomic_task = AtomicTask(
                    task_id=generate_task_id(TaskType.ATOMIC, question_info['content_identifier']),
                    question=question_info['question'],
                    golden_answer=question_info['answer'],
                    content_identifier=question_info['content_identifier'],
                    source_corpus=question_info.get('source_conclusion').content_identifier if question_info.get('source_conclusion') else '',
                    verification_score=verification_result.get('atomicity_score', 0.0),
                    required_tools=validated_tools,
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
    
    def _parse_raw_atomicity_response(self, raw_response: str) -> Dict[str, Any]:
        """解析原始原子性验证响应"""
        try:
            logger.debug(f"🔍 解析原子性验证响应")
            
            # 尝试直接解析JSON响应
            response_clean = raw_response.strip()
            
            # 首先尝试直接解析整个响应为JSON
            atomicity_data = None
            try:
                atomicity_data = json.loads(response_clean)
                if 'is_atomic' in atomicity_data:
                    pass
                    return atomicity_data
            except json.JSONDecodeError:
                pass
            
            # 如果直接解析失败，尝试从代码块中提取
            if not atomicity_data:
                # 尝试从markdown代码块提取
                pattern = r'```json\s*(\{.*?\})\s*```'
                match = re.search(pattern, response_clean, re.DOTALL)
                if match:
                    json_content = clean_json_string(match.group(1))
                    try:
                        atomicity_data = json.loads(json_content)
                        if 'is_atomic' in atomicity_data:
                            return atomicity_data
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ Markdown原子性JSON解析失败: {e}")
                
                # 如果markdown失败，尝试普通代码块
                if not atomicity_data:
                    pattern = r'```\s*(\{.*?\})\s*```'
                    match = re.search(pattern, response_clean, re.DOTALL)
                    if match:
                        json_content = clean_json_string(match.group(1))
                        try:
                            atomicity_data = json.loads(json_content)
                            if 'is_atomic' in atomicity_data:
                                return atomicity_data
                        except json.JSONDecodeError as e:
                            logger.error(f"❌ 普通代码块原子性JSON解析失败: {e}")
            
            # 如果都失败了，返回默认值
            logger.warning(f"⚠️ 无法解析原子性验证响应，使用默认值")
            return {"is_atomic": False, "atomicity_score": 0.0}
            
        except Exception as e:
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
        self.tool_validator = ToolValidator(mcp_client)
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