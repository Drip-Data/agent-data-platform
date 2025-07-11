"""
Result Injector - 结果注入器
在XML流中动态插入工具执行结果，支持多步骤推理
"""

import logging
import re
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

class ResultInjector:
    """结果注入器 - 在XML流中动态插入工具执行结果"""
    
    def __init__(self):
        """初始化结果注入器"""
        self.injection_count = 0
        logger.debug("🔧 ResultInjector初始化完成")
    
    def inject_result(self, xml_response: str, tool_call_pos: Tuple[int, int], 
                     result: Dict[str, Any], step_id: str = None) -> str:
        """
        在指定位置注入结果标签
        
        Args:
            xml_response: 原始XML响应
            tool_call_pos: 工具调用的位置 (start_pos, end_pos)
            result: 执行结果字典
            step_id: 步骤ID (可选，用于调试)
            
        Returns:
            注入结果后的XML响应
        """
        start_pos, end_pos = tool_call_pos
        
        # 构建结果XML
        result_xml = self._build_result_xml(result, step_id)
        
        # 在工具调用标签后插入结果
        before = xml_response[:end_pos]
        after = xml_response[end_pos:]
        
        injected_response = before + result_xml + after
        
        self.injection_count += 1
        logger.info(f"💉 结果注入完成 #{self.injection_count} - 步骤: {step_id}, 位置: {tool_call_pos}")
        logger.debug(f"   结果长度: {len(result_xml)} 字符")
        
        return injected_response
    
    def _build_result_xml(self, result: Dict[str, Any], step_id: str = None) -> str:
        """
        构建结果XML标签
        
        Args:
            result: 执行结果
            step_id: 步骤ID
            
        Returns:
            格式化的结果XML
        """
        if result.get('success', True):
            # 成功结果
            output = result.get('output', result.get('observation', ''))
            
            # 清理和格式化输出
            cleaned_output = self._clean_output(output)
            
            result_xml = f"\n<result>\n{cleaned_output}\n</result>\n"
        else:
            # 错误结果
            error_msg = result.get('error', result.get('error_message', 'Unknown error'))
            result_xml = f"\n<result>\nError: {error_msg}\n</result>\n"
        
        return result_xml
    
    def _clean_output(self, output: Any) -> str:
        """
        清理和格式化输出内容
        
        Args:
            output: 原始输出
            
        Returns:
            清理后的输出字符串
        """
        if output is None:
            return "No output"
        
        # 转换为字符串
        if not isinstance(output, str):
            output = str(output)
        
        # 移除过多的空行
        output = re.sub(r'\n\s*\n\s*\n', '\n\n', output)
        
        # 限制长度（避免过长的输出）
        max_length = 2000
        if len(output) > max_length:
            output = output[:max_length] + "\n... (输出已截断)"
        
        # 确保内容不包含XML标签冲突
        output = output.replace('<result>', '&lt;result&gt;')
        output = output.replace('</result>', '&lt;/result&gt;')
        
        return output.strip()
    
    def inject_multiple_results(self, xml_response: str, 
                               injection_data: list[Dict[str, Any]]) -> str:
        """
        批量注入多个结果
        
        Args:
            xml_response: 原始XML响应
            injection_data: 注入数据列表，每个包含:
                - tool_call_pos: 工具调用位置
                - result: 执行结果
                - step_id: 步骤ID
                
        Returns:
            注入所有结果后的XML响应
        """
        # 按位置从后往前排序，避免位置偏移问题
        sorted_data = sorted(injection_data, 
                           key=lambda x: x['tool_call_pos'][1], 
                           reverse=True)
        
        current_response = xml_response
        
        for data in sorted_data:
            current_response = self.inject_result(
                current_response,
                data['tool_call_pos'],
                data['result'],
                data.get('step_id')
            )
        
        logger.info(f"💉 批量注入完成 - 共注入 {len(injection_data)} 个结果")
        return current_response
    
    def find_tool_call_position(self, xml_response: str, tool_tag: str, 
                               occurrence: int = 1) -> Optional[Tuple[int, int]]:
        """
        查找工具调用标签的位置
        
        Args:
            xml_response: XML响应
            tool_tag: 工具标签名 (如 'microsandbox', 'deepsearch')
            occurrence: 第几次出现 (从1开始)
            
        Returns:
            (start_pos, end_pos) 或 None
        """
        pattern = f'<{tool_tag}>(.*?)</{tool_tag}>'
        matches = list(re.finditer(pattern, xml_response, re.DOTALL))
        
        if len(matches) >= occurrence:
            match = matches[occurrence - 1]
            return match.span()
        
        return None
    
    def extract_tool_calls_positions(self, xml_response: str) -> list[Dict[str, Any]]:
        """
        提取所有工具调用的位置信息
        
        Args:
            xml_response: XML响应
            
        Returns:
            工具调用位置列表
        """
        tool_tags = ['microsandbox', 'deepsearch', 'browser', 'search']
        positions = []
        
        for tool_tag in tool_tags:
            pattern = f'<{tool_tag}>(.*?)</{tool_tag}>'
            for match in re.finditer(pattern, xml_response, re.DOTALL):
                positions.append({
                    'tool_tag': tool_tag,
                    'position': match.span(),
                    'content': match.group(1).strip(),
                    'needs_result': True
                })
        
        # 按位置排序
        positions.sort(key=lambda x: x['position'][0])
        
        logger.debug(f"🔍 发现 {len(positions)} 个工具调用位置")
        return positions
    
    def has_result_tag_after_position(self, xml_response: str, 
                                    position: Tuple[int, int]) -> bool:
        """
        检查指定位置后是否已有result标签
        
        Args:
            xml_response: XML响应
            position: 检查位置
            
        Returns:
            是否已有result标签
        """
        start_pos, end_pos = position
        
        # 在工具调用后查找是否有<result>标签
        after_content = xml_response[end_pos:end_pos+200]  # 只检查后面200字符
        
        return '<result>' in after_content
    
    def remove_existing_results(self, xml_response: str) -> str:
        """
        移除现有的result标签（用于重新注入）
        
        Args:
            xml_response: XML响应
            
        Returns:
            移除result标签后的XML响应
        """
        # 移除所有<result>...</result>标签
        cleaned = re.sub(r'\s*<result>.*?</result>\s*', '', xml_response, flags=re.DOTALL)
        
        logger.debug("🧹 已移除现有的result标签")
        return cleaned
    
    def validate_xml_structure(self, xml_response: str) -> Dict[str, Any]:
        """
        验证XML结构的完整性
        
        Args:
            xml_response: XML响应
            
        Returns:
            验证结果
        """
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'tool_calls_count': 0,
            'result_tags_count': 0
        }
        
        # 检查工具调用标签
        tool_tags = ['microsandbox', 'deepsearch', 'browser', 'search']
        for tool_tag in tool_tags:
            pattern = f'<{tool_tag}>(.*?)</{tool_tag}>'
            matches = re.findall(pattern, xml_response, re.DOTALL)
            validation_result['tool_calls_count'] += len(matches)
        
        # 检查result标签
        result_matches = re.findall(r'<result>(.*?)</result>', xml_response, re.DOTALL)
        validation_result['result_tags_count'] = len(result_matches)
        
        # 检查标签平衡
        for tool_tag in tool_tags + ['think', 'answer', 'result']:
            open_count = xml_response.count(f'<{tool_tag}>')
            close_count = xml_response.count(f'</{tool_tag}>')
            
            if open_count != close_count:
                validation_result['is_valid'] = False
                validation_result['errors'].append(
                    f"不平衡的{tool_tag}标签: {open_count} 个开始标签, {close_count} 个结束标签"
                )
        
        # 检查嵌套问题
        if '<result>' in xml_response and '</result>' in xml_response:
            # 简单检查result标签是否正确嵌套
            result_content = re.findall(r'<result>(.*?)</result>', xml_response, re.DOTALL)
            for content in result_content:
                if '<result>' in content:
                    validation_result['warnings'].append("检测到嵌套的result标签")
        
        logger.debug(f"🔍 XML结构验证: {validation_result}")
        return validation_result