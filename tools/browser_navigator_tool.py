import asyncio
import logging
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse, urljoin
import re
import time
import os
import sys # Added sys import

try:
    from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    # Define dummy classes if playwright is not available to avoid runtime errors on import
    class Browser: pass
    class Page: pass
    class PlaywrightTimeoutError(Exception): pass
    class PlaywrightError(Exception): pass
    async def async_playwright(): raise ImportError("Playwright not installed")


try:
    from core.interfaces import LocalToolInterface, LocalToolSpec
except ImportError: # Fallback
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    from core.interfaces import LocalToolInterface, LocalToolSpec


logger = logging.getLogger(__name__)

class BrowserManager:
    """浏览器管理器，负责创建和管理浏览器实例"""
    _instance = None
    _lock = asyncio.Lock()


    def __new__(cls):
        # Standard singleton pattern, but __init__ should handle initialization logic
        if cls._instance is None:
            cls._instance = super(BrowserManager, cls).__new__(cls)
        return cls._instance


    def __init__(self):
        # Ensure __init__ is called only once
        if hasattr(self, '_initialized') and self._initialized:
            return

        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright 未安装。请运行 'pip install playwright' 并执行 'playwright install'")
            # No further initialization if Playwright is not available
            self._initialized = True # Mark as initialized to prevent re-entry
            return


        self.playwright_context = None # Stores the result of async_playwright()
        self.browser: Optional[Browser] = None
        self.pages: Dict[str, Page] = {} # page_id -> Page object
        self.default_timeout = 30000  # ms
        self.screenshot_dir = os.path.abspath("./screenshots") # Use absolute path

        os.makedirs(self.screenshot_dir, exist_ok=True)
        self._initialized = True
        self._launch_lock = asyncio.Lock() # Lock for launching browser
        logger.info("浏览器管理器初始化完成 (Playwright available).")


    async def start(self):
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not installed, cannot start browser.")

        async with self._launch_lock: # Ensure only one coroutine launches the browser
            if self.browser and self.browser.is_connected():
                logger.info("浏览器已启动且连接正常。")
                return

            try:
                logger.info("正在启动 Playwright...")
                self.playwright_context = await async_playwright().start()
                logger.info("正在启动 Chromium 浏览器...")
                self.browser = await self.playwright_context.chromium.launch(
                    headless=True,
                    args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"]
                )
                logger.info(f"浏览器已启动。版本: {self.browser.version}")
            except Exception as e:
                logger.error(f"启动浏览器失败: {e}", exc_info=True)
                # Clean up if partial launch occurred
                if self.playwright_context:
                    await self.playwright_context.stop()
                    self.playwright_context = None
                self.browser = None
                raise # Re-raise the exception to signal failure


    async def stop(self):
        if not PLAYWRIGHT_AVAILABLE: return

        logger.info("正在停止浏览器...")
        # Close all pages first
        for page_id in list(self.pages.keys()): # Iterate over a copy of keys
            await self.close_page(page_id)

        if self.browser:
            try:
                await self.browser.close()
                logger.info("浏览器已关闭。")
            except Exception as e:
                logger.error(f"关闭浏览器时出错: {e}", exc_info=True)
            finally:
                self.browser = None

        if self.playwright_context:
            try:
                await self.playwright_context.stop()
                logger.info("Playwright 已停止。")
            except Exception as e:
                logger.error(f"停止 Playwright 时出错: {e}", exc_info=True)
            finally:
                self.playwright_context = None
        self.pages.clear()


    async def get_page(self, page_id: Optional[str] = None, create_if_missing: bool = True) -> Optional[Page]:
        if not PLAYWRIGHT_AVAILABLE: return None
        if not self.browser or not self.browser.is_connected():
            await self.start() # Ensure browser is running

        if page_id and page_id in self.pages:
            page = self.pages[page_id]
            if page.is_closed(): # Check if page was closed externally or due to error
                logger.warning(f"页面 {page_id} 已关闭，将尝试重新创建。")
                del self.pages[page_id]
                if create_if_missing:
                    return await self._create_new_page(page_id)
                return None
            return page
        elif create_if_missing:
            return await self._create_new_page(page_id)
        return None

    async def _create_new_page(self, page_id: Optional[str] = None) -> Page:
        if not self.browser: # Should have been handled by get_page's start call
             raise RuntimeError("Browser not available to create new page.")

        new_page_id = page_id or f"page_{len(self.pages) + 1}_{int(time.time())}"
        page = await self.browser.new_page()
        await page.set_viewport_size({"width": 1280, "height": 800})
        await page.set_default_timeout(self.default_timeout)
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        })
        self.pages[new_page_id] = page
        logger.info(f"创建新页面: {new_page_id}")
        # Store the ID on the page object if playwright allows, or manage mapping
        # setattr(page, '_page_id', new_page_id) # Example, not standard playwright
        return page


    async def close_page(self, page_id: str) -> bool:
        if not PLAYWRIGHT_AVAILABLE: return False
        if page_id in self.pages:
            page = self.pages.pop(page_id) # Remove from dict first
            if not page.is_closed():
                try:
                    await page.close()
                    logger.info(f"关闭页面: {page_id}")
                except Exception as e:
                    logger.error(f"关闭页面 {page_id} 时出错: {e}")
                    # Add back to dict if close failed and page might still be usable? Or assume unusable.
            return True
        return False

    async def navigate(self, page_id: str, url: str, wait_until: str = "load") -> Dict[str, Any]:
        if not PLAYWRIGHT_AVAILABLE: return {"success": False, "error": "Playwright not available"}
        page = await self.get_page(page_id)
        if not page: return {"success": False, "error": f"无法获取页面: {page_id}"}
        actual_page_id = next(pid for pid, p in self.pages.items() if p == page) # Get actual ID

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        try:
            parsed_url = urlparse(url)
            if not parsed_url.netloc:
                return {"success": False, "error": f"无效的URL: {url}", "page_id": actual_page_id}

            logger.info(f"页面 {actual_page_id} 导航到: {url}")
            response = await page.goto(url, wait_until=wait_until, timeout=self.default_timeout) # type: ignore
            if not response:
                 return {"success": False, "error": "导航请求无响应", "page_id": actual_page_id}

            await page.wait_for_load_state("networkidle", timeout=self.default_timeout)
            title = await page.title()
            current_url = page.url
            screenshot_filename = f"{actual_page_id}_{parsed_url.netloc}_{int(time.time())}.png"
            screenshot_path = os.path.join(self.screenshot_dir, screenshot_filename)
            await page.screenshot(path=screenshot_path)

            return {"success": True, "title": title, "url": current_url, "status": response.status, "screenshot": screenshot_path, "page_id": actual_page_id}
        except PlaywrightTimeoutError:
            return {"success": False, "error": "导航超时", "page_id": actual_page_id}
        except PlaywrightError as e: # Catch more specific playwright errors
            logger.error(f"Playwright 导航错误 for {url} on page {actual_page_id}: {e}", exc_info=True)
            return {"success": False, "error": f"Playwright 导航错误: {str(e)}", "page_id": actual_page_id}
        except Exception as e:
            logger.error(f"导航失败 for {url} on page {actual_page_id}: {e}", exc_info=True)
            return {"success": False, "error": f"导航错误: {str(e)}", "page_id": actual_page_id}


    async def get_text(self, page_id: str, selector: Optional[str] = None) -> Dict[str, Any]:
        if not PLAYWRIGHT_AVAILABLE: return {"success": False, "error": "Playwright not available"}
        page = await self.get_page(page_id, create_if_missing=False) # Don't create if just getting text
        if not page: return {"success": False, "error": f"页面不存在: {page_id}"}
        actual_page_id = next(pid for pid, p in self.pages.items() if p == page)

        try:
            text_content = ""
            if selector:
                await page.wait_for_selector(selector, timeout=10000) # Increased timeout
                element = await page.query_selector(selector)
                if element:
                    text_content = (await element.text_content() or "").strip()
                else:
                    return {"success": False, "error": f"未找到元素: {selector}", "page_id": actual_page_id}
            else:
                body_handle = await page.query_selector('body')
                if body_handle:
                    text_content = (await body_handle.text_content() or "").strip()
                    text_content = re.sub(r'\s+', ' ', text_content) # Normalize whitespace
                    await body_handle.dispose()
                else:
                    return {"success": False, "error": "无法获取页面body内容", "page_id": actual_page_id}
            return {"success": True, "text": text_content, "selector": selector, "page_id": actual_page_id}
        except PlaywrightTimeoutError:
            return {"success": False, "error": f"等待元素超时: {selector}", "page_id": actual_page_id}
        except Exception as e:
            logger.error(f"获取文本失败 on page {actual_page_id}: {e}", exc_info=True)
            return {"success": False, "error": f"获取文本错误: {str(e)}", "page_id": actual_page_id}


    async def click(self, page_id: str, selector: str) -> Dict[str, Any]:
        if not PLAYWRIGHT_AVAILABLE: return {"success": False, "error": "Playwright not available"}
        page = await self.get_page(page_id, create_if_missing=False)
        if not page: return {"success": False, "error": f"页面不存在: {page_id}"}
        actual_page_id = next(pid for pid, p in self.pages.items() if p == page)

        try:
            await page.wait_for_selector(selector, timeout=10000)
            await page.click(selector, timeout=self.default_timeout) # Click also has timeout
            await page.wait_for_load_state("networkidle", timeout=self.default_timeout)
            title = await page.title()
            current_url = page.url
            return {"success": True, "title": title, "url": current_url, "clicked": selector, "page_id": actual_page_id}
        except PlaywrightTimeoutError:
            return {"success": False, "error": f"点击或等待元素/导航超时: {selector}", "page_id": actual_page_id}
        except Exception as e:
            logger.error(f"点击元素失败 on page {actual_page_id} for selector {selector}: {e}", exc_info=True)
            return {"success": False, "error": f"点击错误: {str(e)}", "page_id": actual_page_id}


    async def fill_form(self, page_id: str, form_data: Dict[str, str]) -> Dict[str, Any]:
        if not PLAYWRIGHT_AVAILABLE: return {"success": False, "error": "Playwright not available"}
        page = await self.get_page(page_id, create_if_missing=False)
        if not page: return {"success": False, "error": f"页面不存在: {page_id}"}
        actual_page_id = next(pid for pid, p in self.pages.items() if p == page)

        filled_fields, failed_fields = [], []
        try:
            for selector, value in form_data.items():
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                    await page.fill(selector, value, timeout=self.default_timeout)
                    filled_fields.append(selector)
                except Exception as field_e:
                    logger.warning(f"填充字段失败 {selector} on page {actual_page_id}: {field_e}")
                    failed_fields.append({"selector": selector, "error": str(field_e)})
            return {"success": len(failed_fields) == 0, "filled_fields": filled_fields, "failed_fields": failed_fields, "page_id": actual_page_id}
        except Exception as e:
            logger.error(f"填充表单失败 on page {actual_page_id}: {e}", exc_info=True)
            return {"success": False, "error": f"填充表单错误: {str(e)}", "page_id": actual_page_id}


    async def submit_form(self, page_id: str, form_selector: str) -> Dict[str, Any]:
        if not PLAYWRIGHT_AVAILABLE: return {"success": False, "error": "Playwright not available"}
        page = await self.get_page(page_id, create_if_missing=False)
        if not page: return {"success": False, "error": f"页面不存在: {page_id}"}
        actual_page_id = next(pid for pid, p in self.pages.items() if p == page)

        try:
            form_element = await page.wait_for_selector(form_selector, timeout=5000)
            if not form_element:
                return {"success": False, "error": f"未找到表单: {form_selector}", "page_id": actual_page_id}

            # Try to find a submit button within the form
            submit_button = await form_element.query_selector('button[type="submit"], input[type="submit"]')
            if submit_button:
                await submit_button.click(timeout=self.default_timeout)
            else:
                # Fallback: try to submit by evaluating JS if no standard button
                # This is less reliable and might not trigger all JS handlers
                await page.evaluate(f'document.querySelector("{form_selector}").submit()')

            await page.wait_for_load_state("networkidle", timeout=self.default_timeout)
            title = await page.title()
            current_url = page.url
            return {"success": True, "title": title, "url": current_url, "form": form_selector, "page_id": actual_page_id}
        except PlaywrightTimeoutError:
            return {"success": False, "error": f"提交表单或等待导航超时: {form_selector}", "page_id": actual_page_id}
        except Exception as e:
            logger.error(f"提交表单失败 on page {actual_page_id} for form {form_selector}: {e}", exc_info=True)
            return {"success": False, "error": f"提交表单错误: {str(e)}", "page_id": actual_page_id}


    async def take_screenshot(self, page_id: str, selector: Optional[str] = None) -> Dict[str, Any]:
        if not PLAYWRIGHT_AVAILABLE: return {"success": False, "error": "Playwright not available"}
        page = await self.get_page(page_id, create_if_missing=False)
        if not page: return {"success": False, "error": f"页面不存在: {page_id}"}
        actual_page_id = next(pid for pid, p in self.pages.items() if p == page)

        try:
            # Sanitize current URL for filename
            safe_url_part = re.sub(r'[^a-zA-Z0-9_-]', '_', page.url.split("://")[-1].split("/")[0])
            screenshot_filename = f"{actual_page_id}_{safe_url_part}_{int(time.time())}.png"
            screenshot_path = os.path.join(self.screenshot_dir, screenshot_filename)


            if selector:
                element = await page.wait_for_selector(selector, timeout=5000)
                if element:
                    await element.screenshot(path=screenshot_path)
                else: # Should not happen if wait_for_selector succeeded
                    return {"success": False, "error": f"未找到元素截图: {selector}", "page_id": actual_page_id}
            else:
                await page.screenshot(path=screenshot_path)
            return {"success": True, "screenshot": screenshot_path, "selector": selector, "page_id": actual_page_id}
        except PlaywrightTimeoutError:
            return {"success": False, "error": f"等待元素截图超时: {selector}", "page_id": actual_page_id}
        except Exception as e:
            logger.error(f"截图失败 on page {actual_page_id}: {e}", exc_info=True)
            return {"success": False, "error": f"截图错误: {str(e)}", "page_id": actual_page_id}


class BrowserNavigatorTool(LocalToolInterface):
    """浏览器导航工具"""

    def __init__(self):
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright not available. BrowserNavigatorTool will be non-functional.")
        # BrowserManager is a singleton, get its instance
        self.browser_manager = BrowserManager() if PLAYWRIGHT_AVAILABLE else None # type: ignore
        self._tool_spec = LocalToolSpec(
            tool_id="browser_navigator",
            name="浏览器导航工具",
            description="控制浏览器导航网页、获取内容和交互",
            version="1.1.0", # Updated version
            actions=[
                {"name": "navigate", "description": "导航到指定URL", "parameters": {
                    "url": {"type": "string", "description": "要导航到的URL", "required": True},
                    "page_id": {"type": "string", "description": "页面ID（可选, 会创建新页面或使用现有页面）", "required": False}
                }},
                {"name": "get_text", "description": "获取页面文本内容", "parameters": {
                    "page_id": {"type": "string", "description": "页面ID", "required": True},
                    "selector": {"type": "string", "description": "CSS选择器（可选, 获取特定元素文本）", "required": False}
                }},
                {"name": "click", "description": "点击页面元素", "parameters": {
                    "page_id": {"type": "string", "description": "页面ID", "required": True},
                    "selector": {"type": "string", "description": "要点击元素的CSS选择器", "required": True}
                }},
                {"name": "fill_form", "description": "填充表单字段", "parameters": {
                    "page_id": {"type": "string", "description": "页面ID", "required": True},
                    "form_data": {"type": "object", "description": "表单数据 (选择器: 值)", "required": True}
                }},
                {"name": "submit_form", "description": "提交表单", "parameters": {
                    "page_id": {"type": "string", "description": "页面ID", "required": True},
                    "form_selector": {"type": "string", "description": "表单的CSS选择器", "required": True}
                }},
                {"name": "take_screenshot", "description": "截取屏幕截图", "parameters": {
                    "page_id": {"type": "string", "description": "页面ID", "required": True},
                    "selector": {"type": "string", "description": "元素的CSS选择器（可选, 截取特定元素）", "required": False}
                }},
                {"name": "new_page", "description": "创建新的浏览器页面", "parameters": {
                    "page_id": {"type": "string", "description": "自定义页面ID（可选）", "required": False}
                }},
                {"name": "close_page", "description": "关闭浏览器页面", "parameters": {
                    "page_id": {"type": "string", "description": "页面ID", "required": True}
                }},
                {"name": "get_current_url", "description": "获取当前页面的URL", "parameters": {
                    "page_id": {"type": "string", "description": "页面ID", "required": True}
                }},
                {"name": "get_page_title", "description": "获取当前页面的标题", "parameters": {
                    "page_id": {"type": "string", "description": "页面ID", "required": True}
                }},
            ],
            type="function", # This tool is used like a function by the agent
            metadata={"category": "web", "icon": "browser", "requires_browser": True}
        )

    @property
    def tool_spec(self) -> LocalToolSpec:
        return self._tool_spec

    async def _ensure_browser_manager(self) -> bool:
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not available. Cannot execute browser actions.")
            return False
        if self.browser_manager is None: # Should not happen if constructor ran with Playwright
            logger.error("BrowserManager not initialized.")
            return False
        # Ensure browser is started within the manager
        if not self.browser_manager.browser or not self.browser_manager.browser.is_connected():
            try:
                await self.browser_manager.start()
            except Exception as e:
                logger.error(f"Failed to start browser manager: {e}")
                return False
        return True


    async def execute(self, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        if not await self._ensure_browser_manager():
             return {"success": False, "error": "浏览器管理器不可用或启动失败。"}
        # self.browser_manager is now assumed to be valid if _ensure_browser_manager returned True

        page_id = parameters.get("page_id") # Common parameter

        # Handle actions that might create a page or don't strictly need an existing one first
        if action == "new_page":
            custom_page_id = parameters.get("page_id") # User might provide a preferred ID
            page = await self.browser_manager._create_new_page(custom_page_id) # type: ignore
            actual_page_id = next(pid for pid, p in self.browser_manager.pages.items() if p == page) # type: ignore
            return {"success": True, "page_id": actual_page_id}

        # For other actions, ensure page_id is provided and page exists
        if not page_id and action not in ["new_page"]: # new_page handled above
            return {"success": False, "error": "page_id is required for this action."}

        # Get the page object using the manager
        page_obj = await self.browser_manager.get_page(page_id, create_if_missing=(action == "navigate")) # type: ignore
        if not page_obj:
            # If navigate action and page couldn't be created/retrieved by get_page
            if action == "navigate":
                 return {"success": False, "error": f"无法创建或获取页面 {page_id} 进行导航。"}
            return {"success": False, "error": f"页面 {page_id} 不存在或无法访问。"}
        # Update page_id to the actual ID used/created by BrowserManager
        page_id = next(pid for pid, p in self.browser_manager.pages.items() if p == page_obj) # type: ignore


        if action == "navigate":
            url = parameters.get("url")
            if not url: return {"success": False, "error": "URL is required for navigation."}
            return await self.browser_manager.navigate(page_id, str(url)) # type: ignore
        elif action == "get_text":
            selector = parameters.get("selector")
            return await self.browser_manager.get_text(page_id, selector) # type: ignore
        elif action == "click":
            selector = parameters.get("selector")
            if not selector: return {"success": False, "error": "Selector is required for click."}
            return await self.browser_manager.click(page_id, str(selector)) # type: ignore
        elif action == "fill_form":
            form_data = parameters.get("form_data")
            if not form_data: return {"success": False, "error": "Form data is required."}
            return await self.browser_manager.fill_form(page_id, form_data) # type: ignore
        elif action == "submit_form":
            form_selector = parameters.get("form_selector")
            if not form_selector: return {"success": False, "error": "Form selector is required."}
            return await self.browser_manager.submit_form(page_id, str(form_selector)) # type: ignore
        elif action == "take_screenshot":
            selector = parameters.get("selector")
            return await self.browser_manager.take_screenshot(page_id, selector) # type: ignore
        elif action == "close_page":
            success = await self.browser_manager.close_page(page_id) # type: ignore
            return {"success": success, "page_id": page_id, "message": "Page closed" if success else "Failed to close page"}
        elif action == "get_current_url":
            if page_obj:
                return {"success": True, "url": page_obj.url, "page_id": page_id}
            return {"success": False, "error": "Page not available", "page_id": page_id}
        elif action == "get_page_title":
            if page_obj:
                return {"success": True, "title": await page_obj.title(), "page_id": page_id}
            return {"success": False, "error": "Page not available", "page_id": page_id}
        else:
            return {"success": False, "error": f"不支持的动作: {action}"}

    async def shutdown(self):
        if self.browser_manager:
            await self.browser_manager.stop()
        logger.info("BrowserNavigatorTool shutdown.")