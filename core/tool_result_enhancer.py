#!/usr/bin/env python3
"""
🔧 工具结果增强器 (Tool Result Enhancer)
优化工具执行结果的结构化存储和处理，确保信息有效传递
"""

import logging
import json
import re
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ResultType(Enum):
    """结果类型"""
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    ERROR = "error"
    EMPTY = "empty"


class DataFormat(Enum):
    """数据格式"""
    TEXT = "text"
    JSON = "json"
    TABLE = "table"
    LIST = "list"
    NUMBER = "number"
    URL = "url"
    CODE = "code"
    MIXED = "mixed"


@dataclass
class EnhancedResult:
    """增强的工具执行结果"""
    tool_name: str
    original_result: Any
    result_type: ResultType
    data_format: DataFormat
    extracted_data: Dict[str, Any]
    confidence_score: float
    processing_timestamp: datetime
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = asdict(self)
        result['processing_timestamp'] = self.processing_timestamp.isoformat()
        result['result_type'] = self.result_type.value
        result['data_format'] = self.data_format.value
        return result


@dataclass
class ExtractionRule:
    """数据提取规则"""
    name: str
    pattern: str
    target_field: str
    data_type: str
    priority: int
    post_process: Optional[str] = None


class ToolResultEnhancer:
    """
    🔧 工具结果增强器
    
    功能：
    1. 智能分析工具执行结果
    2. 提取关键数据和信息
    3. 结构化存储处理结果
    4. 提供下游工具可用的数据格式
    """
    
    def __init__(self):
        """初始化工具结果增强器"""
        self.extraction_rules = self._load_extraction_rules()
        self.tool_specific_processors = self._initialize_tool_processors()
        
        logger.info("🔧 ToolResultEnhancer initialized")
    
    def _load_extraction_rules(self) -> Dict[str, List[ExtractionRule]]:
        """加载数据提取规则"""
        return {
            "deepsearch": [
                ExtractionRule(
                    name="price_extraction",
                    pattern=r'\$?(\d+\.?\d*)\s*(?:per\s+share|each|USD|dollars?|美元)',
                    target_field="prices",
                    data_type="number",
                    priority=10,
                    post_process="parse_float"
                ),
                ExtractionRule(
                    name="url_extraction", 
                    pattern=r'https?://[^\s<>"{}|\\^`[\]]+',
                    target_field="urls",
                    data_type="list",
                    priority=8
                ),
                ExtractionRule(
                    name="company_name",
                    pattern=r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:Inc|Corp|Ltd|LLC|Company|Co)\.?))\b',
                    target_field="companies",
                    data_type="list",
                    priority=7
                ),
                ExtractionRule(
                    name="key_facts",
                    pattern=r'(?:结果|显示|表明|indicates?|shows?|reveals?)[:：]\s*([^.!?]*[.!?])',
                    target_field="key_facts",
                    data_type="list",
                    priority=6
                )
            ],
            
            "browser_use": [
                ExtractionRule(
                    name="page_title",
                    pattern=r'<title[^>]*>(.*?)</title>',
                    target_field="page_title",
                    data_type="text",
                    priority=9
                ),
                ExtractionRule(
                    name="stock_price",
                    pattern=r'(?:Price|股价|Current|当前)[:：]?\s*\$?(\d+\.?\d*)',
                    target_field="stock_prices",
                    data_type="number",
                    priority=10,
                    post_process="parse_float"
                ),
                ExtractionRule(
                    name="links",
                    pattern=r'href=["\'](https?://[^"\']+)["\']',
                    target_field="links",
                    data_type="list",
                    priority=5
                ),
                ExtractionRule(
                    name="error_messages",
                    pattern=r'(?:Error|Failed|错误|失败)[:：]\s*([^\n]+)',
                    target_field="errors",
                    data_type="list",
                    priority=8
                )
            ],
            
            "microsandbox": [
                ExtractionRule(
                    name="calculation_result",
                    pattern=r'(?:Result|结果|Answer|答案)[:：]?\s*([^\n]+)',
                    target_field="calculations",
                    data_type="text",
                    priority=10
                ),
                ExtractionRule(
                    name="numeric_output",
                    pattern=r'\b(\d+\.?\d*(?:[eE][+-]?\d+)?)\b',
                    target_field="numbers",
                    data_type="number",
                    priority=8,
                    post_process="parse_float"
                ),
                ExtractionRule(
                    name="python_errors",
                    pattern=r'((?:Traceback|Error|Exception)[^\n]*(?:\n[^\n]*)*)',
                    target_field="python_errors",
                    data_type="list",
                    priority=9
                ),
                ExtractionRule(
                    name="variable_assignments",
                    pattern=r'(\w+)\s*=\s*([^\n]+)',
                    target_field="variables",
                    data_type="dict",
                    priority=6
                )
            ],
            
            "search_tool": [
                ExtractionRule(
                    name="file_paths",
                    pattern=r'([^\s]+\.[a-zA-Z]{2,4})',
                    target_field="file_paths",
                    data_type="list",
                    priority=8
                ),
                ExtractionRule(
                    name="search_matches",
                    pattern=r'Found:\s*([^\n]+)',
                    target_field="matches",
                    data_type="list",
                    priority=7
                )
            ]
        }
    
    def _initialize_tool_processors(self) -> Dict[str, callable]:
        """初始化工具特定的处理器"""
        return {
            "deepsearch": self._process_deepsearch_result,
            "browser_use": self._process_browser_result,
            "microsandbox": self._process_microsandbox_result,
            "search_tool": self._process_search_result
        }
    
    def enhance_tool_result(self, tool_name: str, raw_result: Any, 
                          execution_context: Optional[Dict[str, Any]] = None) -> EnhancedResult:
        """
        🔧 增强工具执行结果
        
        Args:
            tool_name: 工具名称
            raw_result: 原始结果
            execution_context: 执行上下文
            
        Returns:
            EnhancedResult: 增强后的结果
        """
        processing_start = datetime.now()
        
        # 1. 确定结果类型
        result_type = self._determine_result_type(raw_result)
        
        # 2. 确定数据格式
        data_format = self._determine_data_format(raw_result)
        
        # 3. 提取结构化数据
        extracted_data = self._extract_structured_data(tool_name, raw_result)
        
        # 4. 应用工具特定处理
        if tool_name in self.tool_specific_processors:
            try:
                enhanced_data = self.tool_specific_processors[tool_name](raw_result, extracted_data)
                extracted_data.update(enhanced_data)
            except Exception as e:
                logger.warning(f"⚠️ 工具特定处理失败 ({tool_name}): {e}")
        
        # 5. 计算置信度
        confidence_score = self._calculate_confidence(result_type, extracted_data, raw_result)
        
        # 6. 生成元数据
        metadata = self._generate_metadata(tool_name, raw_result, execution_context)
        
        enhanced_result = EnhancedResult(
            tool_name=tool_name,
            original_result=raw_result,
            result_type=result_type,
            data_format=data_format,
            extracted_data=extracted_data,
            confidence_score=confidence_score,
            processing_timestamp=processing_start,
            metadata=metadata
        )
        
        logger.info(f"🔧 结果增强完成: {tool_name}, 类型: {result_type.value}, 置信度: {confidence_score:.2f}")
        return enhanced_result
    
    def _determine_result_type(self, raw_result: Any) -> ResultType:
        """确定结果类型"""
        if raw_result is None:
            return ResultType.EMPTY
        
        result_str = str(raw_result).lower()
        
        # 检查错误指示
        error_indicators = ["error", "failed", "exception", "timeout", "错误", "失败", "异常"]
        if any(indicator in result_str for indicator in error_indicators):
            return ResultType.ERROR
        
        # 检查空结果
        if not result_str.strip() or result_str.strip() in ["none", "null", ""]:
            return ResultType.EMPTY
        
        # 特殊情况：明确指示失败（优先检查）
        failure_indicators = ["no results", "not found", "no data", "无结果", "未找到"]
        if any(indicator in result_str for indicator in failure_indicators):
            return ResultType.FAILURE
        
        # 检查部分成功
        partial_indicators = ["partial", "incomplete", "some", "部分", "不完整"]
        if any(indicator in result_str for indicator in partial_indicators):
            return ResultType.PARTIAL_SUCCESS
        
        # 检查成功指示
        success_indicators = ["success", "completed", "found", "result", "成功", "完成", "找到", "结果"]
        if any(indicator in result_str for indicator in success_indicators):
            return ResultType.SUCCESS
        
        # 如果有实质内容，认为是成功
        if len(result_str.strip()) > 10:
            return ResultType.SUCCESS
        
        return ResultType.SUCCESS  # 默认为成功，除非明确指示失败
    
    def _determine_data_format(self, raw_result: Any) -> DataFormat:
        """确定数据格式"""
        if raw_result is None:
            return DataFormat.TEXT
        
        # 检查JSON格式
        if isinstance(raw_result, (dict, list)):
            return DataFormat.JSON
        
        result_str = str(raw_result)
        
        # 尝试解析JSON（但排除纯数字）
        try:
            parsed = json.loads(result_str)
            # 如果解析成功但是纯数字，不算JSON格式
            if isinstance(parsed, (int, float)) and result_str.replace('.', '').replace('-', '').isdigit():
                pass  # 继续其他检查
            else:
                return DataFormat.JSON
        except (json.JSONDecodeError, TypeError):
            pass
        
        # 检查表格格式
        if self._is_table_format(result_str):
            return DataFormat.TABLE
        
        # 检查列表格式
        if self._is_list_format(result_str):
            return DataFormat.LIST
        
        # 检查数字格式
        if self._is_numeric_format(result_str):
            return DataFormat.NUMBER
        
        # 检查URL格式
        if self._is_url_format(result_str):
            return DataFormat.URL
        
        # 检查代码格式
        if self._is_code_format(result_str):
            return DataFormat.CODE
        
        # 检查混合格式 - 增强检测
        format_indicators = [
            self._contains_numbers(result_str),
            self._contains_urls(result_str), 
            self._contains_lists(result_str),
            self._contains_json(result_str)
        ]
        
        # 特殊情况：短文本中包含数字和其他内容
        if (self._contains_numbers(result_str) and 
            len(result_str) < 50 and 
            any([self._contains_urls(result_str), ":" in result_str, "$" in result_str])):
            return DataFormat.MIXED
        
        # 一般情况：多种格式并存
        format_count = sum(format_indicators)
        if format_count >= 2:
            return DataFormat.MIXED
        
        return DataFormat.TEXT
    
    def _extract_structured_data(self, tool_name: str, raw_result: Any) -> Dict[str, Any]:
        """提取结构化数据"""
        extracted_data = {}
        
        if tool_name not in self.extraction_rules:
            return extracted_data
        
        result_str = str(raw_result)
        rules = self.extraction_rules[tool_name]
        
        # 按优先级排序规则
        sorted_rules = sorted(rules, key=lambda x: x.priority, reverse=True)
        
        for rule in sorted_rules:
            try:
                matches = re.finditer(rule.pattern, result_str, re.IGNORECASE | re.MULTILINE)
                values = []
                
                for match in matches:
                    if match.groups():
                        # 有捕获组
                        value = match.group(1).strip()
                    else:
                        # 无捕获组，使用整个匹配
                        value = match.group(0).strip()
                    
                    # 应用后处理
                    if rule.post_process:
                        value = self._apply_post_processing(value, rule.post_process)
                    
                    values.append(value)
                
                if values:
                    if rule.data_type == "number":
                        # 数字类型始终作为列表存储，便于后续处理
                        extracted_data[rule.target_field] = values
                    elif rule.data_type == "text" and len(values) == 1:
                        extracted_data[rule.target_field] = values[0]
                    else:
                        extracted_data[rule.target_field] = values
                        
            except Exception as e:
                logger.warning(f"⚠️ 提取规则执行失败 ({rule.name}): {e}")
        
        return extracted_data
    
    def _apply_post_processing(self, value: str, post_process: str) -> Any:
        """应用后处理"""
        try:
            if post_process == "parse_float":
                # 清理数字字符串并转换为浮点数
                clean_value = re.sub(r'[^\d.-]', '', value)
                return float(clean_value) if clean_value else 0.0
            elif post_process == "parse_int":
                clean_value = re.sub(r'[^\d-]', '', value)
                return int(clean_value) if clean_value else 0
            elif post_process == "to_lower":
                return value.lower()
            elif post_process == "strip_html":
                return re.sub(r'<[^>]+>', '', value)
            elif post_process == "extract_domain":
                match = re.search(r'https?://(?:www\.)?([^/]+)', value)
                return match.group(1) if match else value
        except Exception as e:
            logger.warning(f"⚠️ 后处理失败 ({post_process}): {e}")
            return value
        
        return value
    
    def _calculate_confidence(self, result_type: ResultType, extracted_data: Dict[str, Any], 
                            raw_result: Any) -> float:
        """计算置信度"""
        base_confidence = 0.0
        
        # 基于结果类型
        if result_type == ResultType.SUCCESS:
            base_confidence = 0.8
        elif result_type == ResultType.PARTIAL_SUCCESS:
            base_confidence = 0.6
        elif result_type == ResultType.FAILURE:
            base_confidence = 0.3
        elif result_type == ResultType.ERROR:
            base_confidence = 0.1
        else:  # EMPTY
            base_confidence = 0.0
        
        # 基于提取数据的丰富度
        data_richness = len(extracted_data) / 10  # 每个提取字段贡献0.1
        data_richness = min(0.2, data_richness)  # 最多贡献0.2
        
        # 基于内容长度
        content_length = len(str(raw_result))
        if content_length > 100:
            length_bonus = 0.1
        elif content_length > 50:
            length_bonus = 0.05
        else:
            length_bonus = 0.0
        
        # 综合计算
        total_confidence = base_confidence + data_richness + length_bonus
        return min(1.0, max(0.0, total_confidence))
    
    def _generate_metadata(self, tool_name: str, raw_result: Any, 
                         execution_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """生成元数据"""
        metadata = {
            "result_length": len(str(raw_result)),
            "has_numbers": self._contains_numbers(str(raw_result)),
            "has_urls": self._contains_urls(str(raw_result)),
            "has_errors": "error" in str(raw_result).lower(),
            "processing_version": "1.0"
        }
        
        if execution_context:
            metadata["execution_context"] = execution_context
            
        return metadata
    
    # 工具特定处理器
    def _process_deepsearch_result(self, raw_result: Any, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理DeepSearch结果"""
        enhanced_data = {}
        
        result_str = str(raw_result)
        
        # 提取搜索摘要
        summary_match = re.search(r'(?:Summary|摘要)[:：]\s*([^\n]+)', result_str, re.IGNORECASE)
        if summary_match:
            enhanced_data["search_summary"] = summary_match.group(1).strip()
        
        # 提取相关性分数
        relevance_matches = re.findall(r'relevance[:：]?\s*(\d+\.?\d*)%?', result_str, re.IGNORECASE)
        if relevance_matches:
            enhanced_data["relevance_scores"] = [float(score) for score in relevance_matches]
        
        # 提取来源信息
        source_matches = re.findall(r'source[:：]?\s*([^\n]+)', result_str, re.IGNORECASE)
        if source_matches:
            enhanced_data["sources"] = source_matches
        
        return enhanced_data
    
    def _process_browser_result(self, raw_result: Any, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理Browser结果"""
        enhanced_data = {}
        
        result_str = str(raw_result)
        
        # 提取页面状态
        if "200" in result_str:
            enhanced_data["page_status"] = "success"
        elif any(code in result_str for code in ["404", "500", "403"]):
            enhanced_data["page_status"] = "error"
        else:
            enhanced_data["page_status"] = "unknown"
        
        # 提取页面类型
        if "stock" in result_str.lower() or "finance" in result_str.lower():
            enhanced_data["page_type"] = "financial"
        elif "news" in result_str.lower():
            enhanced_data["page_type"] = "news"
        else:
            enhanced_data["page_type"] = "general"
        
        # 提取时间戳
        timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})', result_str)
        if timestamp_match:
            enhanced_data["page_timestamp"] = timestamp_match.group(1)
        
        return enhanced_data
    
    def _process_microsandbox_result(self, raw_result: Any, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理MicroSandbox结果"""
        enhanced_data = {}
        
        result_str = str(raw_result)
        
        # 分析代码执行状态
        if "error" in result_str.lower() or "exception" in result_str.lower():
            enhanced_data["execution_status"] = "error"
        elif "warning" in result_str.lower():
            enhanced_data["execution_status"] = "warning"
        else:
            enhanced_data["execution_status"] = "success"
        
        # 提取数据类型信息
        data_types = []
        if re.search(r'\bDataFrame\b', result_str):
            data_types.append("pandas_dataframe")
        if re.search(r'\blist\b', result_str):
            data_types.append("list")
        if re.search(r'\bdict\b', result_str):
            data_types.append("dictionary")
        if re.search(r'\bnumpy\b', result_str):
            data_types.append("numpy_array")
        
        enhanced_data["detected_data_types"] = data_types
        
        # 提取导入的模块
        import_matches = re.findall(r'import\s+(\w+)', result_str)
        if import_matches:
            enhanced_data["imported_modules"] = list(set(import_matches))
        
        return enhanced_data
    
    def _process_search_result(self, raw_result: Any, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理Search工具结果"""
        enhanced_data = {}
        
        result_str = str(raw_result)
        
        # 提取匹配统计
        match_count = len(re.findall(r'found|match|匹配', result_str, re.IGNORECASE))
        enhanced_data["match_count"] = match_count
        
        # 提取文件类型
        file_extensions = re.findall(r'\.(\w+)', result_str)
        if file_extensions:
            enhanced_data["file_types"] = list(set(file_extensions))
        
        return enhanced_data
    
    # 格式检测辅助方法
    def _is_table_format(self, text: str) -> bool:
        """检查是否为表格格式"""
        lines = text.split('\n')
        if len(lines) < 2:
            return False
        
        # 检查是否有表格分隔符
        separators = ['|', '\t', '  +  ']
        return any(sep in text for sep in separators)
    
    def _is_list_format(self, text: str) -> bool:
        """检查是否为列表格式"""
        list_indicators = [r'^\s*[\d\w]\.\s', r'^\s*[-*]\s', r'^\s*\d+\)\s']
        lines = text.split('\n')
        list_lines = 0
        
        for line in lines:
            if any(re.match(pattern, line) for pattern in list_indicators):
                list_lines += 1
        
        return list_lines >= 2
    
    def _is_numeric_format(self, text: str) -> bool:
        """检查是否为数字格式"""
        # 移除空白后检查是否主要是数字
        clean_text = re.sub(r'\s', '', text)
        numeric_chars = len(re.findall(r'[\d.-]', clean_text))
        total_chars = len(clean_text)
        
        return total_chars > 0 and numeric_chars / total_chars > 0.7
    
    def _is_url_format(self, text: str) -> bool:
        """检查是否为URL格式"""
        url_pattern = r'https?://[^\s<>"{}|\\^`[\]]+'
        urls = re.findall(url_pattern, text)
        return len(urls) > 0 and len(' '.join(urls)) / len(text) > 0.5
    
    def _is_code_format(self, text: str) -> bool:
        """检查是否为代码格式"""
        code_indicators = [
            r'def\s+\w+\(',
            r'class\s+\w+',
            r'import\s+\w+',
            r'from\s+\w+\s+import',
            r'```',
            r'\w+\s*=\s*\w+',
        ]
        
        return any(re.search(pattern, text) for pattern in code_indicators)
    
    def _contains_numbers(self, text: str) -> bool:
        """检查是否包含数字"""
        return bool(re.search(r'\d+', text))
    
    def _contains_urls(self, text: str) -> bool:
        """检查是否包含URL"""
        return bool(re.search(r'https?://', text))
    
    def _contains_lists(self, text: str) -> bool:
        """检查是否包含列表"""
        return bool(re.search(r'^\s*[-*]\s', text, re.MULTILINE))
    
    def _contains_json(self, text: str) -> bool:
        """检查是否包含JSON"""
        return bool(re.search(r'[{\[].*[}\]]', text, re.DOTALL))
    
    def get_extractable_data_summary(self, enhanced_result: EnhancedResult) -> Dict[str, Any]:
        """
        📊 获取可提取数据的摘要
        
        Args:
            enhanced_result: 增强结果
            
        Returns:
            Dict[str, Any]: 数据摘要
        """
        summary = {
            "tool_name": enhanced_result.tool_name,
            "result_type": enhanced_result.result_type.value,
            "data_format": enhanced_result.data_format.value,
            "confidence_score": enhanced_result.confidence_score,
            "extracted_fields": list(enhanced_result.extracted_data.keys()),
            "key_data": {}
        }
        
        # 提取关键数据
        for field, value in enhanced_result.extracted_data.items():
            if isinstance(value, list) and len(value) > 0:
                summary["key_data"][field] = value[:3]  # 最多显示3个
            elif isinstance(value, (int, float, str)) and value:
                summary["key_data"][field] = value
        
        return summary
    
    def prepare_for_next_tool(self, enhanced_result: EnhancedResult, 
                            target_tool: str) -> Dict[str, Any]:
        """
        🎯 为下一个工具准备数据
        
        Args:
            enhanced_result: 增强结果
            target_tool: 目标工具
            
        Returns:
            Dict[str, Any]: 为目标工具准备的数据
        """
        prepared_data = {
            "source_tool": enhanced_result.tool_name,
            "confidence": enhanced_result.confidence_score,
            "available_data": {}
        }
        
        # 根据目标工具选择相关数据
        if target_tool == "microsandbox":
            # 为代码执行准备数据
            if "prices" in enhanced_result.extracted_data:
                prepared_data["available_data"]["price_data"] = enhanced_result.extracted_data["prices"]
            if "numbers" in enhanced_result.extracted_data:
                prepared_data["available_data"]["numeric_data"] = enhanced_result.extracted_data["numbers"]
            if "companies" in enhanced_result.extracted_data:
                prepared_data["available_data"]["company_names"] = enhanced_result.extracted_data["companies"]
                
        elif target_tool == "browser_use":
            # 为浏览器准备数据
            if "urls" in enhanced_result.extracted_data:
                prepared_data["available_data"]["target_urls"] = enhanced_result.extracted_data["urls"]
            if "companies" in enhanced_result.extracted_data:
                prepared_data["available_data"]["search_terms"] = enhanced_result.extracted_data["companies"]
                
        elif target_tool == "deepsearch":
            # 为搜索准备数据
            if "key_facts" in enhanced_result.extracted_data:
                prepared_data["available_data"]["context_facts"] = enhanced_result.extracted_data["key_facts"]
            if "companies" in enhanced_result.extracted_data:
                prepared_data["available_data"]["related_entities"] = enhanced_result.extracted_data["companies"]
        
        # 添加原始结果的精简版本
        original_text = str(enhanced_result.original_result)
        if len(original_text) > 200:
            prepared_data["result_summary"] = original_text[:200] + "..."
        else:
            prepared_data["result_summary"] = original_text
        
        return prepared_data