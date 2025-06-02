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
    
    def __init__(self):
        self.reset()

    def reset(self):
        """Resets all tracked browser states."""
        self.current_url: Optional[str] = None
        self.current_page_title: Optional[str] = None
        self.navigation_history: List[NavigationEntry] = []
        self.last_extracted_text_snippet: Optional[str] = None
        self.available_links_on_page: List[LinkInfo] = []
        # Tracks errors for the current task execution (action_name, error_type_from_tool) -> count
        self.current_task_error_counts: Dict[Tuple[str, str], int] = {}
        logger.debug("BrowserStateManager has been reset.")

    def record_navigation_attempt(self, 
                                  url: str, 
                                  success: bool, 
                                  title: Optional[str] = None, 
                                  error_details: Optional[Dict[str, str]] = None):
        """
        Records a navigation attempt.
        If successful, updates current_url, current_page_title, and clears previous page's links/text.
        """
        timestamp = time.time()
        error_msg = None
        error_type_str = None
        if not success and error_details:
            error_msg = error_details.get("error", error_details.get("message"))
            error_type_str = error_details.get("error_type")

        entry = NavigationEntry(url, success, timestamp, title, error_msg, error_type_str)
        self.navigation_history.append(entry)

        if success:
            self.current_url = url
            self.current_page_title = title
            self.available_links_on_page = []  # Clear links from previous page
            self.last_extracted_text_snippet = None # Clear text from previous page
            logger.info(f"Navigation to '{url}' (Title: {title}) recorded as successful.")
        else:
            logger.warning(f"Navigation attempt to '{url}' failed. Error: {error_type_str} - {error_msg}")
            if error_type_str: # Record the error for this specific action
                 self.record_action_error("navigate", error_type_str, "browser")


    def record_text_extraction(self, text_content: str, snippet_length: int = 250):
        """Records extracted text, storing a snippet."""
        if text_content:
            self.last_extracted_text_snippet = text_content[:snippet_length] + \
                                               ("..." if len(text_content) > snippet_length else "")
        else:
            self.last_extracted_text_snippet = None
        logger.debug(f"Text extraction recorded. Snippet: '{self.last_extracted_text_snippet}'")

    def record_links_extracted(self, links_data: List[Dict[str, str]]):
        """Records links extracted from the current page."""
        self.available_links_on_page = [LinkInfo(**link_item) for link_item in links_data if 'href' in link_item and 'text' in link_item]
        logger.debug(f"Links extracted: {len(self.available_links_on_page)} links recorded.")

    def record_action_error(self, action_name: str, error_type: str, tool_name: str = "browser"):
        """Records an error encountered during a specific tool action."""
        key = (f"{tool_name}.{action_name}", error_type)
        self.current_task_error_counts[key] = self.current_task_error_counts.get(key, 0) + 1
        logger.warning(f"Error recorded for {key}: count {self.current_task_error_counts[key]}")

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

    def get_error_count(self, action_name: str, error_type: str, tool_name: str = "browser") -> int:
        """Gets the count of a specific error for a specific action."""
        key = (f"{tool_name}.{action_name}", error_type)
        return self.current_task_error_counts.get(key, 0)

# 全局 BrowserStateManager 实例，供各模块使用
state_manager = BrowserStateManager()