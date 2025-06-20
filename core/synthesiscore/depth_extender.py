#!/usr/bin/env python3
"""
Depth Extender - 深度扩展器
基于TaskCraft算法，实现原子任务的深度优先扩展
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
    AtomicTask, ExtendedTask, SupersetInfo, TaskDifficulty, 
    TaskType, EnhancedSynthesisConfig, generate_task_id
)

logger = logging.getLogger(__name__)


class SupersetSearcher:
    """超集搜索器 - 寻找原子任务答案的超集"""
    
    def __init__(self, llm_client: LLMClient, mcp_client: Optional[MCPToolClient] = None):
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.config = EnhancedSynthesisConfig()
    
    async def backward_search_superset(self, atomic_task: AtomicTask) -> List[SupersetInfo]:
        """反向搜索超集信息"""
        logger.debug(f"🔍 开始为原子任务搜索超集: {atomic_task.task_id}")
        
        try:
            # 1. 生成搜索查询
            search_queries = await self._generate_search_queries(atomic_task)
            
            # 2. 执行搜索并收集候选超集
            candidate_supersets = []
            for query in search_queries:
                supersets = await self._search_and_extract_supersets(query, atomic_task)
                candidate_supersets.extend(supersets)
            
            # 3. 验证和排序超集
            validated_supersets = await self._validate_and_rank_supersets(candidate_supersets, atomic_task)
            
            logger.info(f"✅ 为任务 {atomic_task.task_id} 找到 {len(validated_supersets)} 个有效超集")
            return validated_supersets
            
        except Exception as e:
            logger.error(f"❌ 超集搜索失败 {atomic_task.task_id}: {e}")
            return []
    
    async def _generate_search_queries(self, atomic_task: AtomicTask) -> List[str]:
        """生成搜索查询"""
        
        query_prompt = f"""
基于以下原子任务，生成搜索查询来寻找包含答案的更大范围信息（超集）：

原子任务问题: {atomic_task.question}
原子任务答案: {atomic_task.golden_answer}

示例：
- 如果答案是"某首歌"，超集可能是"专辑"、"歌手的所有作品"
- 如果答案是"某个城市"，超集可能是"国家"、"地区"
- 如果答案是"某个数值"，超集可能是"完整统计表"、"年度报告"

请生成3-5个搜索查询，用于寻找包含该答案的更大信息集合：

返回JSON格式：
{{
    "search_queries": [
        "查询1: 寻找包含答案的更大类别",
        "查询2: 寻找答案所属的集合",
        "查询3: 寻找相关的上级概念"
    ]
}}
"""
        
        try:
            response = await self.llm_client.generate_reasoning(
                task_description=query_prompt,
                available_tools=[],
                execution_context={"mode": "superset_query_generation"}
            )
            
            return self._parse_search_queries(response)
            
        except Exception as e:
            logger.error(f"❌ 生成搜索查询失败: {e}")
            return [f"{atomic_task.golden_answer} 相关信息"]
    
    def _parse_search_queries(self, response: Dict[str, Any]) -> List[str]:
        """解析搜索查询响应"""
        try:
            thinking = response.get('thinking', '{}')
            
            if thinking.strip().startswith('{'):
                query_data = json.loads(thinking)
            else:
                json_match = re.search(r'\{.*\}', thinking, re.DOTALL)
                if json_match:
                    query_data = json.loads(json_match.group())
                else:
                    return []
            
            return query_data.get('search_queries', [])
            
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"❌ 解析搜索查询失败: {e}")
            return []
    
    async def _search_and_extract_supersets(self, query: str, atomic_task: AtomicTask) -> List[SupersetInfo]:
        """搜索并提取超集信息"""
        if not self.mcp_client:
            logger.warning("⚠️ MCP客户端未配置，无法执行搜索")
            return []
        
        try:
            # 执行搜索
            search_result = await self.mcp_client.call_tool("deepsearch", {
                "query": query,
                "max_results": self.config.DEPTH_EXTENSION_CONFIG['max_search_results_per_query']
            })
            
            if not search_result or 'results' not in search_result:
                return []
            
            # 从搜索结果中提取超集信息
            supersets = []
            for result in search_result['results']:
                superset_info = await self._extract_superset_from_result(result, atomic_task, query)
                if superset_info:
                    supersets.append(superset_info)
            
            return supersets
            
        except Exception as e:
            logger.error(f"❌ 搜索执行失败 '{query}': {e}")
            return []
    
    async def _extract_superset_from_result(self, search_result: Dict[str, Any], 
                                          atomic_task: AtomicTask, query: str) -> Optional[SupersetInfo]:
        """从搜索结果中提取超集信息"""
        
        extraction_prompt = f"""
分析以下搜索结果，判断是否包含原子任务答案的超集信息：

原子任务答案: {atomic_task.golden_answer}
搜索查询: {query}

搜索结果:
标题: {search_result.get('title', '')}
摘要: {search_result.get('snippet', '')}
URL: {search_result.get('url', '')}

请判断：
1. 这个搜索结果是否包含原子任务答案？
2. 是否存在包含该答案的更大信息集合？
3. 该集合与答案的关系是什么？

返回JSON格式：
{{
    "contains_answer": true/false,
    "superset_info": {{
        "identifier": "超集标识符（如专辑名、国家名等）",
        "relation": "与原答案的关系描述",
        "confidence": 0.0-1.0,
        "reasoning": "判断理由"
    }}
}}
"""
        
        try:
            response = await self.llm_client.generate_reasoning(
                task_description=extraction_prompt,
                available_tools=[],
                execution_context={"mode": "superset_extraction"}
            )
            
            result_data = self._parse_superset_extraction(response)
            
            if (result_data.get('contains_answer', False) and 
                result_data.get('superset_info', {}).get('confidence', 0.0) > 0.6):
                
                superset_data = result_data['superset_info']
                return SupersetInfo(
                    identifier=superset_data['identifier'],
                    relation=superset_data['relation'],
                    search_query=query,
                    confidence=superset_data['confidence'],
                    source_urls=[search_result.get('url', '')],
                    validation_passed=False  # 需要后续验证
                )
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 超集提取失败: {e}")
            return None
    
    def _parse_superset_extraction(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """解析超集提取响应"""
        try:
            thinking = response.get('thinking', '{}')
            
            if thinking.strip().startswith('{'):
                return json.loads(thinking)
            else:
                json_match = re.search(r'\{.*\}', thinking, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                else:
                    return {"contains_answer": False}
                    
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"❌ 解析超集提取响应失败: {e}")
            return {"contains_answer": False}
    
    async def _validate_and_rank_supersets(self, candidate_supersets: List[SupersetInfo], 
                                         atomic_task: AtomicTask) -> List[SupersetInfo]:
        """验证和排序超集"""
        if not candidate_supersets:
            return []
        
        validated_supersets = []
        
        for superset in candidate_supersets:
            try:
                # 验证超集的有效性
                is_valid = await self._validate_superset_relationship(superset, atomic_task)
                
                if is_valid:
                    superset.validation_passed = True
                    validated_supersets.append(superset)
                
            except Exception as e:
                logger.error(f"❌ 超集验证失败: {e}")
                continue
        
        # 按置信度排序
        validated_supersets.sort(key=lambda x: x.confidence, reverse=True)
        
        # 返回最多3个高质量超集
        return validated_supersets[:3]
    
    async def _validate_superset_relationship(self, superset: SupersetInfo, atomic_task: AtomicTask) -> bool:
        """验证超集关系的有效性"""
        
        validation_prompt = f"""
验证以下超集关系是否有效：

原子任务答案: {atomic_task.golden_answer}
超集标识符: {superset.identifier}
关系描述: {superset.relation}

验证标准:
1. 超集确实包含原子任务答案
2. 存在唯一的从超集到答案的映射关系
3. 超集比原答案包含更多信息
4. 可以基于超集生成有意义的扩展问题

请返回验证结果 (true/false) 和理由。
"""
        
        try:
            response = await self.llm_client.generate_reasoning(
                task_description=validation_prompt,
                available_tools=[],
                execution_context={"mode": "superset_validation"}
            )
            
            thinking = response.get('thinking', '').lower()
            return 'true' in thinking and 'valid' in thinking
            
        except Exception as e:
            logger.error(f"❌ 超集关系验证失败: {e}")
            return False


class IntermediateTaskGenerator:
    """中间任务生成器 - 基于超集生成中间扩展任务"""
    
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.config = EnhancedSynthesisConfig()
    
    async def generate_intermediate_task(self, superset_info: SupersetInfo, 
                                       source_task: AtomicTask) -> Optional[Dict[str, Any]]:
        """生成中间任务"""
        logger.debug(f"🔄 生成中间任务: {superset_info.identifier}")
        
        try:
            intermediate_prompt = f"""
基于以下信息生成一个中间扩展任务：

原子任务:
- 问题: {source_task.question}
- 答案: {source_task.golden_answer}

超集信息:
- 标识符: {superset_info.identifier}
- 关系: {superset_info.relation}
- 置信度: {superset_info.confidence}

要求生成一个中间任务，该任务：
1. 比原子任务更复杂（需要更多步骤）
2. 答案包含或指向原子任务的答案
3. 需要使用搜索等工具获取超集信息
4. 具有明确的执行路径

返回JSON格式：
{{
    "intermediate_question": "扩展后的问题",
    "intermediate_answer": "扩展后的答案",
    "execution_steps": [
        "步骤1: 具体的执行步骤",
        "步骤2: ...",
        "步骤3: ..."
    ],
    "required_tools": ["tool1", "tool2"],
    "complexity_increase": "复杂度提升说明"
}}
"""
            
            response = await self.llm_client.generate_reasoning(
                task_description=intermediate_prompt,
                available_tools=[],
                execution_context={"mode": "intermediate_task_generation"}
            )
            
            return self._parse_intermediate_task_response(response)
            
        except Exception as e:
            logger.error(f"❌ 中间任务生成失败: {e}")
            return None
    
    def _parse_intermediate_task_response(self, response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析中间任务生成响应"""
        try:
            thinking = response.get('thinking', '{}')
            
            if thinking.strip().startswith('{'):
                task_data = json.loads(thinking)
            else:
                json_match = re.search(r'\{.*\}', thinking, re.DOTALL)
                if json_match:
                    task_data = json.loads(json_match.group())
                else:
                    return None
            
            # 验证必要字段
            required_fields = ['intermediate_question', 'intermediate_answer', 'execution_steps', 'required_tools']
            if all(field in task_data for field in required_fields):
                return task_data
            else:
                return None
                
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"❌ 解析中间任务响应失败: {e}")
            return None


class TaskMerger:
    """任务合并器 - 将原子任务与中间任务合并"""
    
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.config = EnhancedSynthesisConfig()
    
    async def merge_tasks(self, source_task: AtomicTask, 
                         intermediate_tasks: List[Dict[str, Any]], 
                         superset_chain: List[SupersetInfo]) -> Optional[ExtendedTask]:
        """合并任务生成扩展任务"""
        logger.debug(f"🔗 合并任务: {source_task.task_id}")
        
        if not intermediate_tasks:
            return None
        
        try:
            # 构建最终的扩展问题
            final_question = await self._build_final_question(source_task, intermediate_tasks, superset_chain)
            
            # 构建最终答案
            final_answer = await self._build_final_answer(source_task, intermediate_tasks)
            
            # 确定复杂度和工具需求
            complexity_score = self._calculate_complexity_score(intermediate_tasks)
            expected_tools = self._extract_required_tools(intermediate_tasks)
            difficulty_level = self._determine_difficulty_level(len(superset_chain), len(expected_tools))
            
            # 创建扩展任务
            extended_task = ExtendedTask(
                task_id=generate_task_id(TaskType.DEPTH_EXTENDED, source_task.content_identifier),
                question=final_question,
                golden_answer=final_answer,
                hop_level=len(superset_chain),
                source_atomic_task=source_task.task_id,
                intermediate_steps=superset_chain,
                expected_tools=expected_tools,
                difficulty_level=difficulty_level,
                complexity_score=complexity_score
            )
            
            logger.info(f"✅ 任务合并完成: {extended_task.task_id} (跳跃级别: {len(superset_chain)})")
            return extended_task
            
        except Exception as e:
            logger.error(f"❌ 任务合并失败: {e}")
            return None
    
    async def _build_final_question(self, source_task: AtomicTask, 
                                   intermediate_tasks: List[Dict[str, Any]], 
                                   superset_chain: List[SupersetInfo]) -> str:
        """构建最终扩展问题"""
        
        build_prompt = f"""
基于以下信息构建一个完整的扩展问题：

原子任务问题: {source_task.question}

中间任务序列:
{chr(10).join(f"- {task['intermediate_question']}" for task in intermediate_tasks)}

超集链条:
{chr(10).join(f"- {step.identifier} ({step.relation})" for step in superset_chain)}

要求构建一个问题，该问题：
1. 包含完整的推理链条
2. 比原子任务更复杂但仍可执行
3. 答案最终指向原子任务的答案
4. 表述清晰、逻辑连贯

返回扩展后的问题文本。
"""
        
        try:
            response = await self.llm_client.generate_reasoning(
                task_description=build_prompt,
                available_tools=[],
                execution_context={"mode": "final_question_building"}
            )
            
            return response.get('thinking', '').strip() or source_task.question
            
        except Exception as e:
            logger.error(f"❌ 构建最终问题失败: {e}")
            return source_task.question
    
    async def _build_final_answer(self, source_task: AtomicTask, 
                                 intermediate_tasks: List[Dict[str, Any]]) -> str:
        """构建最终答案"""
        
        # 简单策略：使用最后一个中间任务的答案，如果存在的话
        if intermediate_tasks:
            return intermediate_tasks[-1].get('intermediate_answer', source_task.golden_answer)
        else:
            return source_task.golden_answer
    
    def _calculate_complexity_score(self, intermediate_tasks: List[Dict[str, Any]]) -> float:
        """计算复杂度分数"""
        base_score = 1.0  # 原子任务基础分数
        
        # 每个中间任务增加复杂度
        for task in intermediate_tasks:
            steps_count = len(task.get('execution_steps', []))
            tools_count = len(task.get('required_tools', []))
            base_score += 0.3 + (steps_count * 0.1) + (tools_count * 0.2)
        
        return min(base_score / 5.0, 1.0)  # 标准化到0-1范围
    
    def _extract_required_tools(self, intermediate_tasks: List[Dict[str, Any]]) -> List[str]:
        """提取所需工具"""
        all_tools = set()
        
        for task in intermediate_tasks:
            tools = task.get('required_tools', [])
            all_tools.update(tools)
        
        return list(all_tools)
    
    def _determine_difficulty_level(self, hop_count: int, tool_count: int) -> TaskDifficulty:
        """确定难度级别"""
        if hop_count == 1 and tool_count <= 2:
            return TaskDifficulty.MEDIUM
        elif hop_count <= 2 and tool_count <= 3:
            return TaskDifficulty.MEDIUM
        else:
            return TaskDifficulty.COMPLEX


class DepthExtender:
    """深度扩展器 - 统一的深度扩展接口"""
    
    def __init__(self, llm_client: LLMClient, mcp_client: Optional[MCPToolClient] = None):
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.superset_searcher = SupersetSearcher(llm_client, mcp_client)
        self.intermediate_generator = IntermediateTaskGenerator(llm_client)
        self.task_merger = TaskMerger(llm_client)
        self.config = EnhancedSynthesisConfig()
    
    async def extend_atomic_task(self, atomic_task: AtomicTask) -> List[ExtendedTask]:
        """扩展单个原子任务"""
        logger.info(f"🚀 开始深度扩展原子任务: {atomic_task.task_id}")
        
        try:
            extended_tasks = []
            current_task = atomic_task
            superset_chain = []
            
            max_hops = self.config.DEPTH_EXTENSION_CONFIG['max_hops']
            
            for hop in range(1, max_hops + 1):
                logger.debug(f"🔄 执行第 {hop} 跳扩展")
                
                # 1. 搜索超集
                supersets = await self.superset_searcher.backward_search_superset(current_task)
                
                if not supersets:
                    logger.info(f"⚠️ 第 {hop} 跳未找到有效超集，停止扩展")
                    break
                
                # 选择最佳超集
                best_superset = supersets[0]
                superset_chain.append(best_superset)
                
                # 2. 生成中间任务
                intermediate_task = await self.intermediate_generator.generate_intermediate_task(
                    best_superset, atomic_task
                )
                
                if not intermediate_task:
                    logger.warning(f"⚠️ 第 {hop} 跳中间任务生成失败")
                    break
                
                # 3. 验证中间任务质量
                if not await self._validate_intermediate_task_quality(intermediate_task, atomic_task):
                    logger.warning(f"⚠️ 第 {hop} 跳中间任务质量不符合要求")
                    break
                
                # 4. 合并生成扩展任务
                extended_task = await self.task_merger.merge_tasks(
                    atomic_task, [intermediate_task], superset_chain.copy()
                )
                
                if extended_task:
                    extended_tasks.append(extended_task)
                    logger.info(f"✅ 第 {hop} 跳扩展任务生成成功: {extended_task.task_id}")
                else:
                    logger.warning(f"⚠️ 第 {hop} 跳任务合并失败")
                    break
            
            logger.info(f"✅ 原子任务 {atomic_task.task_id} 深度扩展完成，生成 {len(extended_tasks)} 个扩展任务")
            return extended_tasks
            
        except Exception as e:
            logger.error(f"❌ 深度扩展失败 {atomic_task.task_id}: {e}")
            return []
    
    async def batch_extend_atomic_tasks(self, atomic_tasks: List[AtomicTask]) -> List[ExtendedTask]:
        """批量扩展原子任务"""
        logger.info(f"🔄 开始批量深度扩展 {len(atomic_tasks)} 个原子任务")
        
        all_extended_tasks = []
        
        # 使用信号量控制并发
        semaphore = asyncio.Semaphore(self.config.ATOMIC_GENERATION_CONFIG['parallel_workers'])
        
        async def extend_single_task(task):
            async with semaphore:
                return await self.extend_atomic_task(task)
        
        results = await asyncio.gather(
            *[extend_single_task(task) for task in atomic_tasks],
            return_exceptions=True
        )
        
        for i, result in enumerate(results):
            if isinstance(result, list):
                all_extended_tasks.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"❌ 任务扩展异常 {atomic_tasks[i].task_id}: {result}")
        
        logger.info(f"✅ 批量深度扩展完成，总计生成 {len(all_extended_tasks)} 个扩展任务")
        return all_extended_tasks
    
    async def _validate_intermediate_task_quality(self, intermediate_task: Dict[str, Any], 
                                                source_task: AtomicTask) -> bool:
        """验证中间任务质量"""
        try:
            # 基本质量检查
            question = intermediate_task.get('intermediate_question', '')
            answer = intermediate_task.get('intermediate_answer', '')
            steps = intermediate_task.get('execution_steps', [])
            tools = intermediate_task.get('required_tools', [])
            
            # 检查基本完整性
            if not question or not answer or len(steps) < 2:
                return False
            
            # 检查复杂度提升
            if len(question.split()) <= len(source_task.question.split()) + 5:
                return False
            
            # 检查工具需求
            if not tools:
                return False
            
            # 检查答案关联性
            if source_task.golden_answer.lower() not in answer.lower():
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 中间任务质量验证失败: {e}")
            return False
    
    async def get_extension_statistics(self, extended_tasks: List[ExtendedTask]) -> Dict[str, Any]:
        """获取扩展统计信息"""
        if not extended_tasks:
            return {"total_extended_tasks": 0}
        
        # 按跳跃级别统计
        hop_distribution = {}
        complexity_scores = []
        source_tasks = set()
        
        for task in extended_tasks:
            hop_level = task.hop_level
            hop_distribution[hop_level] = hop_distribution.get(hop_level, 0) + 1
            complexity_scores.append(task.complexity_score)
            source_tasks.add(task.source_atomic_task)
        
        return {
            "total_extended_tasks": len(extended_tasks),
            "hop_distribution": hop_distribution,
            "average_complexity_score": sum(complexity_scores) / len(complexity_scores),
            "max_hop_level": max(task.hop_level for task in extended_tasks),
            "unique_source_tasks": len(source_tasks),
            "extension_efficiency": len(extended_tasks) / len(source_tasks) if source_tasks else 0.0
        }