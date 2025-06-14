"""
Browser Tool for Reasoning Runtime
支持网页导航、搜索、信息提取等操作
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from playwright.async_api import async_playwright, Browser, Page
import json
from core.browser_state_manager import state_manager
import uuid
from core.path_utils import get_screenshots_dir # Import get_screenshots_dir

logger = logging.getLogger(__name__)

class BrowserTool:
    """浏览器工具"""
    
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self._initialized = False
        self._init_lock = asyncio.Lock()  # 添加异步锁防止竞态条件
    
    async def initialize(self):
        """初始化浏览器（线程安全）"""
        async with self._init_lock:  # 使用锁确保只有一个初始化过程
            if self._initialized:
                return
            
            try:
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-dev-shm-usage']
                )
                self.page = await self.browser.new_page()
                self._initialized = True
                logger.info("Browser tool initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize browser: {e}")
                # 确保在初始化失败时清理已创建的资源
                await self._cleanup_on_init_failure()
                raise
    
    async def _cleanup_on_init_failure(self):
        """初始化失败时的清理"""
        try:
            if self.page:
                await self.page.close()
                self.page = None
            if self.browser:
                await self.browser.close()
                self.browser = None
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
        except Exception as cleanup_error:
            logger.error(f"Error during initialization cleanup: {cleanup_error}")
    
    async def _get_current_page_state(self, include_content=True) -> Dict[str, Any]:
        """获取当前页面的状态快照"""
        if not self._initialized or not self.page:
            return {"error": "Browser not initialized"}

        state = {
            "url": self.page.url,
            "title": await self.page.title(),
        }

        if include_content:
            try:
                # 只获取body内的可见文本，并进行截断，避免返回内容过长
                body_text = await self.page.inner_text('body')
                max_len = 500
                state["content_summary"] = (body_text[:max_len] + '...') if len(body_text) > max_len else body_text
            except Exception as e:
                logger.warning(f"Could not get page content summary: {e}")
                state["content_summary"] = "Could not retrieve content."

        return state

    async def navigate(self, url: str) -> Dict[str, Any]:
        """导航到指定URL"""
        await self.initialize()

        if not url or not isinstance(url, str) or not (url.startswith('http://') or url.startswith('https://')):
            logger.error(f"Invalid URL parameter for navigate: {url}")
            return {
                "success": False,
                "output": {
                    "error_type": "InvalidArgument",
                    "error": "URL parameter is missing or invalid. It must be a valid HTTP/HTTPS URL.",
                    "message": f"Failed to navigate due to invalid URL parameter: {url}"
                }
            }
        
        try:
            await self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            page_state = await self._get_current_page_state()
            
            return {
                "success": True,
                "output": page_state
            }
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")
            return {
                "success": False,
                "output": {
                    "error_type": "NavigationError",
                    "error": str(e),
                    "message": f"Failed to navigate to {url}"
                }
            }
    
    async def get_text(self, selector: Optional[str] = None) -> Dict[str, Any]:
        """获取页面文本内容"""
        if not self._initialized or not self.page:
            logger.warning("get_text called before browser initialization.")
            return {"success": False, "output": {"error": "Browser not initialized"}}

        # 如果提供了selector，但它是空字符串或非字符串，则视为无效
        if selector is not None: # Only validate if selector is provided
            if not isinstance(selector, str):
                logger.error(f"Invalid selector type for get_text: {selector} (type: {type(selector)})")
                return {
                    "success": False,
                    "output": {
                        "error_type": "InvalidArgument",
                        "error": f"Selector parameter must be a string or None, but got {type(selector)}."
                    }
                }
            if not selector.strip(): # Check if it's an empty or whitespace-only string
                logger.error(f"Empty or whitespace-only selector provided for get_text.")
                return {
                    "success": False,
                    "output": {
                        "error_type": "InvalidArgument",
                        "error": "Selector parameter cannot be an empty or whitespace-only string if provided. Omit for body text."
                    }
                }
            
        try:
            if selector:
                element = await self.page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                else:
                    logger.warning(f"Selector '{selector}' not found in page for get_text.")
                    return {
                        "success": False,
                        "output": {
                            "error_type": "ElementNotFound",
                            "error": f"Element with selector '{selector}' not found."
                        }
                    }
            else:
                text = await self.page.inner_text('body')
            
            return {
                "success": True,
                "output": {
                    "text": text,
                    "length": len(text)
                }
            }
        except Exception as e:
            logger.error(f"Error in get_text (selector: {selector}): {e}")
            return {
                "success": False,
                "output": {
                    "error_type": "ExecutionError",
                    "error": str(e)
                }
            }
    
    async def click(self, selector: str) -> Dict[str, Any]:
        """点击元素"""
        if not self._initialized or not self.page:
            logger.warning("click called before browser initialization.")
            return {"success": False, "output": {"error": "Browser not initialized"}}

        if not selector or not isinstance(selector, str) or not selector.strip():
            logger.error(f"Invalid selector for click: '{selector}'")
            return {
                "success": False,
                "output": {
                    "error_type": "InvalidArgument",
                    "error": "Selector parameter is missing, invalid, or empty."
                }
            }
        
        try:
            await self.page.click(selector, timeout=15000)
            # 等待潜在的导航或内容变化
            await self.page.wait_for_timeout(1000)
            
            page_state = await self._get_current_page_state()
            return {
                "success": True,
                "output": page_state
            }
        except Exception as e:
            logger.error(f"Failed to click '{selector}': {e}")
            # More specific error types could be determined by inspecting 'e'
            error_type_to_report = "ExecutionError"
            if "Timeout" in str(e) and "waiting for selector" in str(e).lower(): # More robust check
                error_type_to_report = "ElementNotFound"
            elif "is not visible" in str(e).lower() or "not interactable" in str(e).lower(): # Common Playwright errors
                error_type_to_report = "ElementNotInteractable"

            return {
                "success": False,
                "output": {
                    "error_type": error_type_to_report,
                    "error": str(e),
                    "message": f"Failed to click '{selector}'"
                }
            }
    
    async def type_text(self, selector: str, text: str) -> Dict[str, Any]:
        """在指定元素中输入文本"""
        if not self._initialized or not self.page:
            return {"success": False, "output": {"error": "Browser not initialized"}}

        if not all([selector, isinstance(selector, str), selector.strip(), text is not None, isinstance(text, str)]):
            return {
                "success": False,
                "output": {"error_type": "InvalidArgument", "error": "Invalid selector or text provided."}
            }
            
        try:
            await self.page.type(selector, text, timeout=15000)
            await self.page.wait_for_timeout(500)
            
            page_state = await self._get_current_page_state()
            return {
                "success": True,
                "output": page_state
            }
        except Exception as e:
            logger.error(f"Failed to type into '{selector}': {e}")
            return {
                "success": False,
                "output": {
                    "error_type": "ExecutionError",
                    "error": str(e)
                }
            }

    async def scroll(self, direction: str = 'down', pixels: int = 500) -> Dict[str, Any]:
        """滚动页面"""
        if not self._initialized or not self.page:
            return {"success": False, "output": {"error": "Browser not initialized"}}

        try:
            if direction == 'down':
                await self.page.evaluate(f"window.scrollBy(0, {pixels})")
            elif direction == 'up':
                await self.page.evaluate(f"window.scrollBy(0, -{pixels})")
            
            await self.page.wait_for_timeout(500)
            
            page_state = await self._get_current_page_state(include_content=False) # 滚动后通常不需要内容
            return {
                "success": True,
                "output": page_state
            }
        except Exception as e:
            logger.error(f"Failed to scroll: {e}")
            return {
                "success": False,
                "output": {
                    "error_type": "ExecutionError",
                    "error": str(e)
                }
            }

    async def screenshot(self, path: Optional[str] = None) -> Dict[str, Any]:
        """截屏"""
        if not self._initialized or not self.page:
            return {"success": False, "output": {"error": "Browser not initialized"}}
        try:
            if not path:
                screenshots_dir = get_screenshots_dir() # Use get_screenshots_dir
                screenshots_dir.mkdir(parents=True, exist_ok=True)
                path = str(screenshots_dir / f"screenshot_{uuid.uuid4()}.png")
            
            await self.page.screenshot(path=path)
            return {
                "success": True,
                "output": {
                   "path": path,
                   "message": f"Screenshot saved to {path}"
                }
            }
        except Exception as e: # Add except block
            logger.error(f"Failed to take screenshot: {e}")
            return {
                "success": False,
                "output": {
                    "error_type": "ScreenshotError",
                    "error": str(e),
                    "message": "Failed to take screenshot"
                }
            }
    
    async def cleanup(self):
        """清理资源"""
        try:
            if self.page:
                await self.page.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            self._initialized = False
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

# 全局浏览器工具实例
browser_tool = BrowserTool()
