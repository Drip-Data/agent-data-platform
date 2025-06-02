import asyncio
import json
import logging
import os
import time
from typing import List, Dict, Optional
import redis.asyncio as redis
from playwright.async_api import Page

from core.interfaces import (
    RuntimeInterface, TaskSpec, TrajectoryResult, 
    ExecutionStep, ActionType, ErrorType
)
from core.metrics import EnhancedMetrics
from core.cache import TemplateCache
from core.llm_client import LLMClient
from browser_manager import BrowserManager

logger = logging.getLogger(__name__)
metrics = EnhancedMetrics(port=8002)

class MemoryControlledWebRuntime(RuntimeInterface):
    """内存控制的Web导航运行时"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.redis = redis.from_url(config["redis_url"])
        self.vllm_url = config.get("vllm_url", "http://localhost:8000")
        self._runtime_id = "web-runtime"
        self._capabilities = ["web_search", "web_navigation", "form_filling"]
        
        # 并发控制
        self.max_concurrent = config.get("max_concurrent", 4)
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        
        self.browser_manager = BrowserManager()
        self.cache = TemplateCache(self.redis)
        self.llm_client = LLMClient(config)
        
    @property
    def runtime_id(self) -> str:
        return self._runtime_id
    
    @property
    def capabilities(self) -> List[str]:
        return self._capabilities
    
    async def start(self):
        """启动运行时"""
        # 初始化浏览器管理器
        await self.browser_manager.initialize()
        
        # 创建消费者组
        queue_name = "tasks:web"
        try:
            await self.redis.xgroup_create(queue_name, "workers", id="0", mkstream=True)
        except redis.ResponseError:
            pass
        
        # 启动metrics服务器
        metrics.start_server()
        
        # 注册健康状态
        await self._register_health()
        
        # 开始消费任务
        await self._consume_tasks()
    
    async def execute(self, task: TaskSpec) -> TrajectoryResult:
        """执行Web导航任务"""
        # 并发控制
        async with self.semaphore:
            return await self._execute_with_browser(task)
    
    async def _execute_with_browser(self, task: TaskSpec) -> TrajectoryResult:
        """在浏览器中执行任务"""
        start_time = time.time()
        metrics.record_task_start(task.task_id, 'web_navigator')
        
        page = None
        steps = []
        
        try:            # 检查缓存
            cached_result = await self.cache.get(task.task_type.value, task.description)
            
            if cached_result:
                metrics.record_cache_hit()
                logger.info(f"Using cached web actions for task {task.task_id}")
                
                # 从缓存快速执行
                result = await self._execute_cached_actions(task, cached_result)
                metrics.record_task_completed(task.task_id, 'web_navigator', True)
                return result
            
            # 缓存未命中，执行新导航
            metrics.record_cache_miss()
            
            # 获取浏览器页面
            page = await self.browser_manager.get_page()
            
            # 获取起始URL
            start_url = task.constraints.get("start_url", "https://www.google.com")
            
            # 导航到起始页面
            await page.goto(start_url, wait_until='networkidle', timeout=30000)
            initial_content = await self._extract_page_content(page)
            
            # 第一步：页面导航
            nav_step = ExecutionStep(
                step_id=0,
                action_type=ActionType.BROWSER_ACTION,
                action_params={"action": "goto", "url": start_url},
                observation=initial_content[:1000],  # 限制观察长度
                success=True,
                duration=1.0
            )
            steps.append(nav_step)
            
            # 执行后续动作
            current_step = 1
            actions_cache = []
            
            while current_step < task.max_steps:
                step_start = time.time()
                
                # 生成下一步动作
                action = await self._generate_next_action(
                    task.description, 
                    await self._extract_page_content(page),
                    page.url
                )
                
                if action.get("type") == "finish":
                    break
                
                # 执行动作
                success, observation, error_type = await self._execute_browser_action(page, action)
                
                step = ExecutionStep(
                    step_id=current_step,
                    action_type=ActionType.BROWSER_ACTION,
                    action_params=action,
                    observation=observation[:1000],  # 限制观察长度
                    success=success,
                    error_type=error_type,
                    duration=time.time() - step_start
                )
                steps.append(step)
                
                # 记录动作用于缓存
                actions_cache.append({
                    "action": action,
                    "success": success
                })
                
                if not success:
                    break
                
                current_step += 1
                
                # 内存压力检查
                if current_step > 5:  # 限制最大步数以控制内存
                    break
            
            # 获取最终结果
            final_content = await self._extract_page_content(page)
            
            # 缓存成功的动作序列
            if len(actions_cache) > 0:
                cache_data = {
                    "actions": actions_cache,
                    "final_result": final_content[:500]
                }
                await self.cache.set(task.task_type.value, task.description, cache_data)
            
            result = TrajectoryResult(
                task_id=task.task_id,
                runtime_id=self.runtime_id,
                success=any(s.success for s in steps),
                steps=steps,
                final_result=final_content[:1000],
                total_duration=time.time() - start_time,
                metadata={
                    "final_url": page.url,
                    "total_steps": len(steps),
                    "cache_hit": False
                }
            )
            
            metrics.record_task_completed(task.task_id, 'web_navigator', True)
            return result
            
        except Exception as e:
            logger.error(f"Error executing web task {task.task_id}: {e}")
            error_type = ErrorType.BROWSER_ERROR
            metrics.record_task_failure(task.task_id, 'web_navigator', error_type.value)
            
            return TrajectoryResult(
                task_id=task.task_id,
                runtime_id=self.runtime_id,
                success=False,
                steps=steps,
                final_result="",
                error_type=error_type,
                error_message=str(e),
                total_duration=time.time() - start_time,
                metadata={}
            )
        finally:
            if page:
                await self.browser_manager.return_page(page)
    
    async def _execute_cached_actions(self, task: TaskSpec, cached_data: Dict) -> TrajectoryResult:
        """执行缓存的动作序列"""
        start_time = time.time()
        
        # 构造缓存结果
        steps = []
        for i, action_data in enumerate(cached_data.get("actions", [])):
            step = ExecutionStep(
                step_id=i,
                action_type=ActionType.BROWSER_ACTION,
                action_params=action_data["action"],
                observation="[Cached result]",
                success=action_data["success"],
                duration=0.1
            )
            steps.append(step)
        
        return TrajectoryResult(
            task_id=task.task_id,
            runtime_id=self.runtime_id,
            success=True,
            steps=steps,
            final_result=cached_data.get("final_result", ""),
            total_duration=time.time() - start_time,
            metadata={"cache_hit": True}
        )
    
    async def _extract_page_content(self, page: Page) -> str:
        """提取页面内容（优化版）"""
        try:
            # 获取页面标题和主要文本
            title = await page.title()
            text_content = await page.evaluate('''
                () => {
                    // 移除脚本和样式
                    const scripts = document.querySelectorAll('script, style, nav, footer');
                    scripts.forEach(el => el.remove());
                    
                    // 获取主要内容区域
                    const main = document.querySelector('main, #content, .content, [role="main"]');
                    const content = main ? main.innerText : document.body.innerText;
                    
                    return content.slice(0, 1500);  // 限制长度
                }
            ''')
            
            return f"# {title}\n\n{text_content}"
            
        except Exception as e:
            logger.error(f"Error extracting page content: {e}")
            return f"Error extracting content: {str(e)}"
    
    async def _generate_next_action(self, task_description: str, page_content: str, current_url: str) -> Dict:
        """生成下一步动作（简化版）"""
        # 基于规则的简单动作生成
        if "search" in task_description.lower():
            if "google.com" in current_url:
                return {
                    "type": "fill_and_submit",
                    "selector": "input[name='q'], input[type='search']",
                    "text": self._extract_search_terms(task_description)
                }
            else:
                return {"type": "finish"}
        elif "click" in task_description.lower():
            return {
                "type": "click",
                "selector": "a:first-of-type, button:first-of-type"
            }
        else:
            return {"type": "finish"}
    
    def _extract_search_terms(self, description: str) -> str:
        """从描述中提取搜索词"""
        # 简单的关键词提取
        words = description.split()
        keywords = [w for w in words if len(w) > 2 and w.lower() not in 
                   ['search', 'find', 'look', 'for', 'about', 'information']]
        return ' '.join(keywords[:3])
    
    async def _execute_browser_action(self, page: Page, action: Dict) -> tuple:
        """执行浏览器动作"""
        try:
            action_type = action.get("type")
            
            if action_type == "fill_and_submit":
                selector = action.get("selector")
                text = action.get("text")
                
                # 填写表单
                await page.fill(selector, text)
                await page.press(selector, "Enter")
                
                # 等待页面加载
                await page.wait_for_load_state('networkidle', timeout=10000)
                
                observation = await self._extract_page_content(page)
                return True, observation, None
                
            elif action_type == "click":
                selector = action.get("selector")
                
                # 点击元素
                await page.click(selector)
                
                # 等待页面变化
                await page.wait_for_load_state('networkidle', timeout=10000)
                
                observation = await self._extract_page_content(page)
                return True, observation, None
                
            elif action_type == "scroll":
                # 滚动页面
                await page.evaluate("window.scrollBy(0, 500)")
                observation = "Scrolled down"
                return True, observation, None
                
            else:
                return False, f"Unknown action type: {action_type}", ErrorType.INVALID_ACTION
                
        except Exception as e:
            logger.error(f"Error executing browser action: {e}")
            return False, str(e), ErrorType.BROWSER_ERROR
    
    async def _consume_tasks(self):
        """消费任务队列"""
        consumer_id = f"web-{os.getpid()}"
        queue_name = "tasks:web"
        
        logger.info(f"Starting task consumer {consumer_id}")
        
        while True:
            try:
                # 读取任务
                messages = await self.redis.xreadgroup(
                    "workers", consumer_id,
                    {queue_name: ">"},
                    count=1, block=1000
                )
                
                if not messages:
                    continue
                
                for stream, msgs in messages:
                    for msg_id, fields in msgs:
                        try:
                            # 解析任务
                            task_data = json.loads(fields[b'task'].decode())
                            task = TaskSpec.from_dict(task_data)
                            
                            # 执行任务
                            result = await self.execute(task)
                            
                            # 保存轨迹
                            await self._save_trajectory(result)
                            
                            # 确认消息
                            await self.redis.xack(queue_name, "workers", msg_id)
                            
                        except Exception as e:
                            logger.error(f"Error processing message {msg_id}: {e}")
                            await self.redis.xack(queue_name, "workers", msg_id)
                            
            except Exception as e:
                logger.error(f"Error in consumer loop: {e}")
                await asyncio.sleep(5)
    
    async def _save_trajectory(self, result: TrajectoryResult):
        """保存轨迹到文件"""
        output_dir = "/app/output/trajectories"
        os.makedirs(output_dir, exist_ok=True)
        
        file_path = os.path.join(output_dir, f"{result.task_id}.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(result.json())
        
        logger.info(f"Trajectory saved: {file_path}")
    
    async def _register_health(self):
        """注册健康状态"""
        await self.redis.hset("runtime_health", self.runtime_id, "healthy")
        
        # 定期更新健康状态
        asyncio.create_task(self._health_updater())
    
    async def _health_updater(self):
        """定期更新健康状态"""
        while True:
            try:
                healthy = await self.health_check()
                status = "healthy" if healthy else "unhealthy"
                await self.redis.hset("runtime_health", self.runtime_id, status)
                metrics.update_runtime_health(self.runtime_id, healthy)
                
                await asyncio.sleep(30)  # 每30秒更新
            except Exception as e:
                logger.error(f"Health update error: {e}")
                await asyncio.sleep(10)
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 检查Redis连接
            await self.redis.ping()
            
            # 检查浏览器管理器
            return await self.browser_manager.health_check()
            
        except Exception:
            return False
    
    async def cleanup(self):
        """清理资源"""
        await self.browser_manager.cleanup()
        await self.redis.close()

async def main():
    """运行时入口"""
    config = {
        "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
        "vllm_url": os.getenv("VLLM_URL", "http://localhost:8000"),
        "max_concurrent": int(os.getenv("MAX_CONCURRENT", "4"))
    }
    
    runtime = MemoryControlledWebRuntime(config)
    
    try:
        await runtime.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await runtime.cleanup()

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    asyncio.run(main())