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
                
                # 修复常见的JSON格式错误
                json_text = self._fix_json_formatting_errors(json_text)
                
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
                    
                    # 🔧 多层级修复策略，减少对fallback的依赖
                    repair_attempts = [
                        ("轻量修复", lambda x: self._lightweight_json_repair(x)),
                        ("激进修复", lambda x: self._aggressive_json_fix(x)),
                        ("结构重建", lambda x: self._reconstruct_json_structure(x)),
                        ("健壮字段提取", lambda x: self._robust_extract_fields(response)),  # 新增健壮提取器
                    ]
                    
                    for repair_name, repair_func in repair_attempts:
                        try:
                            if repair_name == "健壮字段提取":
                                # 健壮字段提取器直接返回结果字典
                                result = repair_func(json_text)
                                if result and result.get('action') != 'error':
                                    logger.info(f"✅ 使用{repair_name}成功提取字段")
                                    return result
                            else:
                                # 其他修复器返回修复后的JSON字符串
                                fixed_json = repair_func(json_text)
                                if fixed_json and fixed_json != json_text:
                                    parsed = json.loads(fixed_json)
                                    result = self._validate_and_complete_parsed_response(parsed)
                                    logger.info(f"✅ 使用{repair_name}成功解析JSON")
                                    return result
                        except json.JSONDecodeError as e:
                            logger.debug(f"⚠️ {repair_name}失败: {e}")
                            continue
                        except Exception as e:
                            logger.debug(f"⚠️ {repair_name}异常: {e}")
                            continue
                    
                    # 如果所有修复都失败，最后尝试从原始响应中智能提取
                    logger.warning("🔄 尝试从原始响应智能提取字段")
                    smart_extracted = self._smart_extract_from_response(response)
                    if smart_extracted and smart_extracted.get('action') != 'error':
                        logger.info("✅ 智能提取成功，避免使用fallback")
                        return smart_extracted
            
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
        """增强的备用解析方法 - 优化版本"""
        logger.info("🔄 执行增强备用解析")
        
        # 智能截断长响应，优先保留JSON结构
        if len(response) > 8000:
            logger.warning(f"⚠️ 响应过长({len(response)}字符)，进行智能截断")
            response = self._smart_truncate_response(response, 8000)
        
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
        """智能推断和修正结果 - 优化版本"""
        
        # 限制文本长度，提高性能
        response_sample = response[:1000].lower()  # 只检查前1000字符
        
        # 如果action是error但响应中包含工具相关内容，尝试修正
        if result['action'] == 'error':
            if any(keyword in response_sample for keyword in ['mcp-search', 'search_and_install', 'tool']):
                result['action'] = 'search_and_install_tools'
                logger.info("🔧 修正action为: search_and_install_tools")
        
        # 如果没有tool_id但action需要工具，自动设置
        if not result['tool_id'] and result['action'] in ['search_and_install_tools', 'analyze_tool_needs']:
            result['tool_id'] = 'mcp-search-tool'
            logger.info("🔧 自动设置tool_id为: mcp-search-tool")
        
        # 如果parameters为空但action需要参数，尝试生成
        if not result['parameters'] and result['action'] in ['search_and_install_tools', 'analyze_tool_needs']:
            # 从thinking中提取任务相关信息（限制处理长度）
            thinking = result['thinking'][:500]  # 只处理前500字符
            params = {}
            
            if '任务' in thinking or 'task' in thinking.lower():
                # 提取可能的任务描述
                lines = thinking.split('\n')[:10]  # 最多检查10行
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
    
    def _fix_json_formatting_errors(self, json_text: str) -> str:
        """修复常见的JSON格式错误 - 增强版本"""
        # 🔧 新增：修复中文标点符号问题 - 解决 "Expecting ':' delimiter" 错误
        json_text = self._fix_chinese_punctuation(json_text)
        
        # 修复未终止的字符串 - 处理"Unterminated string"错误
        json_text = self._fix_unterminated_strings(json_text)
        
        # 修复缺失字段导致的连续逗号问题
        json_text = self._fix_missing_fields(json_text)
        
        # 🔧 修复日志中发现的具体错误模式
        
        # 1. 修复 "Expecting ':' delimiter" 错误
        json_text = self._fix_missing_colons(json_text)
        
        # 2. 修复 "Expecting ',' delimiter" 错误 
        json_text = self._fix_missing_commas(json_text)
        
        # 3. 修复 "Expecting property name enclosed in double quotes" 错误
        json_text = self._fix_property_names(json_text)
        
        # 修复常见的逗号错误
        json_text = re.sub(r',\s*}', '}', json_text)  # 移除对象最后的逗号
        json_text = re.sub(r',\s*]', ']', json_text)  # 移除数组最后的逗号
        
        # 修复缺少逗号的情况
        json_text = re.sub(r'"\s*\n\s*"', '",\n"', json_text)  # 字符串之间缺少逗号
        json_text = re.sub(r'}\s*\n\s*"', '},\n"', json_text)  # 对象后缺少逗号
        
        # 修复引号问题
        json_text = re.sub(r"'([^']*)':", r'"\1":', json_text)  # 单引号替换为双引号
        
        # 修复布尔值和null
        json_text = re.sub(r'\bTrue\b', 'true', json_text)
        json_text = re.sub(r'\bFalse\b', 'false', json_text)
        json_text = re.sub(r'\bNone\b', 'null', json_text)
        
        return json_text
    
    def _fix_chinese_punctuation(self, json_text: str) -> str:
        """修复中文标点符号问题 - 关键修复方法"""
        try:
            # 修复中文冒号 "：" -> ":"
            json_text = json_text.replace('：', ':')
            
            # 修复中文逗号 "，" -> ","  
            json_text = json_text.replace('，', ',')
            
            # 修复中文引号 """ -> '"' 和 """ -> '"'
            json_text = json_text.replace('"', '"').replace('"', '"')
            
            # 修复中文单引号 "'" -> "'" 和 "'" -> "'"
            json_text = json_text.replace(''', "'").replace(''', "'")
            
            # 修复中文句号（如果出现在JSON中）"。" -> "."
            json_text = json_text.replace('。', '.')
            
            # 修复中文分号 "；" -> ";"
            json_text = json_text.replace('；', ';')
            
            logger.debug("🔧 已修复中文标点符号")
            return json_text
            
        except Exception as e:
            logger.warning(f"修复中文标点符号时出错: {e}")
            return json_text
    
    def _fix_missing_fields(self, json_text: str) -> str:
        """修复缺失字段导致的JSON错误"""
        try:
            # 修复连续逗号问题（缺失字段导致）
            json_text = re.sub(r',\s*,', ',', json_text)  # 移除连续逗号
            
            # 修复以逗号开头的行（缺失字段导致）
            lines = json_text.split('\n')
            fixed_lines = []
            
            for i, line in enumerate(lines):
                stripped = line.strip()
                
                # 如果行以逗号开头，说明上一行缺失了字段
                if stripped.startswith(','):
                    # 添加一个占位字段
                    if i > 0 and not fixed_lines[-1].strip().endswith('{'):
                        # 根据上下文推断可能缺失的字段
                        if 'content_identifier' in json_text and '"content_identifier"' not in fixed_lines[-1]:
                            fixed_lines[-1] = fixed_lines[-1].rstrip().rstrip(',') + ','
                            fixed_lines.append('            "content_identifier": "unknown"')
                        elif 'relationship' in json_text and '"relationship"' not in fixed_lines[-1]:
                            fixed_lines[-1] = fixed_lines[-1].rstrip().rstrip(',') + ','
                            fixed_lines.append('            "relationship": "unknown"')
                        else:
                            # 通用占位字段
                            fixed_lines[-1] = fixed_lines[-1].rstrip().rstrip(',') + ','
                            fixed_lines.append('            "missing_field": "placeholder"')
                    
                    # 移除开头的逗号
                    line = line.lstrip().lstrip(',').lstrip()
                    if line:
                        fixed_lines.append('            ' + line)
                else:
                    fixed_lines.append(line)
            
            result = '\n'.join(fixed_lines)
            
            # 最后清理多余的逗号和空行
            result = re.sub(r',\s*\n\s*,', ',', result)
            result = re.sub(r'\n\s*\n', '\n', result)
            
            return result
            
        except Exception as e:
            logger.warning(f"⚠️ 修复缺失字段时出错: {e}")
            return json_text
    
    def _fix_unterminated_strings(self, json_text: str) -> str:
        """修复未终止的字符串错误"""
        try:
            # 处理字符串中的未转义换行符
            # 将字符串值中的真实换行符替换为\\n
            def replace_newlines_in_strings(match):
                content = match.group(1)
                # 只转义未转义的换行符
                content = content.replace('\n', '\\n')
                content = content.replace('\r', '\\r')
                content = content.replace('\t', '\\t')
                return f'"{content}"'
            
            # 匹配字符串值（不包括键名）
            json_text = re.sub(r':\s*"([^"]*(?:\n[^"]*)*)"', replace_newlines_in_strings, json_text)
            
            # 处理字符串中的未转义引号
            # 查找可能有问题的字符串并修复
            lines = json_text.split('\n')
            fixed_lines = []
            
            for line in lines:
                # 检查是否有未终止的字符串（奇数个引号）
                quote_count = line.count('"')
                if quote_count % 2 == 1 and not line.strip().endswith('",') and not line.strip().endswith('"'):
                    # 可能是未终止的字符串，尝试修复
                    if '": "' in line:
                        # 找到最后一个": "并确保字符串正确终止
                        last_colon_quote = line.rfind('": "')
                        if last_colon_quote != -1:
                            before = line[:last_colon_quote + 4]
                            after = line[last_colon_quote + 4:]
                            # 转义内部引号并确保字符串终止
                            after = after.replace('"', '\\"')
                            if not after.endswith('"'):
                                after += '"'
                            line = before + after
                
                fixed_lines.append(line)
            
            return '\n'.join(fixed_lines)
            
        except Exception as e:
            logger.warning(f"⚠️ 修复未终止字符串时出错: {e}")
            return json_text
    
    def _aggressive_json_fix(self, json_text: str) -> Optional[str]:
        """更激进的JSON修复方法"""
        try:
            # 首先应用基本的字符串修复
            json_text = self._fix_unterminated_strings(json_text)
            
            # 尝试修复截断的JSON
            if not json_text.strip().endswith('}'):
                # 找到最后一个完整的字段
                lines = json_text.split('\n')
                valid_lines = []
                brace_count = 0
                in_string = False
                
                for line in lines:
                    # 检查是否在字符串内部（简单检查）
                    quote_count = line.count('"') - line.count('\\"')
                    if quote_count % 2 == 1:
                        in_string = not in_string
                    
                    # 如果不在字符串内部，才计算括号
                    if not in_string:
                        brace_count += line.count('{') - line.count('}')
                    
                    valid_lines.append(line)
                    
                    # 如果括号平衡且该行结束，可能是个好的截断点
                    if not in_string and brace_count == 0 and (line.strip().endswith(',') or line.strip().endswith('"')):
                        break
                
                # 补齐缺失的括号
                if brace_count > 0:
                    valid_lines.append('}' * brace_count)
                
                fixed_json = '\n'.join(valid_lines)
                
                # 清理最后的逗号
                fixed_json = re.sub(r',(\s*})$', r'\1', fixed_json, flags=re.MULTILINE)
                
                return fixed_json
            
            # 如果JSON看起来完整，但仍然有错误，尝试清理格式
            json_text = self._clean_json_format(json_text)
            return json_text
                
        except Exception as e:
            logger.debug(f"激进JSON修复失败: {e}")
            
        return None
    
    def _clean_json_format(self, json_text: str) -> str:
        """清理JSON格式，处理常见的格式问题"""
        try:
            # 移除多余的空白字符
            json_text = re.sub(r'\s+', ' ', json_text)
            
            # 修复字符串中的控制字符
            json_text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_text)
            
            # 确保字符串值被正确引用
            # 修复未引用的字符串值（但保留数字、布尔值和null）
            def quote_unquoted_strings(match):
                key = match.group(1)
                value = match.group(2).strip()
                
                # 如果值已经被引用或是数字/布尔值/null，保持不变
                if (value.startswith('"') and value.endswith('"')) or \
                   value in ['true', 'false', 'null'] or \
                   re.match(r'^-?\d+(\.\d+)?$', value):
                    return f'"{key}": {value}'
                else:
                    # 引用未引用的字符串值
                    return f'"{key}": "{value}"'
            
            json_text = re.sub(r'"([^"]+)":\s*([^,}\]]+)', quote_unquoted_strings, json_text)
            
            return json_text
            
        except Exception as e:
            logger.warning(f"⚠️ 清理JSON格式时出错: {e}")
            return json_text
    
    def _fix_missing_colons(self, json_text: str) -> str:
        """修复缺失冒号的错误 - 处理 'Expecting ':' delimiter' 错误"""
        try:
            # 1. 修复属性名后缺失冒号的情况
            # 匹配 "key" value 模式，应该是 "key": value
            json_text = re.sub(r'"([^"]+)"\s+(["\d\[\{])', r'"\1": \2', json_text)
            
            # 2. 修复换行导致的冒号分离
            # 匹配 "key"\n value 模式  
            json_text = re.sub(r'"([^"]+)"\s*\n\s*(["\d\[\{])', r'"\1": \2', json_text)
            
            # 3. 修复特殊情况：thinking 字段后缺失冒号
            json_text = re.sub(r'"thinking"\s+"([^"]*)"', r'"thinking": "\1"', json_text)
            json_text = re.sub(r'"action"\s+"([^"]*)"', r'"action": "\1"', json_text)
            json_text = re.sub(r'"confidence"\s+(\d+\.?\d*)', r'"confidence": \1', json_text)
            
            # 4. 修复在行首的属性缺失冒号
            lines = json_text.split('\n')
            fixed_lines = []
            for line in lines:
                # 检查是否是 "属性名" 值 的模式
                if re.match(r'^\s*"[^"]+"\s+[^:]', line.strip()):
                    line = re.sub(r'"([^"]+)"\s+', r'"\1": ', line, 1)
                fixed_lines.append(line)
            
            return '\n'.join(fixed_lines)
            
        except Exception as e:
            logger.warning(f"⚠️ 修复缺失冒号时出错: {e}")
            return json_text
    
    def _fix_missing_commas(self, json_text: str) -> str:
        """修复缺失逗号的错误 - 处理 'Expecting ',' delimiter' 错误"""
        try:
            # 1. 修复对象属性之间缺失逗号
            # 匹配 "key": "value"\n  "key2": "value2" 模式
            json_text = re.sub(r'("\s*)\n\s*(")', r'\1,\n\2', json_text)
            
            # 2. 修复数组元素之间缺失逗号
            # 匹配 }\n  { 模式（对象数组）
            json_text = re.sub(r'(\})\s*\n\s*(\{)', r'\1,\n\2', json_text)
            
            # 3. 修复数值后缺失逗号
            json_text = re.sub(r'(\d+\.?\d*)\s*\n\s*"', r'\1,\n"', json_text)
            
            # 4. 修复布尔值和null后缺失逗号
            json_text = re.sub(r'(true|false|null)\s*\n\s*"', r'\1,\n"', json_text)
            
            # 5. 特别处理长字符串截断导致的逗号缺失
            # 如果在第6999字符附近缺失逗号（根据日志错误）
            if len(json_text) > 6990:
                # 在7000字符附近查找可能的逗号缺失
                substr = json_text[6990:7010]
                if '"' in substr and ',' not in substr:
                    # 在引号后添加逗号
                    json_text = json_text[:6999] + ',' + json_text[6999:]
            
            return json_text
            
        except Exception as e:
            logger.warning(f"⚠️ 修复缺失逗号时出错: {e}")
            return json_text
    
    def _fix_property_names(self, json_text: str) -> str:
        """修复属性名格式错误 - 处理 'Expecting property name enclosed in double quotes' 错误"""
        try:
            # 1. 修复未引用的属性名
            json_text = re.sub(r'([^"\s\{\[,]\w+):', r'"\1":', json_text)
            
            # 2. 修复单引号属性名
            json_text = re.sub(r"'([^']+)':", r'"\1":', json_text)
            
            # 3. 修复逗号后直接跟值的情况（缺失属性名）
            # 这种情况通常发生在content_identifier字段缺失
            lines = json_text.split('\n')
            fixed_lines = []
            
            for i, line in enumerate(lines):
                stripped = line.strip()
                
                # 检查是否是 , "value" 或 , value 模式（缺失属性名）
                if re.match(r'^,\s*"', stripped):
                    # 根据上下文添加合适的属性名
                    if 'content_identifier' in json_text.lower():
                        # 添加content_identifier属性
                        indent = len(line) - len(line.lstrip())
                        fixed_lines.append(' ' * indent + '"content_identifier": "unknown",')
                        # 移除行首的逗号
                        line = line.replace(',', '', 1)
                    elif 'relationship' in json_text.lower():
                        indent = len(line) - len(line.lstrip())
                        fixed_lines.append(' ' * indent + '"relationship": "unknown",')
                        line = line.replace(',', '', 1)
                
                # 4. 修复缺失引号的属性名
                if ':' in stripped and not stripped.startswith('"'):
                    # 查找属性名
                    colon_pos = stripped.find(':')
                    prop_name = stripped[:colon_pos].strip()
                    if prop_name and not prop_name.startswith('"'):
                        # 添加引号
                        rest = stripped[colon_pos:]
                        line = line.replace(stripped, f'"{prop_name}"{rest}')
                
                fixed_lines.append(line)
            
            return '\n'.join(fixed_lines)
            
        except Exception as e:
            logger.warning(f"⚠️ 修复属性名时出错: {e}")
            return json_text
    
    def _smart_truncate_response(self, response: str, max_length: int) -> str:
        """智能截断响应，优先保留JSON结构"""
        try:
            if len(response) <= max_length:
                return response
            
            # 1. 尝试找到JSON代码块
            json_patterns = [
                r'```json\s*(\{.*?\})\s*```',
                r'```\s*(\{.*?\})\s*```',
                r'(\{[^{}]*"thinking"[^{}]*\})'
            ]
            
            for pattern in json_patterns:
                match = re.search(pattern, response, re.DOTALL)
                if match:
                    json_content = match.group(1)
                    if len(json_content) <= max_length:
                        # 如果JSON内容不超过限制，返回完整JSON
                        logger.info(f"🎯 保留完整JSON结构 ({len(json_content)} 字符)")
                        return json_content
            
            # 2. 如果没有找到完整JSON，智能截断
            # 查找JSON开始位置
            json_start = -1
            for start_char in ['{', '[']:
                pos = response.find(start_char)
                if pos != -1 and (json_start == -1 or pos < json_start):
                    json_start = pos
            
            if json_start != -1 and json_start < max_length:
                # 从JSON开始位置截断
                truncated = response[json_start:json_start + max_length]
                
                # 尝试找到一个合理的结束点
                # 优先在完整的JSON对象结束
                brace_count = 0
                last_valid_pos = len(truncated)
                
                for i, char in enumerate(truncated):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            last_valid_pos = i + 1
                            break
                
                # 如果找到了完整的JSON对象
                if last_valid_pos < len(truncated):
                    result = truncated[:last_valid_pos]
                    logger.info(f"🎯 智能截断保留完整JSON对象 ({len(result)} 字符)")
                    return result
                
                # 否则在最后一个换行符处截断
                last_newline = truncated.rfind('\n', 0, max_length - 100)
                if last_newline > max_length // 2:
                    result = truncated[:last_newline]
                    logger.info(f"🎯 在换行符处截断 ({len(result)} 字符)")
                    return result
                
                logger.info(f"🎯 从JSON开始位置截断 ({len(truncated)} 字符)")
                return truncated
            
            # 3. 简单截断策略
            # 尝试在句子边界截断
            truncated = response[:max_length]
            sentence_ends = ['.', '!', '?', '。', '！', '？', '\n']
            
            for end_char in sentence_ends:
                last_pos = truncated.rfind(end_char, max_length - 200)
                if last_pos > max_length // 2:
                    result = truncated[:last_pos + 1]
                    logger.info(f"🎯 在句子边界截断 ({len(result)} 字符)")
                    return result
            
            # 最后的简单截断
            logger.info(f"🎯 简单截断 ({max_length} 字符)")
            return response[:max_length]
            
        except Exception as e:
            logger.warning(f"⚠️ 智能截断失败: {e}")
            return response[:max_length]
    
    def _lightweight_json_repair(self, json_text: str) -> Optional[str]:
        """轻量级JSON修复，处理常见小错误"""
        try:
            # 1. 修复常见的引号错误
            json_text = re.sub(r'([^\\])"([^"]*)"([^:])', r'\1"\2"\3', json_text)
            
            # 2. 修复缺失的逗号（字符串后直接跟字符串）
            json_text = re.sub(r'(")\s*\n\s*(")', r'\1,\n\2', json_text)
            
            # 3. 修复多余的逗号
            json_text = re.sub(r',\s*([}\]])', r'\1', json_text)
            
            # 4. 修复缺失的冒号
            json_text = re.sub(r'"([^"]+)"\s+(["{[])', r'"\1": \2', json_text)
            
            return json_text
            
        except Exception as e:
            logger.debug(f"轻量级修复失败: {e}")
            return None
    
    def _reconstruct_json_structure(self, json_text: str) -> Optional[str]:
        """重建JSON结构，从破损的JSON中提取关键信息"""
        try:
            # 提取关键字段的值
            fields = {}
            
            # 提取thinking字段
            thinking_match = re.search(r'"thinking":\s*"([^"]*(?:\\.[^"]*)*)"', json_text, re.DOTALL)
            if thinking_match:
                fields['thinking'] = thinking_match.group(1)
            else:
                # 查找STEP开头的内容作为thinking
                step_match = re.search(r'(STEP[^"]*?)(?:"|$)', json_text, re.DOTALL)
                if step_match:
                    fields['thinking'] = step_match.group(1)[:500]  # 限制长度
            
            # 提取action字段
            action_match = re.search(r'"action":\s*"([^"]+)"', json_text)
            if action_match:
                fields['action'] = action_match.group(1)
            
            # 提取tool_id字段
            tool_match = re.search(r'"tool_id":\s*"([^"]+)"', json_text)
            if tool_match:
                fields['tool_id'] = tool_match.group(1)
            
            # 提取confidence字段
            conf_match = re.search(r'"confidence":\s*([0-9.]+)', json_text)
            if conf_match:
                fields['confidence'] = float(conf_match.group(1))
            
            # 提取parameters字段（简化处理）
            params_match = re.search(r'"parameters":\s*(\{[^}]*\})', json_text)
            if params_match:
                try:
                    fields['parameters'] = json.loads(params_match.group(1))
                except:
                    fields['parameters'] = {}
            
            # 如果提取到了关键字段，重建JSON
            if len(fields) >= 2:  # 至少有2个字段才重建
                reconstructed = {
                    'thinking': fields.get('thinking', 'No thinking extracted'),
                    'action': fields.get('action', 'search_and_install_tools'),
                    'tool_id': fields.get('tool_id', 'mcp-search-tool'),
                    'parameters': fields.get('parameters', {}),
                    'confidence': fields.get('confidence', 0.7)
                }
                
                logger.info(f"🔧 重建JSON结构，提取了 {len(fields)} 个字段")
                return json.dumps(reconstructed, ensure_ascii=False)
            
            return None
            
        except Exception as e:
            logger.debug(f"JSON结构重建失败: {e}")
            return None
    
    def _smart_extract_from_response(self, response: str) -> Optional[Dict[str, Any]]:
        """从原始响应中智能提取字段，无需完整JSON"""
        try:
            result = {}
            
            # 1. 提取thinking - 查找STEP开头或thinking字段
            thinking_patterns = [
                r'STEP 1[^:]*:([^"]*?)(?:STEP 2|$)',
                r'"thinking":\s*"([^"]*(?:\\.[^"]*)*)"',
                r'thinking["\']?\s*[:=]\s*["\']([^"\']*)["\']'
            ]
            
            for pattern in thinking_patterns:
                match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
                if match:
                    result['thinking'] = match.group(1).strip()[:1000]  # 限制长度
                    break
            
            if not result.get('thinking'):
                result['thinking'] = response[:300]  # 使用响应前300字符作为thinking
            
            # 2. 智能推断action
            action_keywords = {
                'search_and_install_tools': ['搜索', 'search', '查找', '工具', 'tool', 'install'],
                'analyze_tool_needs': ['分析', 'analyze', '需要', 'need', '评估'],
                'complete_task': ['完成', 'complete', '结束', 'finish', '总结', 'summary']
            }
            
            response_lower = response.lower()
            action_scores = {}
            
            for action, keywords in action_keywords.items():
                score = sum(1 for keyword in keywords if keyword in response_lower)
                if score > 0:
                    action_scores[action] = score
            
            if action_scores:
                result['action'] = max(action_scores.items(), key=lambda x: x[1])[0]
            else:
                result['action'] = 'search_and_install_tools'  # 默认action
            
            # 3. 推断tool_id
            tool_patterns = [
                r'"tool_id":\s*"([^"]+)"',
                r'"tool":\s*"([^"]+)"',
                r'tool["\']?\s*[:=]\s*["\']([^"\']+)["\']'
            ]
            
            for pattern in tool_patterns:
                match = re.search(pattern, response, re.IGNORECASE)
                if match:
                    result['tool_id'] = match.group(1)
                    break
            
            if not result.get('tool_id'):
                # 基于action推断tool_id
                if result['action'] in ['search_and_install_tools', 'analyze_tool_needs']:
                    result['tool_id'] = 'mcp-search-tool'
                else:
                    result['tool_id'] = 'deepsearch-mcp-server'
            
            # 4. 提取confidence
            conf_patterns = [
                r'"confidence":\s*([0-9.]+)',
                r'confidence["\']?\s*[:=]\s*([0-9.]+)'
            ]
            
            for pattern in conf_patterns:
                match = re.search(pattern, response)
                if match:
                    try:
                        result['confidence'] = float(match.group(1))
                        break
                    except:
                        pass
            
            if 'confidence' not in result:
                result['confidence'] = 0.8  # 默认置信度
            
            # 5. 提取或生成parameters
            result['parameters'] = {}
            
            # 尝试提取task_description
            if result['action'] in ['search_and_install_tools', 'analyze_tool_needs']:
                # 从thinking中提取任务描述
                thinking = result.get('thinking', '')
                if 'TASK ANALYSIS:' in thinking:
                    task_start = thinking.find('TASK ANALYSIS:') + len('TASK ANALYSIS:')
                    task_end = thinking.find('STEP 2', task_start)
                    if task_end == -1:
                        task_end = task_start + 200
                    task_desc = thinking[task_start:task_end].strip()
                    if task_desc:
                        result['parameters']['task_description'] = task_desc[:200]
            
            # 向后兼容
            result['tool'] = result['tool_id']
            
            logger.info(f"🎯 智能提取完成: action={result['action']}, tool_id={result['tool_id']}")
            return result
            
        except Exception as e:
            logger.warning(f"⚠️ 智能提取失败: {e}")
            return None
    
    def _robust_extract_fields(self, response: str) -> Optional[Dict[str, Any]]:
        """健壮的字段提取器 - 最终防线，即使JSON完全无法解析也能提取核心信息"""
        try:
            logger.info("🛡️ 使用健壮字段提取器作为最终防线")
            result = {}
            
            # 1. 提取thinking字段 - 使用多个策略
            thinking_extracted = False
            
            # 策略1: 查找thinking字段（宽松匹配）
            thinking_patterns = [
                r'["\']?thinking["\']?\s*[:：]\s*["\']([^"\']*)["\']',
                r'thinking\s*[:：]\s*([^,}\n]*)',
                r'STEP\s*1[^:]*[:：]([^"]*?)(?:STEP\s*2|action|tool_id|$)',
                r'任务分析[^:]*[:：]([^"]*?)(?:步骤|STEP|action|$)'
            ]
            
            for pattern in thinking_patterns:
                match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
                if match:
                    thinking_content = match.group(1).strip()
                    if len(thinking_content) > 10:  # 确保内容有意义
                        result['thinking'] = thinking_content[:1000]
                        thinking_extracted = True
                        logger.debug(f"🔍 提取thinking成功 (模式: {pattern[:30]}...)")
                        break
            
            if not thinking_extracted:
                # 备用策略：使用响应的前部分作为thinking
                response_clean = re.sub(r'[{}"\[\],]', ' ', response)
                sentences = response_clean.split('.')[:3]  # 取前3句
                result['thinking'] = '. '.join(sentences)[:500]
                logger.debug("🔍 使用响应前部分作为thinking")
            
            # 2. 提取action字段 - 智能推断
            action_patterns = [
                r'["\']?action["\']?\s*[:：]\s*["\']([^"\']*)["\']',
                r'action\s*[:：]\s*([a-zA-Z_]+)',
                r'需要(搜索|查找|安装).*工具',
                r'(搜索|search).*工具',
                r'(分析|analyze).*需要'
            ]
            
            action_found = False
            for pattern in action_patterns:
                match = re.search(pattern, response, re.IGNORECASE)
                if match:
                    if '搜索' in match.group(0) or 'search' in match.group(0).lower():
                        result['action'] = 'search_and_install_tools'
                    elif '分析' in match.group(0) or 'analyze' in match.group(0).lower():
                        result['action'] = 'analyze_tool_needs'
                    else:
                        extracted_action = match.group(1) if len(match.groups()) > 0 else 'search_and_install_tools'
                        result['action'] = extracted_action
                    action_found = True
                    logger.debug(f"🔍 提取action成功: {result['action']}")
                    break
            
            if not action_found:
                # 基于关键词推断action
                if any(keyword in response.lower() for keyword in ['搜索', 'search', '工具', 'tool', '安装', 'install']):
                    result['action'] = 'search_and_install_tools'
                elif any(keyword in response.lower() for keyword in ['分析', 'analyze', '需要', 'need']):
                    result['action'] = 'analyze_tool_needs'
                else:
                    result['action'] = 'search_and_install_tools'  # 默认
                logger.debug(f"🔍 基于关键词推断action: {result['action']}")
            
            # 3. 提取tool_id字段
            tool_patterns = [
                r'["\']?tool_id["\']?\s*[:：]\s*["\']([^"\']*)["\']',
                r'["\']?tool["\']?\s*[:：]\s*["\']([^"\']*)["\']',
                r'工具ID\s*[:：]\s*([^\s,}]*)',
                r'使用.*工具\s*[:：]?\s*([a-zA-Z0-9_-]+)'
            ]
            
            tool_found = False
            for pattern in tool_patterns:
                match = re.search(pattern, response, re.IGNORECASE)
                if match:
                    tool_id = match.group(1).strip()
                    if tool_id and len(tool_id) > 2:  # 确保tool_id有意义
                        result['tool_id'] = tool_id
                        tool_found = True
                        logger.debug(f"🔍 提取tool_id成功: {tool_id}")
                        break
            
            if not tool_found:
                # 基于action推断tool_id
                if result['action'] in ['search_and_install_tools', 'analyze_tool_needs']:
                    result['tool_id'] = 'mcp-search-tool'
                else:
                    result['tool_id'] = 'deepsearch-mcp-server'
                logger.debug(f"🔍 基于action推断tool_id: {result['tool_id']}")
            
            # 4. 提取或生成parameters
            result['parameters'] = {}
            
            # 尝试提取task_description
            if result['action'] in ['search_and_install_tools', 'analyze_tool_needs']:
                # 从thinking中提取任务描述的关键部分
                thinking = result.get('thinking', '')
                
                # 查找任务相关的描述
                task_patterns = [
                    r'任务[:：]([^。\n]*)',
                    r'TASK[^:]*[:：]([^.\n]*)',
                    r'需要([^。\n]*工具[^。\n]*)',
                    r'要求([^。\n]*)'
                ]
                
                for pattern in task_patterns:
                    match = re.search(pattern, thinking, re.IGNORECASE)
                    if match:
                        task_desc = match.group(1).strip()
                        if len(task_desc) > 5:
                            result['parameters']['task_description'] = task_desc[:200]
                            logger.debug(f"🔍 提取task_description成功")
                            break
                
                # 如果没有找到具体的任务描述，使用thinking的摘要
                if not result['parameters'].get('task_description'):
                    # 提取thinking中的关键词作为任务描述
                    keywords = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', thinking)
                    if keywords:
                        task_summary = ' '.join(keywords[:15])  # 取前15个词
                        result['parameters']['task_description'] = task_summary
                        logger.debug("🔍 生成task_description摘要")
            
            # 5. 设置confidence和其他字段
            result['confidence'] = 0.6  # 健壮提取器的置信度较低
            result['tool'] = result['tool_id']  # 向后兼容
            
            # 6. 验证提取结果的质量
            if len(result.get('thinking', '')) < 5:
                logger.warning("健壮提取器: thinking字段质量不足")
                return None
            
            if not result.get('action') or not result.get('tool_id'):
                logger.warning("健壮提取器: 缺少关键字段")
                return None
            
            logger.info(f"🛡️ 健壮字段提取成功: action={result['action']}, tool_id={result['tool_id']}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 健壮字段提取器失败: {e}")
            return None