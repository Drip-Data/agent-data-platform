#!/usr/bin/env python3
"""
🔄 上下文流管理器 (Context Flow Manager)
解决工具间信息孤岛问题，确保数据有效传递和整合
"""

import logging
import json
import re
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class DataType(Enum):
    """数据类型枚举"""
    TEXT = "text"
    JSON = "json"
    TABLE = "table"
    URL = "url"
    CODE = "code"
    NUMBER = "number"
    FILE_PATH = "file_path"
    ERROR = "error"


class DataRelevance(Enum):
    """数据相关性枚举"""
    HIGH = "high"      # 高度相关，必须传递
    MEDIUM = "medium"  # 中等相关，建议传递
    LOW = "low"        # 低相关性，可选传递
    IRRELEVANT = "irrelevant"  # 不相关


@dataclass
class ContextData:
    """上下文数据项"""
    data_id: str
    content: Any
    data_type: DataType
    source_tool: str
    source_step: int
    timestamp: datetime
    relevance: DataRelevance = DataRelevance.MEDIUM
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = asdict(self)
        result['timestamp'] = self.timestamp.isoformat()
        result['data_type'] = self.data_type.value
        result['relevance'] = self.relevance.value
        return result


@dataclass
class DataFlow:
    """数据流定义"""
    from_tool: str
    to_tool: str
    data_mapping: Dict[str, str]  # 源字段 -> 目标字段
    transformation_rule: Optional[str] = None
    required: bool = True


class ContextFlowManager:
    """
    🔄 上下文流管理器
    
    功能：
    1. 智能提取和分类工具输出数据
    2. 建立工具间数据传递映射
    3. 确保关键信息在步骤间有效传递
    4. 提供数据相关性分析和过滤
    """
    
    def __init__(self, max_context_size: int = 1000):
        """初始化上下文流管理器"""
        self.context_store: Dict[str, ContextData] = {}
        self.data_flows: List[DataFlow] = []
        self.step_outputs: Dict[int, List[str]] = {}  # 步骤 -> 数据IDs
        self.max_context_size = max_context_size
        
        # 工具间常见数据流模式
        self.common_flows = self._initialize_common_flows()
        
        # 数据提取模式
        self.extraction_patterns = self._initialize_extraction_patterns()
        
        logger.info("🔄 ContextFlowManager initialized")
    
    def _initialize_common_flows(self) -> List[DataFlow]:
        """初始化常见的工具间数据流"""
        return [
            # 搜索 -> 代码执行
            DataFlow(
                from_tool="deepsearch", 
                to_tool="microsandbox",
                data_mapping={"search_results": "input_data"},
                transformation_rule="extract_key_facts"
            ),
            DataFlow(
                from_tool="browser_use", 
                to_tool="microsandbox",
                data_mapping={"page_content": "input_data", "extracted_data": "raw_data"},
                transformation_rule="parse_web_data"
            ),
            
            # 代码执行 -> 分析
            DataFlow(
                from_tool="microsandbox",
                to_tool="deepsearch", 
                data_mapping={"calculation_result": "query_context", "error_message": "problem_context"},
                transformation_rule="format_for_search"
            ),
            
            # 搜索 -> 浏览器
            DataFlow(
                from_tool="deepsearch",
                to_tool="browser_use",
                data_mapping={"urls": "target_urls", "search_results": "context"},
                transformation_rule="extract_urls"
            )
        ]
    
    def _initialize_extraction_patterns(self) -> Dict[str, List[str]]:
        """初始化数据提取模式"""
        return {
            "numbers": [
                r'\b\d+\.?\d*\b',  # 数字
                r'\$\d+\.?\d*',    # 价格
                r'\d+%',           # 百分比
            ],
            "urls": [
                r'https?://[^\s<>"{}|\\^`[\]]+',
                r'www\.[^\s<>"{}|\\^`[\]]+',
            ],
            "dates": [
                r'\d{4}-\d{2}-\d{2}',
                r'\d{1,2}/\d{1,2}/\d{4}',
                r'\b\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b',
            ],
            "codes": [
                r'```[\s\S]*?```',  # 代码块
                r'`[^`]+`',         # 内联代码
            ],
            "key_facts": [
                r'[A-Z][^.!?]*(?:\d+[^.!?]*)?[.!?]',  # 包含数字的关键句子
                r'(?:结果|结论|发现|显示|表明)[:：][^.!?]*[.!?]',  # 结论性语句
            ]
        }
    
    def extract_context_data(self, tool_output: str, source_tool: str, 
                           step_number: int) -> List[ContextData]:
        """
        🔍 从工具输出中提取上下文数据
        
        Args:
            tool_output: 工具输出内容
            source_tool: 源工具名称
            step_number: 步骤编号
            
        Returns:
            List[ContextData]: 提取的上下文数据列表
        """
        extracted_data = []
        current_time = datetime.now()
        
        # 1. 按数据类型提取
        for data_type, patterns in self.extraction_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, tool_output, re.MULTILINE | re.IGNORECASE)
                for i, match in enumerate(matches):
                    data_id = f"{source_tool}_{step_number}_{data_type}_{i}"
                    
                    # 确定数据类型和相关性
                    extracted_type = self._determine_data_type(match.group(), data_type)
                    relevance = self._assess_relevance(match.group(), source_tool, data_type)
                    
                    context_data = ContextData(
                        data_id=data_id,
                        content=match.group().strip(),
                        data_type=extracted_type,
                        source_tool=source_tool,
                        source_step=step_number,
                        timestamp=current_time,
                        relevance=relevance,
                        metadata={
                            "pattern_type": data_type,
                            "match_start": match.start(),
                            "match_end": match.end(),
                            "context": tool_output[max(0, match.start()-50):match.end()+50]
                        }
                    )
                    
                    extracted_data.append(context_data)
        
        # 2. 特殊数据提取
        special_data = self._extract_special_data(tool_output, source_tool, step_number)
        extracted_data.extend(special_data)
        
        # 3. 存储到上下文仓库
        for data in extracted_data:
            self.context_store[data.data_id] = data
        
        # 4. 记录步骤输出
        if step_number not in self.step_outputs:
            self.step_outputs[step_number] = []
        self.step_outputs[step_number].extend([data.data_id for data in extracted_data])
        
        logger.info(f"🔍 从 {source_tool} 步骤{step_number} 提取了 {len(extracted_data)} 个数据项")
        return extracted_data
    
    def _extract_special_data(self, output: str, source_tool: str, 
                            step_number: int) -> List[ContextData]:
        """提取特殊类型的数据"""
        special_data = []
        current_time = datetime.now()
        
        # 错误信息提取
        error_patterns = [
            r'error[:：]\s*([^\n]+)',
            r'failed[:：]\s*([^\n]+)',
            r'exception[:：]\s*([^\n]+)',
            r'错误[:：]\s*([^\n]+)',
        ]
        
        for pattern in error_patterns:
            matches = re.finditer(pattern, output, re.IGNORECASE)
            for i, match in enumerate(matches):
                data_id = f"{source_tool}_{step_number}_error_{i}"
                
                special_data.append(ContextData(
                    data_id=data_id,
                    content=match.group(1).strip(),
                    data_type=DataType.ERROR,
                    source_tool=source_tool,
                    source_step=step_number,
                    timestamp=current_time,
                    relevance=DataRelevance.HIGH,
                    metadata={"error_type": "execution_error"}
                ))
        
        # JSON数据提取
        try:
            # 尝试解析整个输出为JSON
            json_data = json.loads(output)
            data_id = f"{source_tool}_{step_number}_json_0"
            
            special_data.append(ContextData(
                data_id=data_id,
                content=json_data,
                data_type=DataType.JSON,
                source_tool=source_tool,
                source_step=step_number,
                timestamp=current_time,
                relevance=DataRelevance.HIGH,
                metadata={"json_keys": list(json_data.keys()) if isinstance(json_data, dict) else []}
            ))
        except (json.JSONDecodeError, TypeError):
            # 查找嵌入的JSON片段
            json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
            matches = re.finditer(json_pattern, output)
            for i, match in enumerate(matches):
                try:
                    json_obj = json.loads(match.group())
                    data_id = f"{source_tool}_{step_number}_json_{i}"
                    
                    special_data.append(ContextData(
                        data_id=data_id,
                        content=json_obj,
                        data_type=DataType.JSON,
                        source_tool=source_tool,
                        source_step=step_number,
                        timestamp=current_time,
                        relevance=DataRelevance.MEDIUM,
                        metadata={"embedded_json": True}
                    ))
                except json.JSONDecodeError:
                    continue
        
        return special_data
    
    def _determine_data_type(self, content: str, pattern_type: str) -> DataType:
        """确定数据类型"""
        type_mapping = {
            "numbers": DataType.NUMBER,
            "urls": DataType.URL,
            "dates": DataType.TEXT,
            "codes": DataType.CODE,
            "key_facts": DataType.TEXT,
        }
        return type_mapping.get(pattern_type, DataType.TEXT)
    
    def _assess_relevance(self, content: str, source_tool: str, pattern_type: str) -> DataRelevance:
        """评估数据相关性"""
        # 高相关性指标
        high_indicators = [
            "price", "cost", "result", "error", "failure", "success",
            "价格", "成本", "结果", "错误", "失败", "成功"
        ]
        
        # 中等相关性指标
        medium_indicators = [
            "data", "information", "value", "number", "count",
            "数据", "信息", "值", "数量", "计数"
        ]
        
        content_lower = content.lower()
        
        if any(indicator in content_lower for indicator in high_indicators):
            return DataRelevance.HIGH
        elif any(indicator in content_lower for indicator in medium_indicators):
            return DataRelevance.MEDIUM
        elif pattern_type in ["numbers", "urls", "key_facts"]:
            return DataRelevance.MEDIUM
        else:
            return DataRelevance.LOW
    
    def get_relevant_context(self, target_tool: str, current_step: int, 
                           relevance_threshold: DataRelevance = DataRelevance.MEDIUM) -> Dict[str, Any]:
        """
        📊 获取与目标工具相关的上下文数据
        
        Args:
            target_tool: 目标工具名称
            current_step: 当前步骤编号
            relevance_threshold: 相关性阈值
            
        Returns:
            Dict[str, Any]: 相关的上下文数据
        """
        relevant_data = {}
        
        # 1. 获取前几步的高相关性数据
        relevance_order = [DataRelevance.HIGH, DataRelevance.MEDIUM, DataRelevance.LOW]
        threshold_index = relevance_order.index(relevance_threshold)
        
        for step in range(max(0, current_step - 5), current_step):
            if step in self.step_outputs:
                for data_id in self.step_outputs[step]:
                    if data_id in self.context_store:
                        data = self.context_store[data_id]
                        if relevance_order.index(data.relevance) <= threshold_index:
                            category = f"step_{step}_{data.data_type.value}"
                            if category not in relevant_data:
                                relevant_data[category] = []
                            relevant_data[category].append({
                                "content": data.content,
                                "source": data.source_tool,
                                "relevance": data.relevance.value,
                                "metadata": data.metadata
                            })
        
        # 2. 应用特定工具的数据流规则
        tool_specific_data = self._get_tool_specific_context(target_tool, current_step)
        relevant_data.update(tool_specific_data)
        
        # 3. 限制上下文大小
        if len(str(relevant_data)) > self.max_context_size:
            relevant_data = self._truncate_context(relevant_data)
        
        logger.info(f"📊 为 {target_tool} 获取了 {len(relevant_data)} 类相关上下文")
        return relevant_data
    
    def _get_tool_specific_context(self, target_tool: str, current_step: int) -> Dict[str, Any]:
        """获取特定工具的相关上下文"""
        tool_context = {}
        
        # 查找适用的数据流
        applicable_flows = [flow for flow in self.common_flows if flow.to_tool == target_tool]
        
        for flow in applicable_flows:
            # 寻找来源工具的输出
            for step in range(max(0, current_step - 3), current_step):
                if step in self.step_outputs:
                    for data_id in self.step_outputs[step]:
                        if data_id in self.context_store:
                            data = self.context_store[data_id]
                            if data.source_tool == flow.from_tool:
                                # 应用数据映射
                                for source_field, target_field in flow.data_mapping.items():
                                    if target_field not in tool_context:
                                        tool_context[target_field] = []
                                    
                                    processed_content = self._apply_transformation(
                                        data.content, flow.transformation_rule
                                    )
                                    
                                    tool_context[target_field].append({
                                        "content": processed_content,
                                        "original_content": data.content,
                                        "source_tool": data.source_tool,
                                        "transformation": flow.transformation_rule
                                    })
        
        return tool_context
    
    def _apply_transformation(self, content: Any, transformation_rule: Optional[str]) -> Any:
        """应用数据转换规则"""
        if not transformation_rule:
            return content
        
        content_str = str(content)
        
        try:
            if transformation_rule == "extract_key_facts":
                # 提取关键事实
                sentences = re.split(r'[.!?]+', content_str)
                key_sentences = []
                for sentence in sentences:
                    if any(keyword in sentence.lower() for keyword in 
                          ["price", "cost", "result", "shows", "indicates", "价格", "成本", "结果", "显示", "表明"]):
                        key_sentences.append(sentence.strip())
                return " ".join(key_sentences[:3])  # 最多3个关键句子
            
            elif transformation_rule == "parse_web_data":
                # 解析网页数据
                numbers = re.findall(r'\$?\d+\.?\d*', content_str)
                urls = re.findall(r'https?://[^\s<>"{}|\\^`[\]]+', content_str)
                return {
                    "numbers": numbers[:5],  # 最多5个数字
                    "urls": urls[:3],        # 最多3个URL
                    "summary": content_str[:200]  # 200字符摘要
                }
            
            elif transformation_rule == "format_for_search":
                # 格式化用于搜索
                if isinstance(content, (dict, list)):
                    return f"Based on calculation: {json.dumps(content)}"
                else:
                    return f"Related to: {str(content)[:100]}"
            
            elif transformation_rule == "extract_urls":
                # 提取URL
                urls = re.findall(r'https?://[^\s<>"{}|\\^`[\]]+', content_str)
                return urls[:5]  # 最多5个URL
            
        except Exception as e:
            logger.warning(f"⚠️ 数据转换失败 ({transformation_rule}): {e}")
            return content
        
        return content
    
    def _truncate_context(self, context_data: Dict[str, Any]) -> Dict[str, Any]:
        """截断上下文以控制大小"""
        truncated = {}
        total_size = 0
        
        # 按优先级排序（高相关性优先）
        sorted_items = sorted(
            context_data.items(), 
            key=lambda x: self._get_category_priority(x[0]), 
            reverse=True
        )
        
        for category, items in sorted_items:
            if total_size >= self.max_context_size:
                break
            
            truncated_items = []
            for item in items:
                item_size = len(str(item))
                if total_size + item_size <= self.max_context_size:
                    truncated_items.append(item)
                    total_size += item_size
                else:
                    break
            
            if truncated_items:
                truncated[category] = truncated_items
        
        logger.info(f"🔄 上下文截断: {len(context_data)} -> {len(truncated)} 类别")
        return truncated
    
    def _get_category_priority(self, category: str) -> int:
        """获取类别优先级"""
        if "error" in category:
            return 100
        elif "number" in category:
            return 90
        elif "json" in category:
            return 80
        elif "url" in category:
            return 70
        elif "code" in category:
            return 60
        else:
            return 50
    
    def generate_context_prompt(self, target_tool: str, current_step: int, 
                              task_description: str) -> str:
        """
        📝 生成包含上下文信息的提示
        
        Args:
            target_tool: 目标工具
            current_step: 当前步骤
            task_description: 任务描述
            
        Returns:
            str: 包含上下文的提示文本
        """
        relevant_context = self.get_relevant_context(target_tool, current_step)
        
        if not relevant_context:
            return ""
        
        prompt_parts = [
            "🔄 **Previous Step Results (Use this information in your current action):**\n"
        ]
        
        for category, items in relevant_context.items():
            if items:
                prompt_parts.append(f"\n**{category.replace('_', ' ').title()}:**")
                for i, item in enumerate(items[:3]):  # 最多显示3个项目
                    content = item["content"]
                    if isinstance(content, str) and len(content) > 150:
                        content = content[:150] + "..."
                    prompt_parts.append(f"  {i+1}. {content}")
        
        # 添加使用指导
        prompt_parts.extend([
            "\n🎯 **IMPORTANT**: You MUST reference and use the above information in your tool call.",
            "Do not ignore previous results or generate new simulated data when real data is available.",
            f"Current task context: {task_description[:100]}...\n"
        ])
        
        return "\n".join(prompt_parts)
    
    def get_context_summary(self, steps_range: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
        """
        📈 获取上下文数据摘要
        
        Args:
            steps_range: 步骤范围 (start, end)，None表示所有步骤
            
        Returns:
            Dict[str, Any]: 上下文摘要
        """
        if steps_range:
            start_step, end_step = steps_range
            relevant_steps = range(start_step, end_step + 1)
        else:
            relevant_steps = self.step_outputs.keys()
        
        summary = {
            "total_data_items": 0,
            "data_by_type": {},
            "data_by_relevance": {},
            "data_by_tool": {},
            "recent_errors": [],
            "key_numbers": [],
            "important_urls": []
        }
        
        for step in relevant_steps:
            if step in self.step_outputs:
                for data_id in self.step_outputs[step]:
                    if data_id in self.context_store:
                        data = self.context_store[data_id]
                        summary["total_data_items"] += 1
                        
                        # 按类型统计
                        data_type = data.data_type.value
                        summary["data_by_type"][data_type] = summary["data_by_type"].get(data_type, 0) + 1
                        
                        # 按相关性统计
                        relevance = data.relevance.value
                        summary["data_by_relevance"][relevance] = summary["data_by_relevance"].get(relevance, 0) + 1
                        
                        # 按工具统计
                        tool = data.source_tool
                        summary["data_by_tool"][tool] = summary["data_by_tool"].get(tool, 0) + 1
                        
                        # 收集特殊数据
                        if data.data_type == DataType.ERROR:
                            summary["recent_errors"].append({
                                "step": step,
                                "tool": data.source_tool,
                                "error": str(data.content)[:100]
                            })
                        elif data.data_type == DataType.NUMBER and data.relevance == DataRelevance.HIGH:
                            summary["key_numbers"].append({
                                "step": step,
                                "tool": data.source_tool,
                                "number": data.content
                            })
                        elif data.data_type == DataType.URL:
                            summary["important_urls"].append({
                                "step": step,
                                "tool": data.source_tool,
                                "url": data.content
                            })
        
        return summary
    
    def clear_old_context(self, keep_steps: int = 10):
        """
        🧹 清理旧的上下文数据
        
        Args:
            keep_steps: 保留的步骤数量
        """
        if not self.step_outputs:
            return
        
        max_step = max(self.step_outputs.keys())
        cutoff_step = max_step - keep_steps
        
        removed_count = 0
        for step in list(self.step_outputs.keys()):
            if step < cutoff_step:
                for data_id in self.step_outputs[step]:
                    if data_id in self.context_store:
                        del self.context_store[data_id]
                        removed_count += 1
                del self.step_outputs[step]
        
        logger.info(f"🧹 清理了 {removed_count} 个旧上下文数据项")