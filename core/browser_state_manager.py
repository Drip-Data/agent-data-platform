# agent-data-platform/core/browser_state_manager.py

import time
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class NavigationEntry:
    """Represents a single navigation attempt in the history."""
    def __init__(self, 
                 url: str, 
                 success: bool, 
                 timestamp: float, 
                 title: Optional[str] = None, 
                 error: Optional[str] = None, 
                 error_type: Optional[str] = None):
        self.url = url
        self.success = success
        self.timestamp = timestamp
        self.title = title
        self.error = error
        self.error_type = error_type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "success": self.success,
            "timestamp": self.timestamp,
            "title": self.title,
            "error": self.error,
            "error_type": self.error_type,
        }

class LinkInfo:
    """Represents a hyperlink found on a page."""
    def __init__(self, text: str, href: str, title: Optional[str] = None):
        self.text = text
        self.href = href
        self.title = title

    def to_dict(self) -> Dict[str, Any]:
        return {"text": self.text, "href": self.href, "title": self.title}

class BrowserStateManager:
    """Manages and provides context about the current state of the browser interaction."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        # 默认配置
        self.default_config = {
            "max_history_size": 100,
            "max_text_length": 50000,
            "max_links_count": 200,
            "error_threshold": 10
        }
        
        # 合并用户配置和默认配置
        if config:
            self.config = {**self.default_config, **config}
        else:
            self.config = self.default_config.copy()
            
        self.reset()

    def reset(self):
        """Resets all tracked browser states."""
        self.current_url: Optional[str] = None
        self.current_page_title: Optional[str] = None
        self.current_title: Optional[str] = None  # 别名，用于测试兼容性
        self.navigation_history: List[NavigationEntry] = []
        self.last_extracted_text_snippet: Optional[str] = None
        self.extracted_text: str = ""  # 用于测试兼容性
        self.available_links_on_page: List[LinkInfo] = []
        self.extracted_links: List[Dict[str, str]] = []  # 用于测试兼容性
        self.action_errors: List[Dict[str, Any]] = []  # 用于测试兼容性
        # Tracks errors for the current task execution (action_name, error_type_from_tool) -> count
        self.current_task_error_counts: Dict[Tuple[str, str], int] = {}
        self.error_counts: Dict[str, int] = {}  # 用于测试兼容性
        logger.debug("BrowserStateManager has been reset.")

    def record_navigation_attempt(self, url: str, action: str = "navigate"):
        """测试兼容性方法：记录导航尝试"""
        timestamp = time.time()
        
        # 创建字典格式的历史记录条目
        attempt_entry = {
            "url": url,
            "action": action,
            "type": "attempt",
            "timestamp": timestamp
        }
        
        self.navigation_history.append(attempt_entry)
        
        # 限制历史记录大小
        max_history_size = self.config.get("max_history_size", 50)
        if len(self.navigation_history) > max_history_size:
            self.navigation_history = self.navigation_history[-max_history_size:]
        
        logger.info(f"Navigation attempt to '{url}' recorded.")
    
    def record_navigation(self, url: str, title: Optional[str], success: bool, load_time: float, error_message: Optional[str] = None):
        """
        测试兼容性方法：记录导航信息
        """
        timestamp = time.time()
        
        # 创建历史记录条目（作为字典，用于测试兼容性）
        history_entry = {
            "url": url,
            "title": title,
            "success": success,
            "load_time": load_time,
            "timestamp": timestamp
        }
        
        if error_message:
            history_entry["error_message"] = error_message
            
        self.navigation_history.append(history_entry)
        
        # 限制历史记录大小
        max_history_size = self.config.get("max_history_size", 50)
        if len(self.navigation_history) > max_history_size:
            self.navigation_history = self.navigation_history[-max_history_size:]
        
        if success:
            self.current_url = url
            self.current_page_title = title
            self.current_title = title
            self.available_links_on_page = []
            self.extracted_links = []
            self.last_extracted_text_snippet = None
            self.extracted_text = ""
            logger.info(f"Navigation to '{url}' (Title: {title}) recorded as successful.")
        else:
            logger.warning(f"Navigation attempt to '{url}' failed. Error: {error_message}")
            if error_message:
                self.action_errors.append({
                    "action": "navigate",
                    "error": error_message,
                    "timestamp": timestamp
                })


    def record_text_extraction(self, text_content: str, snippet_length: int = 250):
        """Records extracted text, storing a snippet."""
        if text_content:
            self.last_extracted_text_snippet = text_content[:snippet_length] + \
                                               ("..." if len(text_content) > snippet_length else "")
            # 同时更新测试兼容性属性
            self.extracted_text = text_content
        else:
            self.last_extracted_text_snippet = None
            self.extracted_text = ""
        logger.debug(f"Text extraction recorded. Snippet: '{self.last_extracted_text_snippet}'")

    def record_links_extracted(self, links_data: List[Dict[str, str]]):
        """Records links extracted from the current page."""
        self.available_links_on_page = [LinkInfo(**link_item) for link_item in links_data if 'href' in link_item and 'text' in link_item]
        # 同时更新测试兼容性属性
        self.extracted_links = [link_item for link_item in links_data if 'href' in link_item and 'text' in link_item]
        logger.debug(f"Links extracted: {len(self.available_links_on_page)} links recorded.")

    def _record_internal_error(self, action_name: str, error_type: str, tool_name: str = "browser"):
        """Records an error encountered during a specific tool action (internal method)."""
        key = (f"{tool_name}.{action_name}", error_type)
        self.current_task_error_counts[key] = self.current_task_error_counts.get(key, 0) + 1
        logger.warning(f"Error recorded for {key}: count {self.current_task_error_counts[key]}")
    
    def record_extracted_text(self, text_content: str):
        """测试兼容性方法：记录提取的文本"""
        if text_content:
            max_length = self.config.get("max_text_length", 10000)
            if len(text_content) > max_length:
                self.extracted_text = text_content[:max_length-3] + "..."
            else:
                self.extracted_text = text_content
            
            # 同时更新原有属性
            snippet_length = 250
            self.last_extracted_text_snippet = text_content[:snippet_length] + \
                                               ("..." if len(text_content) > snippet_length else "")
        else:
            self.extracted_text = ""
            self.last_extracted_text_snippet = None
        logger.debug(f"Text extraction recorded. Length: {len(self.extracted_text)}")
    
    def record_extracted_links(self, links_data):
        """测试兼容性方法：记录提取的链接"""
        if links_data is None:
            self.extracted_links = []
            self.available_links_on_page = []
            return
            
        max_count = self.config.get("max_links_count", 100)
        
        # 限制链接数量
        limited_links = links_data[:max_count] if len(links_data) > max_count else links_data
        
        self.extracted_links = limited_links
        # 同时更新原有属性
        self.available_links_on_page = [LinkInfo(**link_item) for link_item in limited_links if 'href' in link_item and 'text' in link_item]
        logger.debug(f"Links extracted: {len(self.extracted_links)} links recorded.")
    
    def record_action_error(self, action: str, error_message: str, selector: str = None, error_type: str = "Unknown"):
        """测试兼容性方法：记录操作错误"""
        error_entry = {
            "action": action,
            "error_message": error_message,
            "selector": selector,
            "error_type": error_type,
            "timestamp": time.time()
        }
        self.action_errors.append(error_entry)
        
        # 更新错误计数
        if error_type not in self.error_counts:
            self.error_counts[error_type] = 0
        self.error_counts[error_type] += 1
        
        logger.warning(f"Action error recorded: {action} - {error_message}")
    
    def reset_state(self):
        """测试兼容性方法：重置状态"""
        self.reset()
    
    def get_current_state(self):
        """测试兼容性方法：获取当前状态"""
        if self.current_url:
            return {
                "url": self.current_url,
                "title": self.current_title,
                "timestamp": time.time()
            }
        else:
            return {
                "url": None,
                "title": None,
                "timestamp": None
            }
    
    def has_recent_errors(self, minutes: int = 5):
        """测试兼容性方法：检查是否有最近的错误"""
        if not self.action_errors:
            return False
            
        current_time = time.time()
        time_threshold = current_time - (minutes * 60)
        
        for error in self.action_errors:
            if error.get("timestamp", 0) > time_threshold:
                return True
        return False
    
    def get_navigation_summary(self):
        """测试兼容性方法：获取导航摘要"""
        total_navigations = len(self.navigation_history)
        successful_navigations = sum(1 for entry in self.navigation_history if entry.get("success", False))
        failed_navigations = total_navigations - successful_navigations
        
        return {
            "total_navigations": total_navigations,
            "current_url": self.current_url,
            "successful_navigations": successful_navigations,
            "failed_navigations": failed_navigations
        }
    
    def get_state_summary_for_llm(self, max_history_items: int = 10, max_error_items: int = 5):
        """测试兼容性方法：获取LLM状态摘要"""
        # 当前页面信息
        current_page = {
            "url": self.current_url,
            "title": self.current_title
        }
        
        # 导航历史（限制数量）
        navigation_history = self.navigation_history[-max_history_items:] if self.navigation_history else []
        
        # 页面内容
        page_content = {
            "text": self.extracted_text,
            "links": self.extracted_links
        }
        
        # 最近错误（限制数量）
        recent_errors = self.action_errors[-max_error_items:] if self.action_errors else []
        
        # 错误统计
        total_errors = len(self.action_errors)
        error_types = {}
        for error in self.action_errors:
            error_type = error.get("error_type", "Unknown")
            error_types[error_type] = error_types.get(error_type, 0) + 1
        
        error_statistics = {
            "total_errors": total_errors,
            "error_types": error_types
        }
        
        return {
            "current_page": current_page,
            "navigation_history": navigation_history,
            "page_content": page_content,
            "recent_errors": recent_errors,
            "error_statistics": error_statistics
        }

    def get_context_for_llm(self) -> Dict[str, Any]:
        """
        Provides a structured summary of the current browser state, 
        intended for inclusion in the LLM prompt.
        """
        history_for_prompt = []
        # Provide last 2-3 navigation attempts
        for entry in self.navigation_history[-3:]:
            status = "Succeeded" if entry.success else f"Failed (Type: {entry.error_type or 'Unknown'}, Msg: {entry.error or 'N/A'})"
            title_str = f", Title: '{entry.title}'" if entry.title else ""
            history_for_prompt.append(f"- Nav to '{entry.url}'{title_str} - {status}")
        
        links_summary = f"{len(self.available_links_on_page)} links found on current page." \
                        if self.available_links_on_page else "No links extracted from current page yet."

        return {
            "current_url": self.current_url or "Not currently on any URL.",
            "current_page_title": self.current_page_title or "N/A",
            "recent_navigation_summary": "\n".join(history_for_prompt) if history_for_prompt else "No navigation attempts yet.",
            "last_text_snippet": self.last_extracted_text_snippet or "No text extracted recently.",
            "links_on_page_summary": links_summary,
        }

    def get_error_count(self, error_type: str = None) -> int:
        """测试兼容性方法：获取错误计数
        
        Args:
            error_type: 错误类型，如果为None则返回总错误数
            
        Returns:
            指定错误类型的计数或总错误数
        """
        if error_type is None:
            # 返回总错误数
            return len(self.action_errors)
        else:
            # 返回特定错误类型的计数
            return self.error_counts.get(error_type, 0)

# 全局 BrowserStateManager 实例，供各模块使用
state_manager = BrowserStateManager()