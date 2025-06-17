import json
import logging
import re
from typing import Dict, Any, List, Optional

from core.llm.response_parsers.interfaces import IResponseParser

logger = logging.getLogger(__name__)

class ReasoningResponseParser(IResponseParser):
    """
    用于解析LLM生成的推理响应的解析器。
    处理复杂的JSON提取、验证和修正逻辑。
    """

    def parse_response(self, response: str, **kwargs) -> Dict[str, Any]:
        """
        解析LLM的原始字符串响应，并将其转换为结构化的推理决策字典。
        
        Args:
            response (str): LLM的原始字符串响应。
            **kwargs: 额外的参数，目前未使用，但保留以符合接口。

        Returns:
            Dict[str, Any]: 包含解析后推理决策的字典。
        """
        logger.info(f"🔍 解析LLM响应 (长度: {len(response)})")
        
        try:
            # 首先尝试直接解析JSON
            response_clean = response.strip()
            
            # 🔍 增强的JSON提取 - 处理各种格式
            json_patterns = [
                r'```json\s*(\{.*?\})\s*```',  # markdown代码块
                r'```\s*(\{.*?\})\s*```',      # 普通代码块  
                r'(\{[^{}]*"thinking"[^{}]*\})', # 包含thinking的JSON
                r'(\{.*?\})',                  # 任何JSON对象
            ]
            
            json_text = None
            for pattern in json_patterns:
                match = re.search(pattern, response_clean, re.DOTALL)
                if match:
                    json_text = match.group(1)
                    logger.info(f"✅ 使用模式提取到JSON: {pattern}")
                    break
            
            # 如果没有找到JSON块，尝试直接解析
            if not json_text:
                # 移除可能的markdown代码块包装
                if response_clean.startswith('```json'):
                    response_clean = response_clean[7:]
                if response_clean.endswith('```'):
                    response_clean = response_clean[:-3]
                json_text = response_clean.strip()
            
            # 🔍 修复常见的JSON格式问题
            if json_text:
                # 修复被截断的JSON
                if not json_text.endswith('}') and json_text.count('{') > json_text.count('}'):
                    missing_braces = json_text.count('{') - json_text.count('}')
                    json_text += '}' * missing_braces
                    logger.warning(f"🔧 修复了 {missing_braces} 个缺失的右括号")
                
                # 尝试解析JSON
                try:
                    parsed = json.loads(json_text)
                    logger.info("✅ JSON解析成功")
                    
                    # 🔍 智能字段补全和验证
                    result = self._validate_and_complete_parsed_response(parsed)
                    
                    logger.info(f"🎯 最终解析结果: action={result.get('action')}, tool_id={result.get('tool_id')}, confidence={result.get('confidence')}")
                    return result
                    
                except json.JSONDecodeError as json_error:
                    logger.warning(f"❌ JSON解析失败: {json_error}")
                    # 继续使用备用解析方法
            
        except Exception as e:
            logger.error(f"❌ 响应解析过程中出错: {e}")
        
        # 🔍 增强的备用解析方法
        logger.warning("🔄 使用备用解析方法")
        return self._fallback_parse_response(response)
    
    def _validate_and_complete_parsed_response(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """验证并补全解析后的响应"""
        result = {}
        
        # 补全thinking字段
        result['thinking'] = parsed.get('thinking', f"LLM响应缺少thinking字段: {str(parsed)[:200]}")
        
        # 补全并验证action字段
        action = parsed.get('action', 'error')
        result['action'] = action
        
        # 补全并验证tool_id字段
        tool_id = parsed.get('tool_id') or parsed.get('tool')
        
        # 🔍 智能推断工具ID
        if not tool_id:
            if action in ['search_and_install_tools', 'analyze_tool_needs']:
                tool_id = 'mcp-search-tool'
                logger.info(f"🔧 自动推断工具ID: {tool_id} (基于action: {action})")
            elif 'search' in result['thinking'].lower() or 'install' in result['thinking'].lower():
                tool_id = 'mcp-search-tool'
                logger.info(f"🔧 基于thinking内容推断工具ID: {tool_id}")
        
        result['tool_id'] = tool_id
        result['tool'] = tool_id  # 向后兼容
        
        # 补全parameters字段
        parameters = parsed.get('parameters', {})
        
        # 🔍 基于action智能补全参数
        if action in ['search_and_install_tools', 'analyze_tool_needs'] and not parameters.get('task_description'):
            # 从thinking中提取任务描述
            thinking = result['thinking']
            if 'TASK ANALYSIS:' in thinking:
                task_desc_start = thinking.find('TASK ANALYSIS:') + len('TASK ANALYSIS:')
                task_desc_end = thinking.find('STEP 2', task_desc_start)
                if task_desc_end > task_desc_start:
                    task_desc = thinking[task_desc_start:task_desc_end].strip()
                    parameters['task_description'] = task_desc[:200]  # 限制长度
        
        result['parameters'] = parameters
        
        # 补全并验证confidence字段
        confidence = parsed.get('confidence', 0.5)
        if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
            confidence = 0.5
        result['confidence'] = confidence
        
        return result
    
    def _fallback_parse_response(self, response: str) -> Dict[str, Any]:
        """增强的备用解析方法"""
        logger.info("🔄 执行增强备用解析")
        
        # 🔍 增强的字段提取
        result = {
            'thinking': self._extract_thinking_field(response),
            'action': self._extract_action_field(response),
            'tool_id': self._extract_tool_id_field(response),
            'parameters': self._extract_parameters_field(response),
            'confidence': self._extract_confidence_field(response)
        }
        
        # 🔍 智能推断和修正
        result = self._smart_inference_and_correction(result, response)
        
        # 向后兼容
        result['tool'] = result['tool_id']
        
        logger.info(f"🎯 备用解析结果: action={result['action']}, tool_id={result['tool_id']}")
        return result
    
    def _extract_thinking_field(self, response: str) -> str:
        """提取thinking字段"""
        patterns = [
            r'"thinking":\s*"([^"]*(?:\\.[^"]*)*)"',
            r'thinking["\']?\s*[:=]\s*["\']([^"\']*)["\']',
            r'STEP 1[^:]*:([^"]*?)(?:STEP 2|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # 如果都找不到，返回响应的前500字符
        return response[:500]
    
    def _extract_action_field(self, response: str) -> str:
        """提取action字段"""
        patterns = [
            r'"action":\s*"([^"]+)"',
            r'action["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                return match.group(1)
        
        # 🔍 基于内容推断action
        if any(keyword in response.lower() for keyword in ['search', 'install', 'tool']):
            return 'search_and_install_tools'
        elif any(keyword in response.lower() for keyword in ['analyze', 'need']):
            return 'analyze_tool_needs'
        elif any(keyword in response.lower() for keyword in ['complete', 'finish', 'done']):
            return 'complete_task'
        
        return 'error'
    
    def _extract_tool_id_field(self, response: str) -> Optional[str]:
        """提取tool_id字段"""
        patterns = [
            r'"tool_id":\s*"([^"]+)"',
            r'"tool":\s*"([^"]+)"',
            r'tool_id["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_parameters_field(self, response: str) -> Dict[str, Any]:
        """提取parameters字段"""
        
        # 尝试提取完整的parameters对象
        params_match = re.search(r'"parameters":\s*(\{[^}]*\})', response, re.DOTALL)
        if params_match:
            try:
                return json.loads(params_match.group(1))
            except:
                pass
        
        # 备用方案：提取常见参数
        params = {}
        
        # 提取task_description
        task_desc_patterns = [
            r'"task_description":\s*"([^"]*)"',
            r'task_description["\']?\s*[:=]\s*["\']([^"\']*)["\']',
        ]
        
        for pattern in task_desc_patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                params['task_description'] = match.group(1)
                break
        
        return params
    
    def _extract_confidence_field(self, response: str) -> float:
        """提取confidence字段"""
        
        patterns = [
            r'"confidence":\s*([0-9.]+)',
            r'confidence["\']?\s*[:=]\s*([0-9.]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                try:
                    confidence = float(match.group(1))
                    return max(0.0, min(1.0, confidence))
                except:
                    pass
        
        return 0.5
    
    def _smart_inference_and_correction(self, result: Dict[str, Any], response: str) -> Dict[str, Any]:
        """智能推断和修正结果"""
        
        # 如果action是error但响应中包含工具相关内容，尝试修正
        if result['action'] == 'error':
            if any(keyword in response.lower() for keyword in ['mcp-search', 'search_and_install', 'tool']):
                result['action'] = 'search_and_install_tools'
                logger.info("🔧 修正action为: search_and_install_tools")
        
        # 如果没有tool_id但action需要工具，自动设置
        if not result['tool_id'] and result['action'] in ['search_and_install_tools', 'analyze_tool_needs']:
            result['tool_id'] = 'mcp-search-tool'
            logger.info("🔧 自动设置tool_id为: mcp-search-tool")
        
        # 如果parameters为空但action需要参数，尝试生成
        if not result['parameters'] and result['action'] in ['search_and_install_tools', 'analyze_tool_needs']:
            # 从thinking中提取任务相关信息
            thinking = result['thinking']
            params = {}
            
            if '任务' in thinking or 'task' in thinking.lower():
                # 提取可能的任务描述
                lines = thinking.split('\n')
                for line in lines:
                    if '任务' in line or 'task' in line.lower():
                        # 简化的任务描述提取
                        task_desc = line.strip()[:100]
                        params['task_description'] = task_desc
                        break
            
            if params:
                result['parameters'] = params
                logger.info(f"🔧 生成参数: {params}")
        
        return result