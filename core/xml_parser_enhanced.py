#!/usr/bin/env python3
"""
🚀 Stage 3: 增强XML解析器 (Enhanced XML Parser)
高容错性XML解析和修复模块
"""

import logging
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple, Any, Union
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class ParseError(Enum):
    """解析错误类型"""
    MALFORMED_XML = "malformed_xml"
    UNCLOSED_TAGS = "unclosed_tags"
    NESTED_STRUCTURE = "nested_structure"
    MISSING_CONTENT = "missing_content"
    ENCODING_ISSUE = "encoding_issue"
    INVALID_CHARACTERS = "invalid_characters"


@dataclass
class ParseResult:
    """解析结果"""
    success: bool
    actions: List[Dict[str, Any]]
    errors: List[str]
    warnings: List[str]
    repaired_xml: Optional[str] = None
    confidence_score: float = 1.0
    execution_type: str = "single"  # "single", "parallel", "sequential"


@dataclass
class RepairOperation:
    """修复操作记录"""
    operation_type: str
    original_text: str
    repaired_text: str
    description: str


class EnhancedXMLParser:
    """
    🔧 增强XML解析器
    
    功能：
    1. 高容错性XML解析
    2. 自动修复常见XML问题
    3. 多种解析策略
    4. 详细的错误报告和修复日志
    """
    
    def __init__(self):
        """初始化增强XML解析器"""
        self.repair_patterns = self._load_repair_patterns()
        self.service_aliases = self._load_service_aliases()
        self.common_tools = self._load_common_tools()
        
    def _load_repair_patterns(self) -> Dict[str, List[Tuple[str, str]]]:
        """加载XML修复模式"""
        return {
            'unclosed_tags': [
                # 自动闭合常见的未闭合标签
                (r'<(microsandbox|deepsearch|browser_use|search_tool)>\s*<(\w+)>([^<]*?)(?!</\2>)', 
                 r'<\1><\2>\3</\2></\1>'),
                (r'<(think|answer|result)>([^<]*?)(?!</\1>)', 
                 r'<\1>\2</\1>'),
            ],
            'malformed_structure': [
                # 修复嵌套结构问题
                (r'<(\w+)><(\w+)>([^<]*?)<(\w+)>', 
                 r'<\1><\2>\3</\2></\1><\4>'),
                # 修复重复标签
                (r'<(\w+)>\s*<\1>', r'<\1>'),
                (r'</(\w+)>\s*</\1>', r'</\1>'),
            ],
            'content_cleanup': [
                # 清理无效字符
                (r'[^\x20-\x7E\u4e00-\u9fff\n\r\t]', ''),
                # 修复编码问题
                (r'&(?!amp;|lt;|gt;|quot;|apos;)', '&amp;'),
            ],
            'execute_tools_fix': [
                # 修复execute_tools标签
                (r'<execute_tools\s*/?\s*>', '<execute_tools />'),
                (r'<execute_tools></execute_tools>', '<execute_tools />'),
                (r'</execute_tools>', '<execute_tools />'),
            ]
        }
    
    def _detect_execution_type(self, xml_string: str) -> str:
        """检测执行类型"""
        if '<parallel>' in xml_string or 'parallel>' in xml_string:
            return "parallel"
        elif '<sequential>' in xml_string or 'sequential>' in xml_string:
            return "sequential"
        else:
            return "single"
    
    def _load_service_aliases(self) -> Dict[str, str]:
        """加载服务别名映射"""
        return {
            'sandbox': 'microsandbox',
            'python': 'microsandbox', 
            'code': 'microsandbox',
            'search': 'deepsearch',
            'research': 'deepsearch',
            'browser': 'browser_use',
            'web': 'browser_use',
            'file_search': 'search_tool',
            'file': 'search_tool',
        }
    
    def _load_common_tools(self) -> Dict[str, List[str]]:
        """加载常见工具映射"""
        return {
            'microsandbox': [
                'microsandbox_execute', 'execute', 'run_code', 'python'
            ],
            'deepsearch': [
                'research', 'search', 'query', 'find'
            ],
            'browser_use': [
                'browser_search_google', 'search_google', 'browse', 'navigate'
            ],
            'search_tool': [
                'search_files', 'find_files', 'grep', 'locate'
            ]
        }
    
    def parse_xml_response(self, xml_string: str) -> ParseResult:
        """
        🎯 主要方法：解析XML响应
        
        Args:
            xml_string: XML响应字符串
            
        Returns:
            ParseResult: 解析结果
        """
        logger.info(f"🔍 开始解析XML响应 ({len(xml_string)} 字符)")
        
        # 清理输入
        cleaned_xml = self._preprocess_xml(xml_string)
        
        # 尝试多种解析策略
        strategies = [
            self._parse_standard_xml,
            self._parse_with_basic_repair,
            self._parse_with_aggressive_repair,
            self._parse_with_regex_extraction,
            self._parse_with_text_analysis
        ]
        
        best_result = None
        repair_operations = []
        
        for i, strategy in enumerate(strategies):
            try:
                logger.debug(f"🔄 尝试解析策略 {i+1}: {strategy.__name__}")
                result, operations = strategy(cleaned_xml)
                
                if result.success:
                    logger.info(f"✅ 策略 {i+1} 解析成功，提取到 {len(result.actions)} 个动作")
                    result.confidence_score = max(0.2, 1.0 - (i * 0.15))  # 策略越后置，置信度越低
                    return result
                
                # 保存最佳的部分成功结果
                if best_result is None or len(result.actions) > len(best_result.actions):
                    best_result = result
                    repair_operations = operations
                    
            except Exception as e:
                logger.debug(f"⚠️ 策略 {i+1} 失败: {e}")
                continue
        
        # 如果所有策略都失败，返回最佳部分结果
        if best_result is None:
            best_result = ParseResult(
                success=False,
                actions=[],
                errors=["所有解析策略都失败"],
                warnings=[],
                confidence_score=0.0,
                execution_type=self._detect_execution_type(xml_string)
            )
        else:
            # 为成功的结果添加执行类型
            best_result.execution_type = self._detect_execution_type(xml_string)
        
        logger.info(f"✅ XML解析完成，提取到 {len(best_result.actions)} 个动作，执行类型: {best_result.execution_type}")
        return best_result
    
    def _preprocess_xml(self, xml_string: str) -> str:
        """预处理XML字符串"""
        # 移除BOM和控制字符
        cleaned = xml_string.strip()
        cleaned = re.sub(r'^\ufeff', '', cleaned)  # 移除BOM
        
        # 基础清理
        for pattern, replacement in self.repair_patterns['content_cleanup']:
            cleaned = re.sub(pattern, replacement, cleaned)
        
        # 修复execute_tools标签
        for pattern, replacement in self.repair_patterns['execute_tools_fix']:
            cleaned = re.sub(pattern, replacement, cleaned)
        
        return cleaned
    
    def _parse_standard_xml(self, xml_string: str) -> Tuple[ParseResult, List[RepairOperation]]:
        """策略1：标准XML解析"""
        try:
            # 包装为根元素
            wrapped_xml = f"<root>{xml_string}</root>"
            root = ET.fromstring(wrapped_xml)
            
            actions = self._extract_actions_from_element(root)
            
            return ParseResult(
                success=True,
                actions=actions,
                errors=[],
                warnings=[],
                execution_type=self._detect_execution_type(xml_string)
            ), []
            
        except ET.ParseError as e:
            return ParseResult(
                success=False,
                actions=[],
                errors=[f"标准XML解析失败: {e}"],
                warnings=[],
                execution_type=self._detect_execution_type(xml_string)
            ), []
    
    def _parse_with_basic_repair(self, xml_string: str) -> Tuple[ParseResult, List[RepairOperation]]:
        """策略2：基础修复后解析"""
        repaired_xml = xml_string
        operations = []
        
        # 应用基础修复模式
        for repair_type, patterns in self.repair_patterns.items():
            if repair_type in ['unclosed_tags', 'execute_tools_fix']:
                for pattern, replacement in patterns:
                    old_xml = repaired_xml
                    repaired_xml = re.sub(pattern, replacement, repaired_xml, flags=re.DOTALL)
                    if old_xml != repaired_xml:
                        operations.append(RepairOperation(
                            operation_type=repair_type,
                            original_text=old_xml[:100] + "...",
                            repaired_text=repaired_xml[:100] + "...",
                            description=f"应用修复模式: {pattern}"
                        ))
        
        try:
            wrapped_xml = f"<root>{repaired_xml}</root>"
            root = ET.fromstring(wrapped_xml)
            actions = self._extract_actions_from_element(root)
            
            return ParseResult(
                success=True,
                actions=actions,
                errors=[],
                warnings=[f"应用了 {len(operations)} 个修复操作"],
                repaired_xml=repaired_xml,
                execution_type=self._detect_execution_type(xml_string)
            ), operations
            
        except ET.ParseError as e:
            return ParseResult(
                success=False,
                actions=[],
                errors=[f"基础修复后解析失败: {e}"],
                warnings=[],
                execution_type=self._detect_execution_type(xml_string)
            ), operations
    
    def _parse_with_aggressive_repair(self, xml_string: str) -> Tuple[ParseResult, List[RepairOperation]]:
        """策略3：激进修复后解析"""
        repaired_xml = xml_string
        operations = []
        
        # 应用所有修复模式
        for repair_type, patterns in self.repair_patterns.items():
            for pattern, replacement in patterns:
                old_xml = repaired_xml
                repaired_xml = re.sub(pattern, replacement, repaired_xml, flags=re.DOTALL)
                if old_xml != repaired_xml:
                    operations.append(RepairOperation(
                        operation_type=repair_type,
                        original_text=old_xml[:50] + "...",
                        repaired_text=repaired_xml[:50] + "...",
                        description=f"激进修复: {pattern}"
                    ))
        
        # 额外的激进修复
        repaired_xml = self._aggressive_tag_repair(repaired_xml, operations)
        
        try:
            wrapped_xml = f"<root>{repaired_xml}</root>"
            root = ET.fromstring(wrapped_xml)
            actions = self._extract_actions_from_element(root)
            
            return ParseResult(
                success=True,
                actions=actions,
                errors=[],
                warnings=[f"应用了 {len(operations)} 个激进修复操作"],
                repaired_xml=repaired_xml,
                execution_type=self._detect_execution_type(xml_string)
            ), operations
            
        except ET.ParseError as e:
            return ParseResult(
                success=False,
                actions=[],
                errors=[f"激进修复后解析失败: {e}"],
                warnings=[],
                execution_type=self._detect_execution_type(xml_string)
            ), operations
    
    def _parse_with_regex_extraction(self, xml_string: str) -> Tuple[ParseResult, List[RepairOperation]]:
        """策略4：正则表达式提取"""
        actions = []
        operations = []
        
        # 定义工具调用提取模式
        tool_patterns = [
            # 标准嵌套结构
            r'<(\w+)>\s*<(\w+)>(.*?)</\2>\s*</\1>',
            # 简化结构
            r'<(\w+)>\s*<(\w+)>(.*?)</\2>',
            # 单标签结构
            r'<(\w+)>(.*?)</\1>',
        ]
        
        for pattern in tool_patterns:
            matches = re.findall(pattern, xml_string, re.DOTALL)
            for match in matches:
                if len(match) == 3:
                    service, tool, content = match
                    # 标准化服务名
                    service = self.service_aliases.get(service.lower(), service)
                    
                    actions.append({
                        "service": service,
                        "tool": tool,
                        "input": content.strip()
                    })
                    
                    operations.append(RepairOperation(
                        operation_type="regex_extraction",
                        original_text=f"<{match[0]}><{match[1]}>{match[2]}</{match[1]}></{match[0]}>",
                        repaired_text=f"service={service}, tool={tool}",
                        description="正则表达式提取工具调用"
                    ))
        
        success = len(actions) > 0
        warnings = [] if success else ["正则表达式未能提取到有效的工具调用"]
        
        return ParseResult(
            success=success,
            actions=actions,
            errors=[] if success else ["正则表达式提取失败"],
            warnings=warnings,
            execution_type=self._detect_execution_type(xml_string)
        ), operations
    
    def _parse_with_text_analysis(self, xml_string: str) -> Tuple[ParseResult, List[RepairOperation]]:
        """策略5：文本分析提取"""
        actions = []
        operations = []
        
        # 分析文本内容，识别可能的工具调用意图
        lines = xml_string.split('\n')
        current_service = None
        current_tool = None
        current_content = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 检查服务标签
            for service in ['microsandbox', 'deepsearch', 'browser_use', 'search_tool']:
                if service in line.lower():
                    current_service = service
                    break
            
            # 检查工具标签
            if current_service:
                tools = self.common_tools.get(current_service, [])
                for tool in tools:
                    if tool in line.lower():
                        current_tool = tool
                        break
            
            # 收集内容
            if current_service and current_tool:
                # 清理标签并收集内容
                clean_line = re.sub(r'<[^>]*>', '', line).strip()
                if clean_line and clean_line not in ['', current_service, current_tool]:
                    current_content.append(clean_line)
        
        # 如果收集到了内容，创建动作
        if current_service and current_tool and current_content:
            content = ' '.join(current_content)
            actions.append({
                "service": current_service,
                "tool": current_tool,
                "input": content
            })
            
            operations.append(RepairOperation(
                operation_type="text_analysis",
                original_text=xml_string[:100] + "...",
                repaired_text=f"service={current_service}, tool={current_tool}",
                description="文本分析推断工具调用"
            ))
        
        success = len(actions) > 0
        
        return ParseResult(
            success=success,
            actions=actions,
            errors=[] if success else ["文本分析未能识别工具调用"],
            warnings=[] if success else ["使用了文本分析作为最后手段"],
            execution_type=self._detect_execution_type(xml_string)
        ), operations
    
    def _aggressive_tag_repair(self, xml_string: str, operations: List[RepairOperation]) -> str:
        """激进的标签修复"""
        repaired = xml_string
        
        # 1. 查找并修复未闭合的标签
        open_tags = re.findall(r'<(\w+)>', repaired)
        close_tags = re.findall(r'</(\w+)>', repaired)
        
        for tag in open_tags:
            if tag not in close_tags and tag not in ['execute_tools']:
                # 在字符串末尾添加闭合标签
                repaired += f'</{tag}>'
                operations.append(RepairOperation(
                    operation_type="aggressive_tag_repair",
                    original_text=f"未闭合的标签: {tag}",
                    repaired_text=f"添加闭合标签: </{tag}>",
                    description="激进标签修复：添加缺失的闭合标签"
                ))
        
        # 2. 修复嵌套问题
        # 简化过度嵌套的结构
        simplified = re.sub(r'<(\w+)>\s*<\1>', r'<\1>', repaired)
        simplified = re.sub(r'</(\w+)>\s*</\1>', r'</\1>', simplified)
        
        if simplified != repaired:
            operations.append(RepairOperation(
                operation_type="nesting_repair",
                original_text="重复嵌套标签",
                repaired_text="简化的标签结构",
                description="修复重复嵌套标签"
            ))
            repaired = simplified
        
        return repaired
    
    def _extract_actions_from_element(self, element: ET.Element) -> List[Dict[str, Any]]:
        """从XML元素中提取动作"""
        actions = []
        
        # 递归处理所有元素
        def process_element(elem):
            tag_name = elem.tag
            
            # 处理容器标签（parallel, sequential等）
            if tag_name in ['parallel', 'sequential', 'root']:
                for child in elem:
                    process_element(child)
                return
            
            # 跳过非服务标签
            if tag_name in ['think', 'answer', 'result', 'execute_tools']:
                return
            
            # 标准化服务名
            service_name = self.service_aliases.get(tag_name, tag_name)
            
            # 查找工具元素
            for tool_elem in elem:
                tool_name = tool_elem.tag
                tool_input = tool_elem.text or ""
                
                actions.append({
                    "service": service_name,
                    "tool": tool_name,
                    "input": tool_input.strip()
                })
        
        process_element(element)
        return actions
    
    def validate_action(self, action: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        ✅ 验证动作的有效性
        
        Args:
            action: 要验证的动作
            
        Returns:
            Tuple[bool, List[str]]: (是否有效, 验证警告列表)
        """
        warnings = []
        
        # 检查必需字段
        required_fields = ['service', 'tool', 'input']
        for field in required_fields:
            if field not in action or not action[field]:
                return False, [f"缺少必需字段: {field}"]
        
        # 验证服务名
        service = action['service']
        if service not in self.common_tools:
            if service in self.service_aliases.values():
                warnings.append(f"服务名 {service} 可能需要标准化")
            else:
                warnings.append(f"未知的服务名: {service}")
        
        # 验证工具名
        tool = action['tool']
        if service in self.common_tools:
            expected_tools = self.common_tools[service]
            if tool not in expected_tools:
                warnings.append(f"服务 {service} 的工具名 {tool} 可能不正确，期望: {expected_tools}")
        
        # 验证输入内容
        input_text = action['input']
        if len(input_text.strip()) == 0:
            warnings.append("工具输入为空")
        elif len(input_text) > 10000:
            warnings.append(f"工具输入过长 ({len(input_text)} 字符)")
        
        return True, warnings
    
    def repair_xml_structure(self, xml_string: str) -> Tuple[str, List[RepairOperation]]:
        """
        🔧 专门的XML结构修复方法
        
        Args:
            xml_string: 要修复的XML字符串
            
        Returns:
            Tuple[str, List[RepairOperation]]: (修复后的XML, 修复操作列表)
        """
        repaired = xml_string
        operations = []
        
        # 应用所有修复模式
        for repair_type, patterns in self.repair_patterns.items():
            for pattern, replacement in patterns:
                old_xml = repaired
                repaired = re.sub(pattern, replacement, repaired, flags=re.DOTALL)
                if old_xml != repaired:
                    operations.append(RepairOperation(
                        operation_type=repair_type,
                        original_text=old_xml[:100] + "..." if len(old_xml) > 100 else old_xml,
                        repaired_text=repaired[:100] + "..." if len(repaired) > 100 else repaired,
                        description=f"应用修复模式: {pattern} -> {replacement}"
                    ))
        
        logger.info(f"🔧 XML结构修复完成，应用了 {len(operations)} 个修复操作")
        return repaired, operations
    
    def get_parsing_confidence(self, result: ParseResult) -> float:
        """
        📊 计算解析置信度
        
        Args:
            result: 解析结果
            
        Returns:
            float: 置信度分数 (0.0 - 1.0)
        """
        if not result.success:
            return 0.0
        
        confidence = result.confidence_score
        
        # 根据动作数量调整
        if len(result.actions) == 0:
            confidence = 0.0
        elif len(result.actions) == 1:
            confidence *= 0.9  # 单个动作稍微降低置信度
        
        # 根据错误和警告调整
        if result.errors:
            confidence *= 0.7
        if result.warnings:
            confidence *= 0.9
        
        # 如果有修复操作，降低置信度
        if result.repaired_xml:
            confidence *= 0.8
        
        return min(1.0, max(0.0, confidence))