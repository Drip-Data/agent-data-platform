import logging
import re
from typing import Dict, Any, Optional, Set

from core.llm.response_parsers.interfaces import IResponseParser

logger = logging.getLogger(__name__)


class ReasoningResponseParser(IResponseParser):
    """
    动态工具发现的响应解析器 - 根本性解决工具调用路由问题
    
    核心原则：
    1. 消除硬编码工具列表
    2. 动态发现所有可能的工具标识符  
    3. 统一处理工具名、动作名和别名
    4. 单一职责：仅负责结构化解析，不做工具验证
    """

    def __init__(self, tool_manager=None):
        """
        初始化动态解析器
        
        Args:
            tool_manager: 工具管理器，用于获取已知工具标识符
        """
        self.tool_manager = tool_manager
        self._known_identifiers_cache = None
        self._last_cache_update = 0
        
    def _get_all_tool_identifiers(self) -> Set[str]:
        """
        获取所有已知的工具标识符（工具名、动作名、别名）
        实现动态工具发现，消除硬编码
        """
        import time
        
        # 缓存机制：避免频繁查询
        current_time = time.time()
        if (self._known_identifiers_cache is None or 
            current_time - self._last_cache_update > 60):  # 1分钟缓存
            
            identifiers = set()
            
            # 添加固定的系统标识符
            identifiers.add("answer")
            
            if self.tool_manager:
                try:
                    # 获取所有工具ID
                    tool_ids = self.tool_manager.get_all_tool_ids() if hasattr(self.tool_manager, 'get_all_tool_ids') else []
                    identifiers.update(tool_ids)
                    
                    # 获取所有动作名
                    for tool_id in tool_ids:
                        actions = self.tool_manager.get_tool_actions(tool_id) if hasattr(self.tool_manager, 'get_tool_actions') else []
                        identifiers.update(actions)
                    
                    # 获取所有别名
                    if hasattr(self.tool_manager, 'get_all_aliases'):
                        aliases = self.tool_manager.get_all_aliases()
                        identifiers.update(aliases)
                        
                except Exception as e:
                    logger.warning(f"获取工具标识符失败，使用默认列表: {e}")
                    # 回退到基础工具列表
                    identifiers.update([
                        "microsandbox", "deepsearch", "browser_use", "search_tool",
                        "browser_use_execute_task", "microsandbox_execute"
                    ])
            else:
                # 无工具管理器时的默认标识符
                identifiers.update([
                    "microsandbox", "deepsearch", "browser_use", "search_tool", 
                    "browser_use_execute_task", "microsandbox_execute", "answer"
                ])
            
            self._known_identifiers_cache = identifiers
            self._last_cache_update = current_time
            
            logger.debug(f"🔄 更新工具标识符缓存: {len(identifiers)} 个标识符")
        
        return self._known_identifiers_cache

    def parse_response(self, response: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        动态解析LLM响应，支持所有已知工具标识符
        
        Args:
            response: LLM的原始字符串响应
            
        Returns:
            包含动作信息的字典，如果找不到有效动作则返回None
        """
        logger.info(f"🔍 动态解析响应 (长度: {len(response)})...")
        
        # 获取所有已知工具标识符
        known_identifiers = self._get_all_tool_identifiers()
        
        # 构建动态正则表达式 - 根本性消除硬编码
        identifiers_pattern = "|".join(re.escape(identifier) for identifier in known_identifiers)
        
        # 动态模式：<think>块 + 任何已知工具标识符
        pattern = re.compile(
            rf"(<think>.*?</think>)?\s*(<({identifiers_pattern})>(.*?)</\3>)",
            re.DOTALL
        )
        
        match = pattern.search(response)
        
        if not match:
            # 兜底：尝试匹配任何XML标签格式
            logger.debug("🔄 主要模式未匹配，尝试通用XML标签匹配...")
            fallback_pattern = re.compile(
                r"(<think>.*?</think>)?\s*(<([a-zA-Z_][a-zA-Z0-9_]*?)>(.*?)</\3>)",
                re.DOTALL
            )
            match = fallback_pattern.search(response)
            
            if match:
                tool_name = match.group(3)
                logger.info(f"🆕 发现未知工具标识符: <{tool_name}>，将进行动态处理")
            else:
                logger.warning("❌ 未找到任何有效的工具调用或答案标签")
                return None
        
        # 提取匹配组件
        thinking = (match.group(1) or "").strip()
        full_action_tag = match.group(2)
        tool_name = match.group(3)
        tool_input = (match.group(4) or "").strip()
        
        logger.info(f"✅ 发现动作: <{tool_name}>")
        
        if tool_name == "answer":
            return {
                "type": "answer",
                "thinking": thinking,
                "content": tool_input,
                "full_tag": full_action_tag
            }
        else:
            # 🔧 嵌套结构检测：如果tool_input包含XML标签，拒绝处理让XML解析器处理
            if self._contains_xml_structure(tool_input):
                logger.debug(f"🔄 检测到嵌套XML结构，回退到XML解析器处理: <{tool_name}>")
                return None
            
            # 标准化工具标识符 - 让工具管理器处理映射
            normalized_info = self._normalize_tool_identifier(tool_name)
            
            return {
                "type": "tool_call",
                "thinking": thinking,
                "tool_name": normalized_info["tool_id"],
                "action_name": normalized_info["action_name"], 
                "tool_input": tool_input,
                "full_tag": full_action_tag,
                "original_identifier": tool_name
            }
    
    def _normalize_tool_identifier(self, identifier: str) -> Dict[str, str]:
        """
        标准化工具标识符，解决工具名/动作名混淆问题
        
        Args:
            identifier: 原始标识符 (可能是工具名、动作名或别名)
            
        Returns:
            包含标准化tool_id和action_name的字典
        """
        if not self.tool_manager:
            # 回退处理：基于命名约定推断
            if "_" in identifier:
                # 可能是动作名格式: tool_action
                parts = identifier.split("_", 1)
                return {
                    "tool_id": parts[0], 
                    "action_name": identifier
                }
            else:
                # 可能是工具名
                return {
                    "tool_id": identifier,
                    "action_name": ""  # 让runtime决定默认动作
                }
        
        try:
            # 1. 首先检查是否是动作名（这是最常见的情况）
            if hasattr(self.tool_manager, 'find_tool_by_action'):
                tool_id = self.tool_manager.find_tool_by_action(identifier)
                if tool_id:
                    return {
                        "tool_id": tool_id,
                        "action_name": identifier
                    }
            
            # 2. 检查是否是已知工具ID
            if hasattr(self.tool_manager, 'is_valid_tool') and self.tool_manager.is_valid_tool(identifier):
                default_action = self._get_default_action(identifier)
                return {
                    "tool_id": identifier,
                    "action_name": default_action
                }
            
            # 3. 检查是否是别名
            if hasattr(self.tool_manager, 'resolve_alias'):
                resolved = self.tool_manager.resolve_alias(identifier)
                if resolved:
                    return resolved
            
            # 4. 智能推断：基于命名模式
            if identifier.startswith(("browser_", "microsandbox_", "deepsearch_")):
                # 格式: tool_action 
                if "browser_use_" in identifier:
                    return {
                        "tool_id": "browser_use",
                        "action_name": identifier
                    }
                elif "microsandbox_" in identifier:
                    return {
                        "tool_id": "microsandbox", 
                        "action_name": identifier
                    }
                elif "deepsearch_" in identifier:
                    return {
                        "tool_id": "deepsearch",
                        "action_name": identifier
                    }
                else:
                    # 通用处理：取第一个下划线前的部分作为工具名
                    parts = identifier.split("_", 1)
                    base_tool = parts[0]
                    
                    # 特殊映射
                    tool_mapping = {
                        "browser": "browser_use",
                        "microsandbox": "microsandbox", 
                        "deepsearch": "deepsearch"
                    }
                    
                    mapped_tool = tool_mapping.get(base_tool, base_tool)
                    return {
                        "tool_id": mapped_tool,
                        "action_name": identifier
                    }
            
            # 5. 默认处理：视为工具ID
            return {
                "tool_id": identifier,
                "action_name": ""
            }
            
        except Exception as e:
            logger.warning(f"工具标识符标准化失败: {e}")
            return {
                "tool_id": identifier,
                "action_name": ""
            }
    
    def _get_default_action(self, tool_id: str) -> str:
        """获取工具的默认动作"""
        try:
            if hasattr(self.tool_manager, 'get_default_action'):
                return self.tool_manager.get_default_action(tool_id) or ""
        except:
            pass
        
        # 硬编码默认动作 (临时方案)
        defaults = {
            "browser_use": "browser_use_execute_task",
            "microsandbox": "microsandbox_execute", 
            "deepsearch": "research",
            "search_tool": "search_file_content"
        }
        return defaults.get(tool_id, "")
    
    def _contains_xml_structure(self, text: str) -> bool:
        """
        检测文本是否包含XML结构（嵌套标签）
        
        Args:
            text: 要检测的文本
            
        Returns:
            bool: 如果包含XML标签结构则返回True
        """
        if not text or not isinstance(text, str):
            return False
        
        # 检查是否包含XML标签模式
        xml_pattern = r'<\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*[^>]*>.*?</\s*\1\s*>'
        
        # 简单的XML标签检测
        if re.search(xml_pattern, text, re.DOTALL):
            logger.debug(f"🔍 检测到XML结构: {text[:100]}...")
            return True
        
        # 检查是否包含未闭合的XML标签（可能是部分嵌套）
        if '<' in text and '>' in text:
            # 检查是否有XML标签格式
            tag_pattern = r'<[a-zA-Z_][a-zA-Z0-9_]*[^>]*>'
            if re.search(tag_pattern, text):
                logger.debug(f"🔍 检测到XML标签: {text[:100]}...")
                return True
        
        return False

    def set_tool_schema_manager(self, tool_schema_manager):
        """保持与旧接口的兼容性，但在此实现中未使用。"""
        pass
