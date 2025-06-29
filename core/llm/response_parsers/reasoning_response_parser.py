import json
import logging
import re
from typing import Dict, Any, List

from core.llm.response_parsers.interfaces import IResponseParser

logger = logging.getLogger(__name__)

class ReasoningResponseParser(IResponseParser):
    """
    简化的响应解析器 - XML流式模式优先
    专注于XML标签解析，最小化复杂的JSON处理逻辑
    """
    
    def __init__(self):
        """初始化响应解析器"""
        pass
    
    def set_tool_schema_manager(self, tool_schema_manager):
        """保持接口兼容性"""
        pass

    def parse_response(self, response: str, **kwargs) -> Dict[str, Any]:
        """
        简化的响应解析 - XML流式模式优先
        
        Args:
            response (str): LLM的原始字符串响应
            **kwargs: 额外参数
            
        Returns:
            Dict[str, Any]: 解析后的推理决策字典
        """
        logger.info(f"🔍 解析响应 - 长度: {len(response)} 字符")
        logger.debug(f"响应预览: {response[:200]}..." if len(response) > 200 else response)
        
        # 🚀 优先检测XML流式模式 (核心设计)
        if self._is_xml_streaming_response(response):
            # 检测是否为Sequential模式
            if self._is_sequential_xml_response(response):
                logger.info("🎯 Sequential XML流式模式")
                return self._parse_sequential_steps(response)
            else:
                logger.info("🎯 单步XML流式模式")
                return self.parse_streaming_response(response)
        
        # 🔧 简单的JSON fallback (向后兼容)
        logger.info("📋 JSON模式")
        return self._simple_json_fallback(response)
    
    def _simple_json_fallback(self, response: str) -> Dict[str, Any]:
        """简单的JSON fallback解析 - 向后兼容"""
        try:
            # 尝试提取JSON
            cleaned = response.strip()
            
            # 移除markdown包装
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            elif cleaned.startswith('```'):
                cleaned = cleaned[3:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            
            cleaned = cleaned.strip()
            
            # 查找JSON对象
            first_brace = cleaned.find('{')
            last_brace = cleaned.rfind('}')
            
            if first_brace != -1 and last_brace != -1:
                json_text = cleaned[first_brace:last_brace + 1]
                
                # 基础清理
                json_text = re.sub(r',\s*}', '}', json_text)
                json_text = re.sub(r'\bTrue\b', 'true', json_text)
                json_text = re.sub(r'\bFalse\b', 'false', json_text)
                json_text = re.sub(r'\bNone\b', 'null', json_text)
                
                # 尝试解析
                parsed = json.loads(json_text)
                
                # 基本字段补全
                result = {
                    'thinking': parsed.get('thinking', 'No thinking provided'),
                    'action': parsed.get('action', 'error'),
                    'tool_id': parsed.get('tool_id') or parsed.get('tool', 'microsandbox'),
                    'parameters': parsed.get('parameters', {}),
                    'confidence': parsed.get('confidence', 0.5)
                }
                
                # 向后兼容
                result['tool'] = result['tool_id']
                
                logger.info(f"✅ JSON解析成功 - action: {result['action']}")
                return result
                
        except Exception as e:
            logger.warning(f"JSON解析失败: {e}")
        
        # 最终fallback
        return {
            'thinking': response[:500] if len(response) > 500 else response,
            'action': 'error',
            'tool_id': 'microsandbox',
            'tool': 'microsandbox',
            'parameters': {},
            'confidence': 0.1,
            'error': 'Failed to parse response'
        }
    
    def _is_xml_streaming_response(self, response: str) -> bool:
        """检测是否为XML流式响应"""
        xml_indicators = ['<think>', '<microsandbox>', '<deepsearch>', '<browser>', '<search>', '<answer>']
        return any(tag in response for tag in xml_indicators)
    
    def parse_streaming_response(self, response: str) -> Dict[str, Any]:
        """解析XML流式响应 - 基于MCP Server级别的标签"""
        logger.info("🎯 开始解析XML流式响应")
        
        # 提取完整thinking内容（不截断）
        thinking_segments = self._extract_all_xml_tags(response, 'think')
        complete_thinking = '\n\n'.join(thinking_segments)
        logger.debug(f"✅ 提取thinking内容: {len(complete_thinking)} 字符")
        
        # MCP Server级别的XML标签映射
        xml_to_server_map = {
            'microsandbox': 'microsandbox',
            'deepsearch': 'mcp-deepsearch', 
            'browser': 'browser_use',
            'search': 'mcp-search-tool'
        }
        
        # 检测工具调用
        for xml_tag, server_id in xml_to_server_map.items():
            content = self._extract_xml_tag(response, xml_tag)
            if content:
                logger.info(f"🔧 检测到MCP Server调用: {xml_tag} -> {server_id}")
                
                # 提取confidence值（如果存在）
                confidence = self._extract_confidence_from_content(content)
                
                # 去除content中的confidence标签，保留纯粹的指令
                clean_content = self._remove_confidence_tags(content)
                
                # 让系统自动选择最佳action，传递原始内容
                return {
                    "thinking": complete_thinking,
                    "tool_id": server_id,
                    "action": "auto_select",  # 特殊标记，让系统自己选择
                    "parameters": {"instruction": clean_content.strip()},
                    "confidence": confidence,
                    "xml_source": xml_tag
                }
        
        # 检测答案完成
        answer_content = self._extract_xml_tag(response, 'answer')
        if answer_content:
            logger.info("✅ 检测到任务完成标志")
            
            # 提取confidence值（如果存在）
            confidence = self._extract_confidence_from_content(answer_content)
            clean_answer = self._remove_confidence_tags(answer_content)
            
            return {
                "thinking": complete_thinking,
                "action": "complete_task",
                "final_answer": clean_answer,
                "confidence": confidence if confidence != 0.9 else 1.0  # answer默认高置信度
            }
        
        # 如果只有thinking内容，继续等待
        if complete_thinking:
            logger.info("💭 只有thinking内容，等待工具调用")
            return {
                "thinking": complete_thinking,
                "action": "continue_thinking",
                "confidence": 0.7
            }
        
        # Fallback到现有解析逻辑
        logger.warning("⚠️ XML解析失败，回退到传统JSON解析")
        return self._fallback_json_parse(response)
    
    def _extract_xml_tag(self, text: str, tag: str) -> str:
        """提取单个XML标签的内容"""
        pattern = f'<{tag}>(.*?)</{tag}>'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            content = match.group(1).strip()
            logger.debug(f"✅ 提取{tag}标签内容: {len(content)} 字符")
            return content
        return ""
    
    def _extract_all_xml_tags(self, text: str, tag: str) -> List[str]:
        """提取所有同名XML标签的内容"""
        pattern = f'<{tag}>(.*?)</{tag}>'
        matches = re.findall(pattern, text, re.DOTALL)
        contents = [match.strip() for match in matches]
        logger.debug(f"✅ 提取所有{tag}标签: {len(contents)} 个")
        return contents
    
    def _extract_confidence_from_content(self, content: str) -> float:
        """从内容中提取confidence值"""
        pattern = r'<confidence>(.*?)</confidence>'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            try:
                confidence_value = float(match.group(1).strip())
                # 确保在有效范围内
                confidence_value = max(0.0, min(1.0, confidence_value))
                logger.debug(f"✅ 提取到confidence值: {confidence_value}")
                return confidence_value
            except ValueError:
                logger.warning(f"⚠️ 无效的confidence值: {match.group(1)}")
        
        # 默认confidence值
        return 0.9
    
    def _remove_confidence_tags(self, content: str) -> str:
        """从内容中移除confidence标签"""
        # 移除confidence标签及其内容
        clean_content = re.sub(r'<confidence>.*?</confidence>', '', content, flags=re.DOTALL)
        # 清理多余的空白行
        clean_content = re.sub(r'\n\s*\n', '\n', clean_content.strip())
        return clean_content
    
    def _fallback_json_parse(self, response: str) -> Dict[str, Any]:
        """回退到传统JSON解析"""
        try:
            # 移除XML标签干扰，尝试JSON解析
            clean_response = re.sub(r'<[^>]+>.*?</[^>]+>', '', response, flags=re.DOTALL)
            clean_response = clean_response.strip()
            
            if clean_response.startswith('{') and clean_response.endswith('}'):
                parsed = json.loads(clean_response)
                return {
                    'thinking': parsed.get('thinking', 'No thinking provided'),
                    'action': parsed.get('action', 'error'),
                    'tool_id': parsed.get('tool_id', 'microsandbox'),
                    'tool': parsed.get('tool_id', 'microsandbox'),
                    'parameters': parsed.get('parameters', {}),
                    'confidence': parsed.get('confidence', 0.5)
                }
            
            # 完全失败，返回基本响应
            return {
                "thinking": response[:500] if len(response) > 500 else response,
                "action": "error",
                "tool_id": "microsandbox",
                "tool": "microsandbox",
                "parameters": {},
                "error": "无法解析响应格式",
                "confidence": 0.1
            }
            
        except Exception as e:
            logger.error(f"❌ Fallback解析也失败: {e}")
            return {
                "thinking": "解析失败: " + str(e),
                "action": "error", 
                "tool_id": "microsandbox",
                "tool": "microsandbox",
                "parameters": {},
                "error": str(e),
                "confidence": 0.0
            }
    
    def _is_sequential_xml_response(self, response: str) -> bool:
        """
        检测是否为Sequential XML响应
        
        Args:
            response: 响应字符串
            
        Returns:
            是否为Sequential模式
        """
        # 检测多个工具调用标签
        tool_tags = ['<microsandbox>', '<deepsearch>', '<browser>', '<search>']
        tool_count = sum(1 for tag in tool_tags if tag in response)
        
        # 检测是否有<think>和工具调用交替模式
        has_thinking_flow = '<think>' in response and any(tag in response for tag in tool_tags)
        
        # 检测完整的推理流程
        has_complete_flow = '<think>' in response and '<answer>' in response
        
        # Sequential模式的特征
        is_sequential = (
            tool_count > 1 or  # 多个工具调用
            has_thinking_flow or  # thinking + 工具调用
            has_complete_flow  # 完整推理流程
        )
        
        logger.debug(f"🔍 Sequential检测 - 工具数: {tool_count}, 思维流: {has_thinking_flow}, 完整流程: {has_complete_flow}")
        return is_sequential
    
    def _parse_sequential_steps(self, response: str) -> Dict[str, Any]:
        """
        解析Sequential XML步骤序列
        
        Args:
            response: XML响应
            
        Returns:
            Sequential解析结果
        """
        import re
        
        steps = []
        current_pos = 0
        
        # 正则匹配所有XML标签
        xml_pattern = r'<(think|microsandbox|deepsearch|browser|search|answer)>(.*?)</\1>'
        
        for match in re.finditer(xml_pattern, response, re.DOTALL):
            tag_name = match.group(1)
            content = match.group(2).strip()
            
            step = {
                'type': tag_name,
                'content': content,
                'position': match.span(),
                'needs_execution': tag_name in ['microsandbox', 'deepsearch', 'browser', 'search']
            }
            steps.append(step)
        
        # 提取完整thinking (合并所有<think>标签)
        thinking_segments = [s['content'] for s in steps if s['type'] == 'think']
        complete_thinking = '\n\n'.join(thinking_segments)
        
        # 检查是否有最终答案
        answer_steps = [s for s in steps if s['type'] == 'answer']
        final_answer = answer_steps[0]['content'] if answer_steps else ""
        
        # 统计工具调用步骤
        execution_steps = [s for s in steps if s['needs_execution']]
        
        logger.info(f"🎯 Sequential解析完成 - 总步骤: {len(steps)}, 执行步骤: {len(execution_steps)}")
        
        return {
            'action': 'sequential_streaming',
            'thinking': complete_thinking,
            'steps': steps,
            'execution_steps': execution_steps,
            'final_answer': final_answer,
            'xml_source': 'sequential',
            'confidence': 0.9,
            # 为了兼容现有系统，选择第一个执行步骤作为主要工具调用
            'tool_id': execution_steps[0]['type'] if execution_steps else 'microsandbox',
            'parameters': {'instruction': execution_steps[0]['content'] if execution_steps else ''}
        }