import asyncio
import json
import logging
import os
import time
from typing import Set
from core.interfaces import TaskSpec

logger = logging.getLogger(__name__)

class TaskLoader:
    """
    任务加载器，负责从 tasks.jsonl 文件中读取新任务。
    """
    def __init__(self, task_file: str = "tasks.jsonl"):
        self.task_file = task_file
        self.processed_tasks: Set[str] = set()
        self.last_position = 0
        
        # 🔧 添加智能等待机制
        self.consecutive_misses = 0
        self.max_consecutive_misses = 12  # 1分钟后切换到慢轮询
        self.fast_polling_interval = 5   # 快速轮询：5秒
        self.slow_polling_interval = 30  # 慢速轮询：30秒
        self.last_activity_time = time.time()

    async def load_new_tasks(self):
        """
        加载 tasks.jsonl 文件中的新任务。
        这是一个生成器，每次返回一个新任务。
        """
        while True:
            try:
                if not os.path.exists(self.task_file):
                    # 🔧 智能等待机制
                    self.consecutive_misses += 1
                    
                    # 选择等待间隔
                    if self.consecutive_misses <= self.max_consecutive_misses:
                        wait_time = self.fast_polling_interval
                        level = "debug"
                    else:
                        wait_time = self.slow_polling_interval
                        level = "info" if self.consecutive_misses % 6 == 0 else "debug"  # 每3分钟输出一次info
                    
                    # 输出日志
                    log_msg = f"任务文件 {self.task_file} 不存在，等待... (第{self.consecutive_misses}次, {wait_time}s间隔)"
                    if level == "info":
                        logger.info(f"📋 {log_msg} - 建议通过API提交任务")
                    else:
                        logger.debug(log_msg)
                    
                    await asyncio.sleep(wait_time)
                    continue

                with open(self.task_file, 'r', encoding='utf-8') as f:
                    # 移动到上次读取的位置
                    f.seek(self.last_position)
                    
                    line_number = 0
                    while True:
                        line = f.readline()
                        
                        # 如果到达文件末尾，退出循环
                        if not line:
                            break
                            
                        line_number += 1
                        line = line.strip()
                        if not line:
                            # 更新位置并继续
                            self.last_position = f.tell()
                            continue

                        try:
                            task_data = json.loads(line)
                            task = TaskSpec.from_dict(task_data)
                            
                            if task.task_id in self.processed_tasks:
                                self.last_position = f.tell()
                                continue
                            
                            self.processed_tasks.add(task.task_id)
                            self.last_position = f.tell() # 记录当前文件位置
                            
                            # 🔧 重置连续失败计数器
                            if self.consecutive_misses > 0:
                                logger.debug(f"✅ 找到任务，重置等待计数器 (之前{self.consecutive_misses}次未找到)")
                                self.consecutive_misses = 0
                                self.last_activity_time = time.time()
                            
                            yield task # 返回新任务
                            
                        except (json.JSONDecodeError, ValueError) as e:
                            logger.error(f"第 {line_number} 行任务解析失败: {e} - 内容: {line}")
                            self.last_position = f.tell() # 即使解析失败也更新位置，避免重复处理错误行
                
                # 更新文件大小，如果文件被截断，重置 processed_tasks 和 last_position
                current_file_size = os.path.getsize(self.task_file)
                if current_file_size < self.last_position:
                    logger.warning(f"任务文件 {self.task_file} 被截断，重置加载状态。")
                    self.processed_tasks.clear()
                    self.last_position = 0
                
                # 🔧 文件存在但无新任务时的智能等待
                self.consecutive_misses += 1
                if self.consecutive_misses <= self.max_consecutive_misses:
                    await asyncio.sleep(self.fast_polling_interval)
                else:
                    await asyncio.sleep(self.slow_polling_interval)
                
            except Exception as e:
                logger.error(f"任务加载过程中出错: {e}")
                await asyncio.sleep(5) # 错误时等待更长时间