import asyncio
import json
import logging
import os
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

    async def load_new_tasks(self):
        """
        加载 tasks.jsonl 文件中的新任务。
        这是一个生成器，每次返回一个新任务。
        """
        while True:
            try:
                if not os.path.exists(self.task_file):
                    logger.debug(f"任务文件 {self.task_file} 不存在，等待...")
                    await asyncio.sleep(5)
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
                
                await asyncio.sleep(1) # 短暂等待，避免CPU空转
                
            except Exception as e:
                logger.error(f"任务加载过程中出错: {e}")
                await asyncio.sleep(5) # 错误时等待更长时间