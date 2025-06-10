import asyncio
import logging
import time
from typing import Dict, List, Optional
from playwright.async_api import async_playwright, Browser, Page, BrowserContext, Locator
from bs4 import BeautifulSoup
import markdownify

logger = logging.getLogger(__name__)

class BrowserManager:
    """浏览器管理器 - 管理浏览器实例和页面池"""
    
    def __init__(self, max_browsers: int = 2, max_pages_per_browser: int = 4):
        self.max_browsers = max_browsers
        self.max_pages_per_browser = max_pages_per_browser
        self.playwright = None
        self.browsers: List[Browser] = []
        self.page_pools: Dict[Browser, List[Page]] = {}
        self.page_usage: Dict[Page, float] = {}
        self._lock = asyncio.Lock()
        
    async def initialize(self):
        """初始化浏览器管理器"""
        logger.info("Initializing browser manager")
        
        self.playwright = await async_playwright().start()
        
        # 启动浏览器实例
        for i in range(self.max_browsers):
            browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--memory-pressure-off',
                    '--max_old_space_size=512'
                ]
            )
            self.browsers.append(browser)
            self.page_pools[browser] = []
            
            logger.info(f"Browser {i+1} started")
        
        # 预创建页面
        await self._precreate_pages()
        
        # 启动清理任务
        asyncio.create_task(self._cleanup_task())
        
    async def _precreate_pages(self):
        """预创建页面"""
        for browser in self.browsers:
            for _ in range(2):  # 每个浏览器预创建2个页面
                page = await self._create_new_page(browser)
                self.page_pools[browser].append(page)
                
    async def _create_new_page(self, browser: Browser) -> Page:
        """创建新页面"""
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        
        page = await context.new_page()
        
        # 设置超时
        page.set_default_timeout(30000)
        page.set_default_navigation_timeout(30000)
        
        # 记录使用时间
        self.page_usage[page] = time.time()
        
        return page
        
    async def get_page(self) -> Page:
        """获取可用页面"""
        async with self._lock:
            # 寻找可用页面
            for browser in self.browsers:
                if self.page_pools[browser]:
                    page = self.page_pools[browser].pop()
                    self.page_usage[page] = time.time()
                    return page
            
            # 没有可用页面，创建新页面
            for browser in self.browsers:
                if len(self.page_pools[browser]) < self.max_pages_per_browser:
                    page = await self._create_new_page(browser)
                    self.page_usage[page] = time.time()
                    return page
            
            # 所有浏览器都满了，等待或重用最老的页面
            oldest_page = min(self.page_usage.keys(), key=lambda p: self.page_usage[p])
            await self._reset_page(oldest_page)
            self.page_usage[oldest_page] = time.time()
            return oldest_page
    
    async def return_page(self, page: Page):
        """归还页面到池中"""
        async with self._lock:
            try:
                # 清理页面状态
                await self._reset_page(page)
                
                # 找到对应的浏览器
                for browser, pool in self.page_pools.items():
                    if page.context.browser == browser:
                        if len(pool) < self.max_pages_per_browser:
                            pool.append(page)
                        else:
                            # 池满了，关闭页面
                            await page.close()
                            del self.page_usage[page]
                        break
                        
            except Exception as e:
                logger.error(f"Error returning page: {e}")
                try:
                    await page.close()
                    if page in self.page_usage:
                        del self.page_usage[page]
                except:
                    pass
    
    async def _reset_page(self, page: Page):
        """重置页面状态"""
        try:
            # 清除所有cookie和存储
            await page.context.clear_cookies()
            await page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
            
            # 导航到空白页
            await page.goto('about:blank')
            
        except Exception as e:
            logger.warning(f"Error resetting page: {e}")
    
    async def _cleanup_task(self):
        """定期清理任务"""
        while True:
            try:
                await asyncio.sleep(300)  # 每5分钟清理一次
                await self._cleanup_old_pages()
            except Exception as e:
                logger.error(f"Cleanup task error: {e}")
    
    async def _cleanup_old_pages(self):
        """清理长时间未使用的页面"""
        current_time = time.time()
        max_idle_time = 1800  # 30分钟
        
        async with self._lock:
            pages_to_remove = []
            
            for page, last_used in self.page_usage.items():
                if current_time - last_used > max_idle_time:
                    pages_to_remove.append(page)
            
            for page in pages_to_remove:
                try:
                    await page.close()
                    del self.page_usage[page]
                    
                    # 从池中移除
                    for pool in self.page_pools.values():
                        if page in pool:
                            pool.remove(page)
                            break
                            
                    logger.info(f"Cleaned up idle page")
                    
                except Exception as e:
                    logger.error(f"Error cleaning up page: {e}")
    
    async def get_stats(self) -> Dict:
        """获取统计信息"""
        stats = {
            "browsers": len(self.browsers),
            "total_pages": len(self.page_usage),
            "available_pages": sum(len(pool) for pool in self.page_pools.values()),
            "browser_stats": []
        }
        
        for i, browser in enumerate(self.browsers):
            browser_stat = {
                "browser_id": i,
                "available_pages": len(self.page_pools[browser]),
                "total_pages_created": len([p for p in self.page_usage.keys() 
                                          if p.context.browser == browser])
            }
            stats["browser_stats"].append(browser_stat)
        
        return stats
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 检查所有浏览器是否正常
            for browser in self.browsers:
                if not browser.is_connected():
                    return False
            
            # 检查是否有可用页面
            total_available = sum(len(pool) for pool in self.page_pools.values())
            if total_available == 0 and len(self.page_usage) >= self.max_browsers * self.max_pages_per_browser:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def cleanup(self):
        """清理所有资源"""
        logger.info("Cleaning up browser manager")
        
        # 关闭所有页面
        for page in list(self.page_usage.keys()):
            try:
                await page.close()
            except:
                pass
        
        # 关闭所有浏览器
        for browser in self.browsers:
            try:
                await browser.close()
            except:
                pass
        
        # 停止playwright
        if self.playwright:
            try:
                await self.playwright.stop()
            except:
                pass
        
        logger.info("Browser manager cleanup completed")

    async def fill(self, page: Page, selector: str, value: str, timeout: int = 10000):
        """在指定选择器中填写文本"""
        try:
            await page.fill(selector, value, timeout=timeout)
            logger.info(f"Filled '{value}' into selector '{selector}'")
            return {"success": True, "message": f"Filled '{value}' into '{selector}'"}
        except Exception as e:
            logger.error(f"Failed to fill selector '{selector}': {e}")
            return {"success": False, "error": str(e)}

    async def click(self, page: Page, selector: str, timeout: int = 10000):
        """点击指定选择器"""
        try:
            await page.click(selector, timeout=timeout)
            logger.info(f"Clicked selector '{selector}'")
            return {"success": True, "message": f"Clicked '{selector}'"}
        except Exception as e:
            logger.error(f"Failed to click selector '{selector}': {e}")
            return {"success": False, "error": str(e)}

    async def wait_for_selector(self, page: Page, selector: str, state: str = "visible", timeout: int = 30000):
        """等待指定选择器出现"""
        try:
            await page.wait_for_selector(selector, state=state, timeout=timeout)
            logger.info(f"Waited for selector '{selector}' to be '{state}'")
            return {"success": True, "message": f"Selector '{selector}' is {state}"}
        except Exception as e:
            logger.error(f"Failed to wait for selector '{selector}': {e}")
            return {"success": False, "error": str(e)}

    async def get_current_page_content(self, page: Page, selector: Optional[str] = None) -> str:
        """
        获取当前页面内容，并转换为Markdown格式。
        如果指定了选择器，则只提取该元素内的文本。
        """
        try:
            if selector:
                element = await page.query_selector(selector)
                if element:
                    html_content = await element.inner_html()
                    logger.info(f"Extracted HTML from selector '{selector}'. Length: {len(html_content)}")
                else:
                    logger.warning(f"Selector '{selector}' not found. Returning full page content.")
                    html_content = await page.content()
            else:
                html_content = await page.content()
                logger.info(f"Extracted full page HTML. Length: {len(html_content)}")

            # 使用BeautifulSoup解析HTML并提取主要文本
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 移除不必要的标签，如script, style
            for script_or_style in soup(["script", "style"]):
                script_or_style.extract()
            
            # 尝试提取主要内容区域，例如 <main>, <article>, <div> with specific class
            main_content = soup.find('main') or soup.find('article') or soup.find('body')
            if not main_content:
                main_content = soup # Fallback to full soup if no main content found

            # 将HTML转换为Markdown
            markdown_content = markdownify.markdownify(str(main_content), heading_style="ATX")
            
            # 清理多余的空行和空格
            markdown_content = "\n".join([line.strip() for line in markdown_content.splitlines() if line.strip()])
            markdown_content = markdown_content.replace('\n\n\n', '\n\n') # 减少多余空行

            logger.info(f"Converted page content to Markdown. Markdown length: {len(markdown_content)}")
            return markdown_content
        except Exception as e:
            logger.error(f"Error extracting or converting page content: {e}")
            return f"Error extracting page content: {str(e)}"