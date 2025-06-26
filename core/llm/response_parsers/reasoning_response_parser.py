import json
import logging
import re
from typing import Dict, Any, List, Optional

from core.llm.response_parsers.interfaces import IResponseParser
from core.llm.validation_middleware import validation_middleware, ResponseValidationResult, validate_llm_response
from core.unified_tool_manager import get_tool_manager

logger = logging.getLogger(__name__)

class ReasoningResponseParser(IResponseParser):
    """
    用于解析LLM生成的推理响应的解析器。
    处理复杂的JSON提取、验证和修正逻辑。
    """
    
    def __init__(self):
        """初始化响应解析器"""
        self.tool_schema_manager = None  # 通过依赖注入设置
    
    def set_tool_schema_manager(self, tool_schema_manager):
        """🔒 P0-2修复：设置工具Schema管理器以支持动态验证"""
        self.tool_schema_manager = tool_schema_manager
        logger.debug("✅ 响应解析器已连接工具Schema管理器")

    def parse_response(self, response: str, **kwargs) -> Dict[str, Any]:
        """
        解析LLM的原始字符串响应，并将其转换为结构化的推理决策字典。
        
        Args:
            response (str): LLM的原始字符串响应。
            **kwargs: 额外的参数，目前未使用，但保留以符合接口。

        Returns:
            Dict[str, Any]: 包含解析后推理决策的字典。
        """
        logger.info(f"🔍 开始解析LLM响应 - 长度: {len(response)} 字符, 类型: {type(response)}")
        logger.debug(f"响应内容预览: {response[:200]}..." if len(response) > 200 else response)
        
        # 🔧 修复：自动处理超长响应，避免卡住
        MAX_RESPONSE_LENGTH = 5000  # 限制响应长度为5000字符
        if len(response) > MAX_RESPONSE_LENGTH:
            logger.warning(f"⚠️ 响应过长 ({len(response)} 字符)，启用智能截断...")
            response = self._smart_truncate_response(response, MAX_RESPONSE_LENGTH)
            logger.info(f"✅ 智能截断完成，新长度: {len(response)} 字符")
        
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
                    logger.debug(f"使用模式提取到JSON: {pattern}")
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
                
                # 🆕 P3增强：修复特定的分隔符错误
                json_text = self._fix_delimiter_errors(json_text)
                
                # 🔧 新增：修复控制字符问题 - 解决 "Invalid control character" 错误
                json_text = self._fix_control_characters(json_text)
                
                # 修复常见的JSON格式错误
                json_text = self._fix_json_formatting_errors(json_text)
                
                # 尝试解析JSON
                try:
                    parsed = json.loads(json_text)
                    logger.debug("JSON解析成功")
                    
                    # 🔍 智能字段补全和验证
                    result = self._validate_and_complete_parsed_response(parsed)
                    
                    # ✨ 新增：结构化预校验
                    validation_result = self._apply_structured_validation(result)
                    if validation_result.is_valid:
                        if validation_result.corrected:
                            logger.info("✅ 结构化校验通过（已自动纠正）")
                            result = validation_result.data
                        else:
                            logger.debug("✅ 结构化校验通过")
                    else:
                        logger.warning(f"⚠️ 结构化校验失败: {validation_result.error}")
                        # 继续使用原有的验证机制作为备选
                    
                    logger.info(f"✅ 响应解析成功 - action: {result.get('action')}, tool: {result.get('tool_id') or result.get('tool')}, confidence: {result.get('confidence')}")
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
        
        # 补全并验证tool_id字段 - 先推断tool_id，再验证action
        tool_id = parsed.get('tool_id') or parsed.get('tool')
        
        # 🔍 智能推断工具ID（优先使用现有专业工具）
        if not tool_id:
            # 使用智能映射 - 优先基于action推断
            action_to_tool_mapping = {
                'research': 'mcp-deepsearch',
                'quick_research': 'mcp-deepsearch', 
                'comprehensive_research': 'mcp-deepsearch',
                'microsandbox_execute': 'microsandbox-mcp-server',
                'microsandbox_install_package': 'microsandbox-mcp-server',
                # 🔧 P0紧急修复1: 修正browser动作映射为实际存在的动作
                'browser_navigate': 'browser-use-mcp-server',
                'browser_use_execute_task': 'browser-use-mcp-server',
                'browser_click_element': 'browser-use-mcp-server',
                'browser_input_text': 'browser-use-mcp-server',
                'browser_extract_content': 'browser-use-mcp-server',
                'browser_search_google': 'browser-use-mcp-server',
                'search_and_install_tools': 'mcp-search-tool',
                'analyze_tool_needs': 'mcp-search-tool',
                'search_file_content': 'mcp-search-tool',
                'list_code_definitions': 'mcp-search-tool'
            }
            
            if action in action_to_tool_mapping:
                tool_id = action_to_tool_mapping[action]
                logger.debug(f"自动推断工具ID: {tool_id} (基于action: {action})")
            elif any(keyword in result['thinking'].lower() for keyword in ['deepsearch', '研究', 'research']):
                tool_id = 'mcp-deepsearch'
                logger.debug(f"基于thinking内容推断工具ID: {tool_id} (研究类任务)")
            elif any(keyword in result['thinking'].lower() for keyword in ['microsandbox', '代码', 'code', 'python']):
                tool_id = 'microsandbox-mcp-server' 
                logger.debug(f"基于thinking内容推断工具ID: {tool_id} (代码执行)")
            elif any(keyword in result['thinking'].lower() for keyword in ['browser', '浏览', '网页']):
                tool_id = 'browser-use-mcp-server'
                logger.debug(f"基于thinking内容推断工具ID: {tool_id} (网页浏览)")
            elif 'search' in result['thinking'].lower() and 'install' in result['thinking'].lower():
                tool_id = 'mcp-search-tool'
                logger.debug(f"基于thinking内容推断工具ID: {tool_id} (工具搜索)")
        
        # 现在使用正确推断的tool_id来验证action
        action = self._validate_and_correct_action(action, tool_id)
        result['action'] = action
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
        
        # 🔍 验证和纠正action
        # 验证和纠正action
        result['action'] = self._validate_and_correct_action(result['action'], result['tool_id'])
        
        # 🔍 智能推断和修正
        result = self._smart_inference_and_correction(result, response)
        
        # 向后兼容
        result['tool'] = result['tool_id']
        
        logger.debug(f"备用解析结果: action={result['action']}, tool_id={result['tool_id']}")
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
        
        # 🔍 基于任务内容智能推断action（优先使用现有工具）
        response_lower = response.lower()
        
        # 检查是否是特定工具的明确调用
        if any(keyword in response_lower for keyword in ['deepsearch', '研究', 'research']):
            return 'research'
        elif any(keyword in response_lower for keyword in ['microsandbox', '代码', 'code', 'python', '执行']):
            return 'microsandbox_execute'  
        elif any(keyword in response_lower for keyword in ['browser', '浏览', '网页', 'navigate']):
            return 'browser_navigate'
        elif any(keyword in response_lower for keyword in ['complete', 'finish', 'done']):
            return 'complete_task'
        # 只在真正需要搜索新工具时才使用搜索动作
        elif any(keyword in response_lower for keyword in ['analyze', 'need']) and 'install' not in response_lower:
            return 'analyze_tool_needs'
        elif 'install' in response_lower and 'search' in response_lower:
            return 'search_and_install_tools'
        
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
        """
        🔧 【核心修复】智能推断和修正结果 - 使用统一工具管理器
        
        解决工具ID映射不一致的关键方法：
        - 使用统一工具管理器获取标准工具ID
        - 动态生成动作到工具的映射关系
        - 避免硬编码旧版工具ID
        """
        
        # 限制文本长度，提高性能
        response_sample = response[:1000].lower()  # 只检查前1000字符
        
        # 🌟 【关键修复】使用统一工具管理器动态构建映射
        tool_manager = get_tool_manager()
        
        # 构建动作到标准工具ID的映射（使用统一工具管理器确保一致性）
        action_to_tool_mapping = {}
        try:
            # DeepSearch工具的动作映射
            deepsearch_id = tool_manager.get_standard_id('deepsearch')
            for action in ['research', 'quick_research', 'comprehensive_research']:
                action_to_tool_mapping[action] = deepsearch_id
            
            # MicroSandbox工具的动作映射
            microsandbox_id = tool_manager.get_standard_id('microsandbox')
            microsandbox_actions = tool_manager.get_tool_actions(microsandbox_id)
            for action in microsandbox_actions:
                action_to_tool_mapping[action] = microsandbox_id
            
            # Browser Use工具的动作映射
            browser_id = tool_manager.get_standard_id('browser_use')
            browser_actions = tool_manager.get_tool_actions(browser_id)
            for action in browser_actions:
                action_to_tool_mapping[action] = browser_id
            
            # Search Tool工具的动作映射
            search_id = tool_manager.get_standard_id('mcp-search-tool')
            search_actions = tool_manager.get_tool_actions(search_id)
            for action in search_actions:
                action_to_tool_mapping[action] = search_id
                
            logger.debug(f"🔧 动态构建动作映射: {len(action_to_tool_mapping)} 个动作")
            
        except Exception as e:
            logger.warning(f"⚠️ 构建动作映射失败，使用备用映射: {e}")
            # 备用映射（使用标准ID）
            action_to_tool_mapping = {
                'research': 'deepsearch',
                'quick_research': 'deepsearch', 
                'comprehensive_research': 'deepsearch',
                'microsandbox_execute': 'microsandbox',
                'microsandbox_install_package': 'microsandbox',
                'browser_navigate': 'browser_use',
                'browser_extract_content': 'browser_use',
                'browser_click_element': 'browser_use',
                'search_and_install_tools': 'mcp-search-tool',
                'analyze_tool_needs': 'mcp-search-tool'
            }
        
        # 如果没有tool_id，基于action智能推断
        if not result['tool_id'] and result['action'] in action_to_tool_mapping:
            result['tool_id'] = action_to_tool_mapping[result['action']]
            logger.debug(f"🎯 基于action({result['action']})智能推断标准tool_id: {result['tool_id']}")
        
        # 🔧 【关键修复】如果action是error，基于响应内容智能推断工具和动作（使用标准ID）
        if result['action'] == 'error':
            try:
                if any(keyword in response_sample for keyword in ['deepsearch', '研究', 'research']):
                    result['action'] = 'research'
                    result['tool_id'] = tool_manager.get_standard_id('deepsearch')
                    logger.debug(f"🔧 修正为使用标准工具进行研究: {result['tool_id']}")
                elif any(keyword in response_sample for keyword in ['microsandbox', '代码', 'code', 'python', '执行']):
                    result['action'] = 'microsandbox_execute'
                    result['tool_id'] = tool_manager.get_standard_id('microsandbox')
                    logger.debug(f"🔧 修正为使用标准工具执行代码: {result['tool_id']}")
                elif any(keyword in response_sample for keyword in ['browser', '浏览', '网页', 'navigate']):
                    result['action'] = 'browser_navigate'
                    result['tool_id'] = tool_manager.get_standard_id('browser_use')
                    logger.debug(f"🔧 修正为使用标准工具浏览网页: {result['tool_id']}")
                elif any(keyword in response_sample for keyword in ['mcp-search', 'search_and_install', 'tool']) and 'install' in response_sample:
                    result['action'] = 'search_and_install_tools'
                    result['tool_id'] = tool_manager.get_standard_id('mcp-search-tool')
                    logger.debug(f"🔧 修正为使用标准工具搜索: {result['tool_id']}")
            except Exception as e:
                logger.warning(f"⚠️ 智能修正失败，保持原始结果: {e}")
        
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
        
        # 4. 修复 "Extra data" 错误
        json_text = self._fix_extra_data(json_text)
        
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
    
    def _fix_control_characters(self, json_text: str) -> str:
        """修复JSON中的控制字符问题 - 关键修复方法"""
        try:
            # 移除或转义常见的控制字符
            control_char_fixes = {
                '\b': '\\b',    # 退格符
                '\f': '\\f',    # 换页符  
                '\r': '\\r',    # 回车符
                '\t': '\\t',    # 制表符
                '\v': '\\v',    # 垂直制表符
                '\0': '',       # 空字符，直接移除
            }
            
            for char, replacement in control_char_fixes.items():
                json_text = json_text.replace(char, replacement)
            
            # 移除其他ASCII控制字符 (0-31, 除了已处理的)
            import re
            # 保留必要的控制字符：\n (10), \r (13), \t (9)
            # 移除其他控制字符
            json_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', json_text)
            
            # 修复Unicode控制字符
            # 移除常见的Unicode控制字符
            unicode_control_chars = [
                '\u0000', '\u0001', '\u0002', '\u0003', '\u0004', '\u0005', '\u0006', '\u0007',
                '\u0008', '\u000B', '\u000C', '\u000E', '\u000F', '\u0010', '\u0011', '\u0012',
                '\u0013', '\u0014', '\u0015', '\u0016', '\u0017', '\u0018', '\u0019', '\u001A',
                '\u001B', '\u001C', '\u001D', '\u001E', '\u001F', '\u007F'
            ]
            
            for char in unicode_control_chars:
                json_text = json_text.replace(char, '')
            
            # 修复特定的控制字符错误模式（基于日志中的错误）
            # "Invalid control character at: line X column Y"
            
            # 1. 修复行尾的控制字符
            json_text = re.sub(r'[\x00-\x1F]+$', '', json_text, flags=re.MULTILINE)
            
            # 2. 修复字符串值中的控制字符
            def fix_string_control_chars(match):
                content = match.group(1)
                # 转义或移除字符串中的控制字符
                content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', content)
                # 确保换行符正确转义
                content = content.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                return f'": "{content}"'
            
            # 修复字符串值中的控制字符
            json_text = re.sub(r'": "([^"]*)"', fix_string_control_chars, json_text)
            
            # 3. 修复JSON结构中的控制字符（在键名和标点符号附近）
            json_text = re.sub(r'([\{\[,:])\s*[\x00-\x1F]+\s*', r'\1 ', json_text)
            json_text = re.sub(r'\s*[\x00-\x1F]+\s*([\}\],:])', r' \1', json_text)
            
            logger.debug("已修复JSON控制字符")
            return json_text
            
        except Exception as e:
            logger.warning(f"修复控制字符时出错: {e}")
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
            
            # 增强修复：处理更多边界情况
            # 修复属性名后的中文冒号
            json_text = re.sub(r'(["\'])(\s*)：(\s*)', r'\1\2:\3', json_text)
            
            # 修复值后的中文逗号
            json_text = re.sub(r'(["\'\d}])(\s*)，(\s*)', r'\1\2,\3', json_text)
            
            # 修复混合中英文标点的情况
            json_text = re.sub(r'([a-zA-Z0-9_])(\s*)：(\s*)', r'\1\2:\3', json_text)
            
            logger.debug("已修复中文标点符号")
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
    
    def _fix_missing_colons(self, json_text: str) -> str:
        """修复缺失冒号的错误"""
        try:
            # 修复属性名后缺失冒号的情况："key" "value" -> "key": "value"
            json_text = re.sub(r'("[^"]*")\s+("[^"]*")', r'\1: \2', json_text)
            
            # 修复属性名后有等号而不是冒号的情况："key" = "value" -> "key": "value"
            json_text = re.sub(r'("[^"]*")\s*=\s*', r'\1: ', json_text)
            
            return json_text
        except Exception as e:
            logger.warning(f"修复缺失冒号时出错: {e}")
            return json_text
    
    def _fix_missing_commas(self, json_text: str) -> str:
        """修复缺失逗号的错误"""
        try:
            # 修复对象属性之间缺失逗号：}"key" -> },"key"
            json_text = re.sub(r'}\s*"', '},"', json_text)
            
            # 修复字符串之间缺失逗号："value1" "key2" -> "value1", "key2"
            json_text = re.sub(r'("(?:[^"\\]|\\.)*")\s+("(?:[^"\\]|\\.)*"\s*:)', r'\1, \2', json_text)
            
            # 修复数值后缺失逗号：123 "key" -> 123, "key"
            json_text = re.sub(r'(\d+)\s+("[^"]*"\s*:)', r'\1, \2', json_text)
            
            return json_text
        except Exception as e:
            logger.warning(f"修复缺失逗号时出错: {e}")
            return json_text
    
    def _fix_property_names(self, json_text: str) -> str:
        """修复属性名未加引号的错误"""
        try:
            # 修复未引用的属性名：key: "value" -> "key": "value"
            json_text = re.sub(r'(\n\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', json_text)
            
            # 修复开头的未引用属性名
            json_text = re.sub(r'^(\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', json_text, flags=re.MULTILINE)
            
            return json_text
        except Exception as e:
            logger.warning(f"修复属性名时出错: {e}")
            return json_text
    
    def _fix_extra_data(self, json_text: str) -> str:
        """修复JSON后有额外数据的错误"""
        try:
            # 找到第一个完整的JSON对象并截断其后的内容
            depth = 0
            in_string = False
            escape_next = False
            end_pos = -1
            
            for i, char in enumerate(json_text):
                if escape_next:
                    escape_next = False
                    continue
                    
                if char == '\\':
                    escape_next = True
                    continue
                    
                if char == '"':
                    in_string = not in_string
                    continue
                    
                if in_string:
                    continue
                    
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        end_pos = i + 1
                        break
            
            if end_pos > 0:
                json_text = json_text[:end_pos]
            
            return json_text
        except Exception as e:
            logger.warning(f"修复额外数据时出错: {e}")
            return json_text
    
    def _fix_delimiter_errors(self, json_text: str) -> str:
        """修复分隔符错误"""
        try:
            # 这个函数可能之前缺失，添加基本实现
            # 修复分号代替逗号的情况
            json_text = re.sub(r'("[^"]*")\s*;\s*("[^"]*")', r'\1, \2', json_text)
            
            # 修复其他常见分隔符错误
            json_text = re.sub(r'("[^"]*")\s*\|\s*("[^"]*")', r'\1, \2', json_text)
            
            return json_text
        except Exception as e:
            logger.warning(f"修复分隔符错误时出错: {e}")
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
                # 智能推断默认工具基于任务内容
                default_action = 'error'
                default_tool_id = None
                
                # 基于内容推断合适的默认值
                response_lower = response.lower()
                if any(keyword in response_lower for keyword in ['deepsearch', '研究', 'research']):
                    default_action = 'research'
                    default_tool_id = 'mcp-deepsearch'
                elif any(keyword in response_lower for keyword in ['microsandbox', '代码', 'code', 'python', '执行']):
                    default_action = 'microsandbox_execute'
                    default_tool_id = 'microsandbox-mcp-server'
                elif any(keyword in response_lower for keyword in ['browser', '浏览', '网页', 'navigate']):
                    default_action = 'browser_navigate'
                    default_tool_id = 'browser-use-mcp-server'
                elif 'search' in response_lower and 'install' in response_lower:
                    default_action = 'search_and_install_tools'
                    default_tool_id = 'mcp-search-tool'
                
                reconstructed = {
                    'thinking': fields.get('thinking', 'No thinking extracted'),
                    'action': fields.get('action', default_action),
                    'tool_id': fields.get('tool_id', default_tool_id),
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
                # 基于action推断tool_id（使用智能映射）
                action_to_tool_mapping = {
                    'research': 'mcp-deepsearch',
                    'quick_research': 'mcp-deepsearch', 
                    'comprehensive_research': 'mcp-deepsearch',
                    'microsandbox_execute': 'microsandbox-mcp-server',
                    'microsandbox_install_package': 'microsandbox-mcp-server',
                    'browser_navigate': 'browser-use-mcp-server',
                    'browser_extract_content': 'browser-use-mcp-server',
                    'browser_click_element': 'browser-use-mcp-server',
                    'search_and_install_tools': 'mcp-search-tool',
                    'analyze_tool_needs': 'mcp-search-tool'
                }
                
                if result['action'] in action_to_tool_mapping:
                    result['tool_id'] = action_to_tool_mapping[result['action']]
                else:
                    # 基于内容进一步推断
                    response_lower = response.lower()
                    if any(keyword in response_lower for keyword in ['deepsearch', '研究', 'research']):
                        result['tool_id'] = 'mcp-deepsearch'
                    elif any(keyword in response_lower for keyword in ['microsandbox', '代码', 'code', 'python']):
                        result['tool_id'] = 'microsandbox-mcp-server'
                    elif any(keyword in response_lower for keyword in ['browser', '浏览', '网页']):
                        result['tool_id'] = 'browser-use-mcp-server'
                    else:
                        result['tool_id'] = 'mcp-deepsearch'  # 默认使用研究工具
            
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
            
            logger.debug(f"智能提取完成: action={result['action']}, tool_id={result['tool_id']}")
            return result
            
        except Exception as e:
            logger.warning(f"智能提取失败: {e}")
            return None
    
    def _identify_task_type(self, response_lower: str) -> str:
        """智能识别任务类型"""
        # 研究类任务关键词（优先级最高）
        research_keywords = ['deepsearch', '研究', 'research', 'asyncio', '基本概念', '用法', '最佳实践', '调研']
        if any(keyword in response_lower for keyword in research_keywords):
            return 'research'
        
        # 代码执行类任务
        code_keywords = ['microsandbox', '代码', 'code', 'python', '执行', 'execute', '运行', 'script']
        if any(keyword in response_lower for keyword in code_keywords):
            return 'code'
        
        # 浏览器类任务
        browser_keywords = ['browser', '浏览', '网页', 'navigate', 'url', 'website', '访问']
        if any(keyword in response_lower for keyword in browser_keywords):
            return 'browser'
        
        # 工具搜索类任务（最低优先级）
        tool_search_keywords = ['search_and_install', 'analyze_tool_needs', '安装工具', '搜索工具']
        if any(keyword in response_lower for keyword in tool_search_keywords):
            return 'tool_search'
        
        return 'unknown'
    
    def _robust_extract_fields(self, response: str) -> Optional[Dict[str, Any]]:
        """健壮的字段提取器 - 最终防线，增强版本with智能上下文分析"""
        try:
            logger.debug("使用健壮字段提取器")
            result = {}
            
            # 🔧 增强：预处理响应，提取关键信息
            response_lower = response.lower()
            
            # 智能任务类型识别（基于上下文）
            task_type = self._identify_task_type(response_lower)
            # 识别任务类型
            
            # 1. 提取thinking字段 - 更智能的策略
            thinking_extracted = False
            
            # 策略1: 查找thinking字段（宽松匹配）
            thinking_patterns = [
                r'["\']?thinking["\']?\s*[:：]\s*["\']([^"\']*)["\']',
                r'thinking\s*[:：]\s*([^,}\n]*)',
                r'STEP\s*1[^:]*[:：]([^"]*?)(?:STEP\s*2|action|tool_id|$)',
                r'任务分析[^:]*[:：]([^"]*?)(?:步骤|STEP|action|$)',
                r'Brief\s*[^:]*[:：]([^"]*?)(?:tool|action|$)'  # 新增：适配简化格式
            ]
            
            for pattern in thinking_patterns:
                match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
                if match:
                    thinking_content = match.group(1).strip()
                    if len(thinking_content) > 10:  # 确保内容有意义
                        result['thinking'] = thinking_content[:500]  # 缩短thinking长度
                        thinking_extracted = True
                        logger.debug(f"🔍 提取thinking成功 (模式: {pattern[:30]}...)")
                        break
            
            if not thinking_extracted:
                # 备用策略：基于任务类型生成简化thinking
                result['thinking'] = f"Task type: {task_type}, using appropriate tool"
                logger.debug("🔍 生成基于任务类型的thinking")
            
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
                    # action提取成功
                    break
            
            if not action_found:
                # 🔧 增强：基于识别的任务类型智能推断action
                action_mapping = {
                    'research': 'research',
                    'code': 'microsandbox_execute', 
                    'browser': 'browser_navigate',
                    'tool_search': 'search_and_install_tools',
                    'unknown': 'research'  # 默认为研究任务
                }
                
                result['action'] = action_mapping.get(task_type, 'research')
                # 基于任务类型推断action
            
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
                        # tool_id提取成功
                        break
            
            if not tool_found:
                # 基于action推断tool_id（使用智能映射）
                action_to_tool_mapping = {
                    'research': 'mcp-deepsearch',
                    'quick_research': 'mcp-deepsearch', 
                    'comprehensive_research': 'mcp-deepsearch',
                    'microsandbox_execute': 'microsandbox-mcp-server',
                    'microsandbox_install_package': 'microsandbox-mcp-server',
                    'browser_navigate': 'browser-use-mcp-server',
                    'browser_extract_content': 'browser-use-mcp-server',
                    'browser_click_element': 'browser-use-mcp-server',
                    'search_and_install_tools': 'mcp-search-tool',
                    'analyze_tool_needs': 'mcp-search-tool'
                }
                
                if result['action'] in action_to_tool_mapping:
                    result['tool_id'] = action_to_tool_mapping[result['action']]
                else:
                    # 基于内容进一步推断
                    response_lower = response.lower()
                    if any(keyword in response_lower for keyword in ['deepsearch', '研究', 'research']):
                        result['tool_id'] = 'mcp-deepsearch'
                    elif any(keyword in response_lower for keyword in ['microsandbox', '代码', 'code', 'python']):
                        result['tool_id'] = 'microsandbox-mcp-server'
                    elif any(keyword in response_lower for keyword in ['browser', '浏览', '网页']):
                        result['tool_id'] = 'browser-use-mcp-server'
                    else:
                        result['tool_id'] = 'mcp-deepsearch'  # 默认使用研究工具
                
                # 基于action推断tool_id
            
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
                            # task_description提取成功
                            break
                
                # 如果没有找到具体的任务描述，使用thinking的摘要
                if not result['parameters'].get('task_description'):
                    # 提取thinking中的关键词作为任务描述
                    keywords = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', thinking)
                    if keywords:
                        task_summary = ' '.join(keywords[:15])  # 取前15个词
                        result['parameters']['task_description'] = task_summary
                        # 生成task_description摘要
            
            # 5. 验证和纠正action（重要：健壮提取器也需要验证）
            result['action'] = self._validate_and_correct_action(result['action'], result['tool_id'])
            
            # 6. 设置confidence和其他字段
            result['confidence'] = 0.6  # 健壮提取器的置信度较低
            result['tool'] = result['tool_id']  # 向后兼容
            
            # 7. 验证提取结果的质量
            if len(result.get('thinking', '')) < 5:
                logger.warning("健壮提取器: thinking字段质量不足")
                return None
            
            if not result.get('action') or not result.get('tool_id'):
                logger.warning("健壮提取器: 缺少关键字段")
                return None
            
            logger.debug(f"健壮字段提取成功: action={result['action']}, tool_id={result['tool_id']}")
            return result
            
        except Exception as e:
            logger.error(f"健壮字段提取器失败: {e}")
            return None
    
    def _apply_structured_validation(self, result: Dict[str, Any]) -> ResponseValidationResult:
        """
        应用结构化工具校验
        使用新的预校验中间件进行严格的Schema校验
        """
        try:
            # 使用校验中间件
            is_valid, validated_data, error = validation_middleware.validate_before_llm_call(result)
            
            if is_valid:
                # 检查数据是否被修改（自动纠正）
                corrected = (result != validated_data)
                return ResponseValidationResult(True, validated_data, None, corrected)
            else:
                return ResponseValidationResult(False, result, error, False)
                
        except Exception as e:
            logger.debug(f"结构化校验过程出错: {str(e)}")
            return ResponseValidationResult(False, result, str(e), False)

    def _validate_and_correct_action(self, action: str, tool_id: Optional[str]) -> str:
        """
        🔧 【核心修复】验证和纠正action - 使用统一工具管理器
        
        解决动作验证不一致的问题：
        - 使用统一工具管理器进行动作验证
        - 支持智能纠正和建议
        - 避免复杂的异步调用问题
        """
        # 如果没有tool_id，无法验证
        if not tool_id:
            return action
        
        # 🌟 【关键修复】使用统一工具管理器进行同步验证
        try:
            tool_manager = get_tool_manager()
            
            # 先规范化tool_id
            standard_tool_id = tool_manager.get_standard_id(tool_id)
            
            # 检查动作是否有效
            if tool_manager.is_valid_action(standard_tool_id, action):
                logger.debug(f"✅ 动作验证通过: {standard_tool_id}.{action}")
                return action
            
            # 如果动作无效，尝试智能纠正
            valid_actions = tool_manager.get_tool_actions(standard_tool_id)
            
            # 尝试模糊匹配
            normalized_action = action.lower().replace('_', '').replace('-', '')
            for valid_action in valid_actions:
                normalized_valid = valid_action.lower().replace('_', '').replace('-', '')
                if normalized_action == normalized_valid:
                    logger.warning(f"⚠️ Action智能纠正: {action} -> {valid_action}")
                    return valid_action
            
            # 如果无法纠正，记录警告并返回默认动作
            default_action = tool_manager.get_default_action(standard_tool_id)
            logger.warning(f"Action验证失败: {action} 不存在于 {standard_tool_id}，尝试纠正")
            logger.warning(f"🔧 有效动作: {valid_actions}")
            logger.warning(f"🎯 使用默认动作: {default_action}")
            
            return default_action
            
        except Exception as e:
            logger.warning(f"⚠️ 动作验证失败，保持原始动作: {e}")
            return action
    
    
    def _fix_delimiter_errors(self, json_text: str) -> str:
        """修复特定的分隔符错误 - P3增强方法"""
        try:
            # 🔧 P3修复：处理"Expecting ':' delimiter: line 2 column 13"类错误
            
            # 0. 预处理：移除BOM和特殊字符
            json_text = json_text.replace('\ufeff', '').replace('\u200b', '')  # 移除BOM和零宽字符
            
            # 1. 通用JSON修复
            # 修复常见的属性名缺少引号问题 - 但排除已经有引号的
            json_text = re.sub(r'([^"\w])(\w+):', r'\1"\2":', json_text)
            # 修复字符串值缺少引号问题 - 更精确的模式
            json_text = re.sub(r':\s*([^",\[\]\{\}\s\d][^",\[\]\{\}]*?)([,\]\}])', r': "\1"\2', json_text)
            
            # 1. 修复第2行附近的分隔符错误
            lines = json_text.split('\n')
            if len(lines) >= 2:
                # 检查第2行（索引1）是否有分隔符问题
                line2 = lines[1].strip()
                if '"' in line2 and ':' not in line2 and not line2.startswith('}'):
                    # 可能是属性名后缺少冒号
                    # 查找 "属性名" 后面没有冒号的情况
                    fixed_line2 = re.sub(r'"([^"]+)"\s+([^:])', r'"\1": \2', line2)
                    if fixed_line2 != line2:
                        logger.debug("🔧 修复第2行缺失冒号")
                        lines[1] = fixed_line2
                
                # 检查是否是属性名和值之间缺少冒号
                if '"' in line2 and '"' in line2[1:]:
                    # 找到第一个和第二个引号之间的部分
                    quote_match = re.match(r'^(\s*"[^"]+")(\s*)([^:].*)$', line2)
                    if quote_match:
                        prop_name = quote_match.group(1)
                        spacing = quote_match.group(2)
                        value_part = quote_match.group(3)
                        lines[1] = f"{prop_name}:{spacing}{value_part}"
                        logger.debug("🔧 修复属性名和值之间缺少冒号")
            
            # 2. 修复特定位置的分隔符错误（基于column 13的提示）
            if len(lines) >= 2 and len(lines[1]) >= 13:
                char_at_13 = lines[1][12] if len(lines[1]) > 12 else ''
                if char_at_13 and char_at_13 not in [':', ',', '"', ' ']:
                    # 在第13位置附近可能缺少分隔符
                    line = lines[1]
                    before = line[:12]
                    after = line[12:]
                    
                    # 如果前面有引号，可能需要冒号
                    if before.count('"') % 2 == 0 and '"' in before:
                        lines[1] = before + ':' + after
                        logger.debug("🔧 修复第13列位置缺少冒号")
                        logger.debug("🔧 在第13列位置添加冒号")
                    # 如果需要逗号
                    elif before.endswith('"') or before.endswith('}'):
                        lines[1] = before + ',' + after
                        logger.debug("🔧 在第13列位置添加逗号")
            
            # 3. 修复通用的分隔符缺失
            for i, line in enumerate(lines):
                # 修复 "key" value 模式缺少冒号
                fixed_line = re.sub(r'"([^"]+)"\s+(["\d\[\{])', r'"\1": \2', line)
                # 修复 "key"后直接跟值而无冒号的情况
                fixed_line = re.sub(r'"([^"]+)"\s*([^:\s,\]\}][^,\]\}]*)', r'"\1": "\2"', fixed_line)
                if fixed_line != line:
                    lines[i] = fixed_line
                    logger.debug(f"🔧 修复第{i+1}行缺失冒号")
            
            # 4. 尝试更激进的修复策略
            result = '\n'.join(lines)
            
            # 检查是否仍有JSON错误，如果有则尝试更激进的修复
            try:
                json.loads(result)
                return result  # 已经是有效JSON
            except json.JSONDecodeError as e:
                if "Expecting ':' delimiter" in str(e):
                    logger.debug("🔧 使用激进修复策略")
                    # 尝试逐字符修复
                    result = self._aggressive_delimiter_fix(result)
            
            return result
            
        except Exception as e:
            logger.warning(f"⚠️ 修复分隔符错误时出现异常: {e}")
            return json_text
    
    def _aggressive_delimiter_fix(self, json_text: str) -> str:
        """激进的分隔符修复策略"""
        try:
            # 将文本转换为字符列表以便修改
            chars = list(json_text)
            in_string = False
            escape_next = False
            i = 0
            
            while i < len(chars):
                char = chars[i]
                
                if escape_next:
                    escape_next = False
                    i += 1
                    continue
                
                if char == '\\':
                    escape_next = True
                    i += 1
                    continue
                
                if char == '"':
                    in_string = not in_string
                    i += 1
                    continue
                
                if not in_string:
                    # 在JSON结构中，寻找可能缺少冒号的位置
                    if char == '"' and i + 1 < len(chars):
                        # 寻找下一个非空白字符
                        j = i + 1
                        while j < len(chars) and chars[j] in ' \t\n\r':
                            j += 1
                        
                        if j < len(chars) and chars[j] != ':' and chars[j] not in ',}]':
                            # 可能缺少冒号，插入冒号
                            chars.insert(j, ':')
                            chars.insert(j + 1, ' ')
                            logger.debug(f"🔧 在位置{j}插入冒号")
                            i = j + 2
                            continue
                
                i += 1
            
            return ''.join(chars)
            
        except Exception as e:
            logger.warning(f"⚠️ 激进修复失败: {e}")
            return json_text