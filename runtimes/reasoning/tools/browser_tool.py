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

logger = logging.getLogger(__name__)

class BrowserTool:
    """浏览器工具"""
    
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self._initialized = False
    
    async def initialize(self):
        """初始化浏览器"""
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
            raise
    
    async def navigate(self, url: str) -> Dict[str, Any]:
        """导航到指定URL"""
        await self.initialize()

        if not url or not isinstance(url, str) or not (url.startswith('http://') or url.startswith('https://')):
            logger.error(f"Invalid URL parameter for navigate: {url}")
            return {
                "success": False,
                "error_type": "InvalidArgument",
                "error": "URL parameter is missing or invalid. It must be a valid HTTP/HTTPS URL.",
                "message": f"Failed to navigate due to invalid URL parameter: {url}"
            }
        
        try:
            # 使用更合理的超时和等待策略，参考 AGENT_IMPROVEMENT_PLAN.md
            # 默认超时可以设置在 playwright.chromium.launch 或 new_page 中，这里用默认的
            # wait_until='networkidle' 可能会很慢，先尝试 'domcontentloaded'
            await self.page.goto(url, wait_until='domcontentloaded', timeout=30000) # 30秒超时
            title = await self.page.title()
            content = await self.page.content() # 获取内容可能较慢，如果只是导航确认，可以考虑移除或仅获取头部
            
            result = {
                "success": True,
                "url": url,
                "title": title,
                "content_length": len(content),
                "message": f"Successfully navigated to {url}"
            }
            # 更新浏览器状态
            state_manager.record_navigation_attempt(url, True, title)
            urls_and_texts = await self.page.eval_on_selector_all('a[href]', 'els => els.map(e => [e.href, e.textContent.trim()])')
            links_data = [{"href": href, "text": text} for href, text in urls_and_texts]
            state_manager.record_links_extracted(links_data)
            state_manager.record_text_extraction(content)
            return result
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")
            error_info = {
                "success": False,
                "error_type": "NavigationError",
                "error": str(e),
                "message": f"Failed to navigate to {url}"
            }
            # 记录错误状态
            error_details = {"error": str(e), "error_type": "NavigationError"}
            state_manager.record_navigation_attempt(url, False, error_details=error_details)
            return error_info
    
    async def get_text(self, selector: Optional[str] = None) -> Dict[str, Any]:
        """获取页面文本内容"""
        if not self._initialized or not self.page:
            logger.warning("get_text called before browser initialization.")
            return {"success": False, "error_type": "BrowserError", "error": "Browser not initialized"}

        # 如果提供了selector，但它是空字符串或非字符串，则视为无效
        if selector is not None: # Only validate if selector is provided
            if not isinstance(selector, str):
                logger.error(f"Invalid selector type for get_text: {selector} (type: {type(selector)})")
                return {
                    "success": False,
                    "error_type": "InvalidArgument",
                    "error": f"Selector parameter must be a string or None, but got {type(selector)}.",
                    "message": "Failed to get text due to invalid selector type."
                }
            if not selector.strip(): # Check if it's an empty or whitespace-only string
                logger.error(f"Empty or whitespace-only selector provided for get_text.")
                return {
                    "success": False,
                    "error_type": "InvalidArgument",
                    "error": "Selector parameter cannot be an empty or whitespace-only string if provided. Omit for body text.",
                    "message": "Failed to get text due to empty or whitespace-only selector."
                }
            
        try:
            if selector: # selector is not None and a non-empty string here
                element = await self.page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                else:
                    logger.warning(f"Selector '{selector}' not found in page for get_text.")
                    return {
                        "success": False,
                        "error_type": "ElementNotFound",
                        "error": f"Element with selector '{selector}' not found.",
                        "text": "", # Explicitly return empty text and length 0
                        "length": 0
                    }
            else: # selector is None, get body text
                text = await self.page.inner_text('body') # Default to body if selector is None
            
            return {
                "success": True,
                "text": text,
                "length": len(text)
            }
        except Exception as e:
            logger.error(f"Error in get_text (selector: {selector}): {e}")
            return {
                "success": False,
                "error_type": "ExecutionError",
                "error": str(e)
            }
    
    async def click(self, selector: str) -> Dict[str, Any]:
        """点击元素"""
        if not self._initialized or not self.page:
            logger.warning("click called before browser initialization.")
            return {"success": False, "error_type": "BrowserError", "error": "Browser not initialized"}

        if not selector or not isinstance(selector, str) or not selector.strip():
            logger.error(f"Invalid selector for click: '{selector}'")
            return {
                "success": False,
                "error_type": "InvalidArgument",
                "error": "Selector parameter is missing, invalid, or empty. It must be a non-empty string.",
                "message": f"Failed to click due to invalid selector: '{selector}'"
            }
        
        try:
            # Added a timeout for click, e.g., 15 seconds
            await self.page.click(selector, timeout=15000)
            # Reduced wait or make it conditional, e.g., only if expecting navigation
            await self.page.wait_for_timeout(500)
            return {
                "success": True,
                "message": f"Successfully clicked '{selector}'"
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
                "error_type": error_type_to_report,
                "error": str(e),
                "message": f"Failed to click '{selector}'"
            }
    
    async def fill_form(self, selector: str, value: str) -> Dict[str, Any]:
        """填写表单"""
        if not self._initialized or not self.page:
            return {"success": False, "error": "Browser not initialized"}
        
        try:
            await self.page.fill(selector, value)
            return {
                "success": True,
                "message": f"Successfully filled {selector} with value"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to fill {selector}"
            }
    
    async def screenshot(self, path: Optional[str] = None) -> Dict[str, Any]:
        """截屏"""
        if not self._initialized or not self.page:
            return {"success": False, "error": "Browser not initialized"}
        
        try:
            if not path:
                path = f"/tmp/screenshot_{int(asyncio.get_event_loop().time())}.png"
            
            await self.page.screenshot(path=path)
            return {
                "success": True,
                "path": path,
                "message": f"Screenshot saved to {path}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def extract_links(self) -> Dict[str, Any]:
        """提取页面链接"""
        if not self._initialized or not self.page:
            return {"success": False, "error": "Browser not initialized"}
        
        try:
            links = await self.page.evaluate("""
                () => {
                    const links = Array.from(document.querySelectorAll('a[href]'));
                    return links.map(link => ({
                        text: link.textContent.trim(),
                        href: link.href,
                        title: link.title || ''
                    }));
                }
            """)
            
            return {
                "success": True,
                "links": links,
                "count": len(links)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
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
