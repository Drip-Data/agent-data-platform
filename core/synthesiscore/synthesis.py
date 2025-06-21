#!/usr/bin/env python3
"""
任务合成器模块 - 基于轨迹学习的种子任务生成系统

专注于通过分析agent执行轨迹，提取任务本质，并生成高质量的种子任务。
完全移除数据库依赖，使用JSON文件进行数据存储。

主要功能：
1. 轨迹分析：深度理解agent行为模式
2. 本质提取：识别任务的核心特征和成功要素  
3. 种子生成：基于本质创造新的训练任务
4. 自动监控：实时跟踪轨迹文件变化
"""

import os
import sys
import json
import asyncio
import logging
import threading
import time
import uuid
import hashlib
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from collections import defaultdict
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import aiofiles
import redis  # For synchronous operations in threading contexts
import redis.asyncio as async_redis

from ..interfaces import TaskSpec, TrajectoryResult, TaskType, ExecutionStep, ActionType, ErrorType, LLMInteraction
from ..llm_client import LLMClient
from ..toolscore.unified_tool_library import UnifiedToolLibrary
from ..toolscore.interfaces import ToolType, FunctionToolSpec, ToolCapability
from ..utils.path_utils import get_output_dir, get_trajectories_dir

logger = logging.getLogger(__name__)

@dataclass
class TaskEssence:
    """任务本质数据结构"""
    essence_id: str
    task_type: str
    domain: str
    query: str
    complexity_level: str
    success_pattern: Dict
    extracted_at: str
    source_trajectory_id: str

class TrajectoryHandler(FileSystemEventHandler):
    """轨迹文件变化处理器"""
    
    def __init__(self, synthesis_instance, target_file_path):
        self.synthesis = synthesis_instance
        self.target_file_path = target_file_path
        
    def on_created(self, event):
        if not event.is_directory and event.src_path == self.target_file_path:
            logger.info(f"🔔 检测到轨迹集合文件创建: {event.src_path}")
            # 使用线程安全的方式触发处理
            self._trigger_processing()
    
    def on_modified(self, event):
        if not event.is_directory and event.src_path == self.target_file_path:
            logger.info(f"🔔 检测到轨迹集合文件修改: {event.src_path}")
            # 使用线程安全的方式触发处理
            self._trigger_processing()
    
    def _trigger_processing(self):
        """线程安全地触发轨迹处理"""
        try:
            # 使用Redis发送处理命令，而不是直接调用异步函数
            redis_client = redis.from_url(self.synthesis.config["redis_url"])
            redis_client.xadd(
                "synthesis:commands",
                {
                    "command": "process_trajectories",
                    "timestamp": time.time(),
                    "source": "file_watcher"
                }
            )
            logger.info("📨 已发送轨迹处理命令到Redis队列")
        except Exception as e:
            logger.error(f"❌ 发送处理命令失败: {e}")

class SynthesisService:
    """简单任务合成器 - 基于JSON文件存储"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.redis = async_redis.from_url(config["redis_url"])  # 使用异步redis客户端
        self.llm_client = LLMClient(config)
        self.enabled = config.get("synthesis_enabled", False)
        self.tool_library = UnifiedToolLibrary() # 初始化UnifiedToolLibrary
          # 使用统一的路径管理
        self.task_essences_path = str(get_output_dir() / "task_essences.json")
        self.seed_tasks_path = str(get_output_dir() / "seed_tasks.jsonl")
        self.processed_trajectories_path = str(get_output_dir() / "processed_trajectories.json")
        self.auto_monitor_enabled = config.get("auto_monitor_trajectories", True)
        self.auto_export_seeds = config.get("auto_export_seeds", True)
        
        # 指定监控的轨迹集合文件
        self.trajectories_collection_path = str(get_output_dir("trajectories") / "trajectories_collection.json")
        self.observer = None
        
        # 文件锁
        self._file_lock = threading.Lock()
        
        # 已处理轨迹的记录（从文件加载）
        self.processed_trajectories = set()
        
        # 初始化JSON文件
        self._init_json_files()
        
        # 加载已处理的轨迹列表
        self._load_processed_trajectories()
    
    def _init_json_files(self):
        """初始化JSON存储文件"""
        try:
            # 创建输出目录
            os.makedirs(os.path.dirname(self.task_essences_path), exist_ok=True)
            os.makedirs(os.path.dirname(self.seed_tasks_path), exist_ok=True)
            
            # 初始化任务本质文件
            if not os.path.exists(self.task_essences_path):
                self._save_json_file(self.task_essences_path, [])
                logger.info(f"✅ 初始化任务本质文件: {self.task_essences_path}")
            
            # 初始化种子任务文件目录
            if not os.path.exists(self.seed_tasks_path):
                Path(self.seed_tasks_path).touch()
                logger.info(f"✅ 初始化种子任务文件: {self.seed_tasks_path}")
            
            # 初始化已处理轨迹记录文件
            if not os.path.exists(self.processed_trajectories_path):
                self._save_json_file(self.processed_trajectories_path, [])
                logger.info(f"✅ 初始化已处理轨迹记录文件: {self.processed_trajectories_path}")
                
            logger.info("✅ JSON文件存储初始化完成")
        except Exception as e:
            logger.error(f"❌ JSON文件存储初始化失败: {e}")
            raise

    def _load_processed_trajectories(self):
        """从文件加载已处理的轨迹列表"""
        try:
            processed_list = self._load_json_file(self.processed_trajectories_path, [])
            self.processed_trajectories = set(processed_list)
            
            if self.processed_trajectories:
                logger.info(f"📋 从文件加载了 {len(self.processed_trajectories)} 个已处理轨迹记录")
                logger.debug(f"已处理轨迹列表: {list(self.processed_trajectories)[:5]}{'...' if len(self.processed_trajectories) > 5 else ''}")
            else:
                logger.info("📋 未发现已处理轨迹记录，从空白状态开始")
                
        except Exception as e:
            logger.error(f"❌ 加载已处理轨迹记录失败: {e}")
            self.processed_trajectories = set()

    def _save_processed_trajectories(self):
        """将已处理轨迹列表保存到文件"""
        try:
            processed_list = list(self.processed_trajectories)
            success = self._save_json_file(self.processed_trajectories_path, processed_list)
            if success:
                logger.debug(f"💾 已保存 {len(processed_list)} 个已处理轨迹记录到文件")
            else:
                logger.error("❌ 保存已处理轨迹记录失败")
        except Exception as e:
            logger.error(f"❌ 保存已处理轨迹记录时出错: {e}")

    def _load_json_file(self, filepath: str, default_value=None):
        """线程安全地加载JSON文件"""
        with self._file_lock:
            try:
                if os.path.exists(filepath):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        return json.load(f)
                else:
                    return default_value if default_value is not None else []
            except Exception as e:
                logger.error(f"加载JSON文件失败 {filepath}: {e}")
                return default_value if default_value is not None else []
    
    def _save_json_file(self, filepath: str, data):
        """线程安全地保存JSON文件"""
        with self._file_lock:
            try:
                # 创建临时文件，确保原子写入
                temp_filepath = filepath + '.tmp'
                with open(temp_filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                # 原子替换
                os.replace(temp_filepath, filepath)
                return True
            except Exception as e:
                logger.error(f"保存JSON文件失败 {filepath}: {e}")
                return False

    async def start(self):
        """启动合成器，支持自动轨迹监控和种子数据导出"""
        if not self.enabled:
            logger.info("Task synthesis is disabled")
            return
            
        logger.info("🚀 启动基于JSON的任务合成器...")
        
        await self.tool_library.initialize() # 初始化UnifiedToolLibrary
        
        # 启动自动轨迹监控（如果启用）
        if self.auto_monitor_enabled:
            await self._start_trajectory_monitoring()
        
        # 启动指令监听器
        await self._listen_for_synthesis_commands()

    async def _start_trajectory_monitoring(self):
        """启动轨迹文件自动监控 - 专门监控trajectories_collection.json"""
        try:
            logger.info("🔍 启动轨迹集合文件监控...")
            
            # 检查目标文件是否存在
            target_dir = os.path.dirname(self.trajectories_collection_path)
            if not os.path.exists(target_dir):
                logger.warning(f"⚠️ 轨迹目录不存在，创建目录: {target_dir}")
                os.makedirs(target_dir, exist_ok=True)
            
            logger.info(f"📁 监控文件: {self.trajectories_collection_path}")
            
            # 创建文件监控器
            self.observer = Observer()
            handler = TrajectoryHandler(self, self.trajectories_collection_path)
            
            # 监控轨迹集合文件所在目录
            self.observer.schedule(handler, target_dir, recursive=False)
            self.observer.start()
            
            logger.info(f"✅ 自动轨迹监控已启动，监控文件: {self.trajectories_collection_path}")
            
            # 处理现有的轨迹集合文件（如果存在）
            if os.path.exists(self.trajectories_collection_path):
                await self._process_trajectories_collection()
            else:
                logger.info(f"📝 轨迹集合文件尚不存在: {self.trajectories_collection_path}")
                
        except Exception as e:
            logger.error(f"❌ 启动轨迹监控失败: {e}")
    
    async def _process_trajectories_collection(self):
        """处理trajectories_collection.json文件中的轨迹"""
        try:
            if not os.path.exists(self.trajectories_collection_path):
                logger.warning(f"⚠️ 轨迹集合文件不存在: {self.trajectories_collection_path}")
                return
            
            logger.info(f"🔄 开始处理轨迹集合文件: {self.trajectories_collection_path}")

            if not os.path.exists(self.trajectories_collection_path) or os.path.getsize(self.trajectories_collection_path) == 0:
                logger.info(f"📝 Trajectory collection file is empty or does not exist: {self.trajectories_collection_path}")
                return

            # 读取轨迹集合数据
            try:
                with open(self.trajectories_collection_path, 'r', encoding='utf-8') as f:
                    trajectories_data = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"❌ Error decoding JSON from {self.trajectories_collection_path}: {e}")
                return
            
            if not isinstance(trajectories_data, list):
                logger.error("❌ 轨迹集合文件格式错误，应为轨迹数组")
                return
            
            new_essences = []
            new_seed_tasks = []
            processed_count = 0
            skipped_count = 0
            
            logger.info(f"📊 轨迹集合包含 {len(trajectories_data)} 个轨迹")
            
            for i, trajectory_data in enumerate(trajectories_data):
                try:
                    # 生成轨迹唯一标识符
                    trajectory_id = trajectory_data.get('task_id', f'trajectory_{i}')
                    
                    # 避免重复处理
                    if self._is_trajectory_processed(trajectory_id):
                        skipped_count += 1
                        logger.debug(f"⏩ 跳过已处理的轨迹: {trajectory_id}")
                        continue
                    
                    # 转换轨迹格式
                    trajectory = self._convert_trajectory_format(trajectory_data)
                    if trajectory and self._should_process_trajectory(trajectory):
                        # 提取任务本质
                        essence = await self._extract_essence(trajectory)
                        if essence:
                            # 保存本质到JSON文件
                            new_essences.append(asdict(essence))
                            
                            # 直接转换为种子任务
                            seed_task = await self._convert_essence_to_seed(essence)
                            if seed_task:
                                new_seed_tasks.append(seed_task)
                                processed_count += 1
                                logger.info(f"✅ 生成任务本质和种子任务: {trajectory_id}")
                                
                                # 标记为已处理
                                self._mark_trajectory_processed(trajectory_id)
                        
                except Exception as e:
                    logger.error(f"❌ 处理第{i+1}个轨迹时出错: {e}")
                    continue
            
            # 保存新的任务本质
            if new_essences:
                await self._save_new_essences(new_essences)
                logger.info(f"💾 保存 {len(new_essences)} 个任务本质")
            
            # 直接追加到种子文件
            if new_seed_tasks:
                await self._append_seed_tasks(new_seed_tasks)
                logger.info(f"📤 成功添加 {len(new_seed_tasks)} 个种子任务")
            
            logger.info(f"✅ 轨迹集合处理完成: 新处理 {processed_count} 个，跳过 {skipped_count} 个")
                
        except Exception as e:
            logger.error(f"❌ 处理轨迹集合文件失败: {e}")
    
    async def _save_new_essences(self, new_essences: List[Dict]):
        """保存新的任务本质到JSON文件"""
        try:
            # 读取现有本质
            existing_essences = self._load_json_file(self.task_essences_path, [])
            
            # 添加新本质
            existing_essences.extend(new_essences)
            
            # 保存回文件
            self._save_json_file(self.task_essences_path, existing_essences)
            
            logger.info(f"💾 已保存 {len(new_essences)} 个新任务本质到 {self.task_essences_path}")
            
            # 统计信息
            type_stats = defaultdict(int)
            domain_stats = defaultdict(int)
            for essence in new_essences:
                type_stats[essence['task_type']] += 1
                domain_stats[essence['domain']] += 1
            
            logger.info(f"📊 新增本质分布 - 类型: {dict(type_stats)}, 领域: {dict(domain_stats)}")
            
        except Exception as e:
            logger.error(f"❌ 保存任务本质失败: {e}")

    async def _process_existing_trajectories(self):
        """处理现有的轨迹集合文件"""
        logger.info("🔄 检查现有轨迹集合文件...")
        
        if os.path.exists(self.trajectories_collection_path):
            await self._process_trajectories_collection()
        else:
            logger.info("📝 没有现有的轨迹集合文件")

    async def _process_new_trajectory_file(self, trajectory_path: str):
        """处理轨迹集合文件（保持兼容性）"""
        if trajectory_path == self.trajectories_collection_path:
            await self._process_trajectories_collection()
        else:
            logger.debug(f"⏩ 忽略非目标文件: {trajectory_path}")
    
    async def _convert_essence_to_seed(self, essence: TaskEssence) -> Optional[Dict]:
        """将任务本质直接转换为种子任务"""
        try:
            # 生成种子任务ID
            task_id = f"seed_{essence.task_type}_{self._generate_task_id_suffix(essence.query)}"
            
            # 推断预期工具
            success_pattern = essence.success_pattern
            expected_tools = success_pattern.get('tools_used', [])
            if not expected_tools:
                expected_tools = await self._infer_expected_tools(essence.task_type, essence.domain)
            
            # 推断最大步数
            max_steps = self._infer_max_steps(essence.complexity_level, essence.task_type)
            
            seed_task = {
                "task_id": task_id,
                "task_type": essence.task_type,
                "description": essence.query,
                "expected_tools": expected_tools,
                "max_steps": max_steps,
                "domain": essence.domain,
                "complexity": essence.complexity_level,
                "confidence": success_pattern.get('confidence', 0.8),
                "source_essence_id": essence.essence_id,
                "source_trajectory": essence.source_trajectory_id,
                "extracted_at": essence.extracted_at
            }
            
            return seed_task
            
        except Exception as e:
            logger.error(f"转换任务本质为种子任务时出错: {e}")
            return None
    
    async def _append_seed_tasks(self, seed_tasks: List[Dict]):
        """追加种子任务到文件"""
        with self._file_lock:
            try:
                async with aiofiles.open(self.seed_tasks_path, 'a', encoding='utf-8') as f:
                    for seed_task in seed_tasks:
                        await f.write(json.dumps(seed_task, ensure_ascii=False) + '\n')
                
                logger.info(f"✅ 成功追加 {len(seed_tasks)} 个种子任务到 {self.seed_tasks_path}")
                
                # 统计信息
                type_stats = defaultdict(int)
                for task in seed_tasks:
                    type_stats[task['task_type']] += 1
                
                logger.info(f"📊 新增种子任务分布: {dict(type_stats)}")
                
            except Exception as e:
                logger.error(f"❌ 追加种子任务失败: {e}")

    async def _export_seed_tasks(self):
        """导出种子任务统计和状态报告"""
        try:
            if not os.path.exists(self.seed_tasks_path):
                logger.info("📝 种子任务文件尚不存在")
                return
            
            # 读取并统计种子任务
            seed_count = 0
            type_stats = defaultdict(int)
            domain_stats = defaultdict(int)
            
            with open(self.seed_tasks_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        try:
                            task = json.loads(line.strip())
                            seed_count += 1
                            type_stats[task.get('task_type', 'unknown')] += 1
                            domain_stats[task.get('domain', 'unknown')] += 1
                        except json.JSONDecodeError:
                            continue
            
            logger.info("📊 种子任务导出统计:")
            logger.info(f"  总数量: {seed_count}")
            logger.info(f"  任务类型分布: {dict(type_stats)}")
            logger.info(f"  领域分布: {dict(domain_stats)}")
            logger.info(f"  文件路径: {self.seed_tasks_path}")
            
            # 发布统计信息到Redis
            export_stats = {
                "total_seeds": seed_count,
                "type_distribution": dict(type_stats),
                "domain_distribution": dict(domain_stats),
                "file_path": self.seed_tasks_path,
                "exported_at": datetime.now().isoformat()
            }
            
            await self.redis.xadd(
                "synthesis:seed_export",
                {
                    "timestamp": time.time(),
                    "stats": json.dumps(export_stats)
                }
            )
            
        except Exception as e:
            logger.error(f"❌ 导出种子任务统计失败: {e}")

    def _generate_task_id_suffix(self, description: str) -> str:
        """根据描述生成任务ID后缀"""
        # 使用描述的哈希值生成短后缀
        hash_obj = hashlib.md5(description.encode('utf-8'))
        return hash_obj.hexdigest()[:8]
    
    async def _infer_expected_tools(self, task_type: str, domain: str) -> List[str]:
        """根据任务类型和领域推断预期工具 - 动态从UnifiedToolLibrary获取"""
        
        all_tools = await self.tool_library.get_all_tools()
        available_tool_ids = {tool.tool_id for tool in all_tools}
        
        inferred_tools = set()

        # 优先匹配明确的工具ID
        if task_type == 'code':
            if "python_executor" in available_tool_ids:
                inferred_tools.add("python_executor")
        elif task_type == 'web':
            if "browser_navigator" in available_tool_ids:
                inferred_tools.add("browser_navigator")
            # 假设有其他web工具，例如"web_scraper"
            # if "web_scraper" in available_tool_ids:
            #     inferred_tools.add("web_scraper")
        elif task_type == 'reasoning':
            if "browser_navigator" in available_tool_ids:
                inferred_tools.add("browser_navigator")
            if "python_executor" in available_tool_ids:
                inferred_tools.add("python_executor")

        # 根据领域进一步细化，匹配工具的tags或description
        # 这是一个示例，实际可能需要更复杂的匹配逻辑
        domain_keywords_map = {
            'data_analysis': ['data', 'analysis', 'pandas', 'numpy', 'matplotlib'],
            'web_automation': ['web', 'browser', 'scrape', 'requests', 'BeautifulSoup'],
            'algorithm': ['algorithm', 'math', 'calculate'],
            'research': ['search', 'research', 'query'],
            'stock_analysis': ['stock', 'finance', 'market']
        }

        domain_keywords = domain_keywords_map.get(domain, [])
        
        for tool in all_tools:
            tool_description_lower = tool.description.lower()
            tool_name_lower = tool.name.lower()
            tool_tags_lower = [tag.lower() for tag in tool.tags] if tool.tags else []

            # 检查工具描述、名称或标签是否包含领域关键词
            if any(keyword in tool_description_lower or
                   keyword in tool_name_lower or
                   any(keyword in tag for tag in tool_tags_lower)
                   for keyword in domain_keywords):
                inferred_tools.add(tool.tool_id)
        
        # 如果没有推断出任何工具，则根据任务类型提供一个默认工具
        if not inferred_tools:
            if task_type == 'code' and "python_executor" in available_tool_ids:
                inferred_tools.add("python_executor")
            elif task_type == 'web' and "browser_navigator" in available_tool_ids:
                inferred_tools.add("browser_navigator")
            elif task_type == 'reasoning' and "browser_navigator" in available_tool_ids:
                inferred_tools.add("browser_navigator")
            elif task_type == 'reasoning' and "python_executor" in available_tool_ids:
                inferred_tools.add("python_executor")

        return list(inferred_tools)
    
    def _infer_max_steps(self, complexity_level: str, task_type: str) -> int:
        """根据复杂度和任务类型推断最大步数"""
        base_steps = {
            'simple': 5,
            'medium': 10,
            'complex': 15
        }
        
        steps = base_steps.get(complexity_level, 8)
        
        # reasoning任务通常需要更多步骤
        if task_type == 'reasoning':
            steps += 5
        
        return min(steps, 20)  # 最大不超过20步

    async def _listen_for_synthesis_commands(self):
        """监听合成指令"""
        logger.info("🎯 Synthesis service ready - waiting for manual triggers")
        logger.info("Available trigger methods:")
        logger.info("1. Redis command: XADD synthesis:commands command trigger_synthesis")
        logger.info("2. Redis command: XADD synthesis:commands command process_trajectories")
        logger.info("3. Redis command: XADD synthesis:commands command process_specific trajectory_file.json")
        
        # 首先处理队列中现有的命令
        await self._process_pending_commands()
        
        while True:
            try:
                # 监听synthesis:commands队列，使用$表示从当前最新位置开始读取新消息
                # 使用 type: ignore 抑制 Pylance 对 redis.asyncio.Redis.xread 类型提示的误报。
                streams = {b"synthesis:commands": b"$"}
                result = await self.redis.xread(streams, count=1, block=5000)  # type: ignore # 5秒超时
                
                if result:
                    for stream_name, messages in result:
                        for message_id, fields in messages:
                            await self._handle_synthesis_command(fields)
                            # 确认处理完成
                            await self.redis.xdel("synthesis:commands", message_id)
                
            except Exception as e:
                logger.error(f"Error listening for synthesis commands: {e}")
                await asyncio.sleep(10)

    async def _process_pending_commands(self):
        """处理队列中现有的待处理命令"""
        try:
            # 读取队列中所有现有命令
            # 使用 type: ignore 抑制 Pylance 对 redis.asyncio.Redis.xread 类型提示的误报。
            result = await self.redis.xread({b"synthesis:commands": b"0"}, count=100)  # type: ignore
            
            if result:
                for stream_name, messages in result:
                    logger.info(f"Found {len(messages)} pending commands in queue")
                    for message_id, fields in messages:
                        logger.info(f"Processing pending command: {message_id}")
                        await self._handle_synthesis_command(fields)
                        # 删除已处理的命令
                        await self.redis.xdel("synthesis:commands", message_id)
                        
                logger.info("✅ All pending commands processed")
            else:
                logger.info("No pending commands found")
                
        except Exception as e:
            logger.error(f"Error processing pending commands: {e}")

    async def _handle_synthesis_command(self, command_fields: dict):
        """处理合成指令"""
        try:
            command = command_fields.get(b'command', b'').decode('utf-8')
            logger.info(f"📨 Received synthesis command: {command}")
            
            if command == "trigger_synthesis":
                # 触发完整的轨迹处理
                await self._process_all_trajectories_once()
                # 自动导出种子数据
                if self.auto_export_seeds:
                    await self._export_seed_tasks()
                
            elif command == "process_trajectories":
                # 处理所有未处理的轨迹
                await self._process_unprocessed_trajectories()
                # 自动导出种子数据
                if self.auto_export_seeds:
                    await self._export_seed_tasks()
                
            elif command.startswith("process_specific"):
                # 处理指定的轨迹文件
                parts = command.split(" ", 1)
                if len(parts) > 1:
                    filename = parts[1]
                    await self._process_specific_trajectory(filename)
                    # 自动导出种子数据
                    if self.auto_export_seeds:
                        await self._export_seed_tasks()
                    
            elif command == "export_seeds":
                # 手动导出种子任务
                await self._export_seed_tasks()
                
            elif command == "start_monitoring":
                # 启动轨迹监控
                if not self.observer or not self.observer.is_alive():
                    await self._start_trajectory_monitoring()
                    logger.info("✅ 轨迹监控已启动")
                else:
                    logger.info("⚠️ 轨迹监控已在运行")
                    
            elif command == "stop_monitoring":
                # 停止轨迹监控
                if self.observer and self.observer.is_alive():
                    self.observer.stop()
                    self.observer.join()
                    logger.info("🛑 轨迹监控已停止")
                else:
                    logger.info("⚠️ 轨迹监控未运行")
                    
            elif command == "generate_tasks":
                # 手动生成任务
                count = int(command_fields.get(b'count', b'3').decode('utf-8'))
                tasks = await self.generate_tasks_manually(count)
                logger.info(f"Generated {len(tasks)} tasks manually")
                
            elif command == "generate_seeds_from_essences":
                # 从现有任务本质生成种子任务
                await self._generate_seeds_from_existing_essences()
                
            elif command == "status":
                # 报告状态
                await self._report_synthesis_status()
                
            else:
                logger.warning(f"Unknown synthesis command: {command}")
                
        except Exception as e:
            logger.error(f"Error handling synthesis command: {e}")
    
    async def _process_all_trajectories_once(self):
        """一次性处理所有轨迹（不循环）"""
        logger.info("🔄 Starting one-time trajectory processing...")
        
        try:
            trajectories_dir = get_trajectories_dir()
            if not os.path.exists(trajectories_dir):
                logger.warning("Trajectories directory not found")
                return
            
            processed_count = 0
            skipped_count = 0
            
            # 处理所有轨迹文件
            for filename in os.listdir(trajectories_dir):
                if filename.endswith('.json'):
                    trajectory_path = os.path.join(trajectories_dir, filename)
                    
                    # 检查是否已处理
                    if not self._is_trajectory_processed(filename):
                        await self._process_trajectory_file(trajectory_path)
                        self._mark_trajectory_processed(filename)
                        processed_count += 1
                        logger.info(f"✅ Processed: {filename}")
                    else:
                        skipped_count += 1
                        logger.debug(f"⏩ Skipped (already processed): {filename}")
            
            logger.info(f"🎯 Trajectory processing completed: {processed_count} processed, {skipped_count} skipped")
            
        except Exception as e:
            logger.error(f"Error in one-time trajectory processing: {e}")

    async def _process_unprocessed_trajectories(self):
        """只处理未处理的轨迹"""
        logger.info("🔄 Processing only unprocessed trajectories...")
        try:
            trajectories_dir = get_trajectories_dir()
            if not os.path.exists(trajectories_dir):
                logger.warning("Trajectories directory not found")
                return
            
            processed_count = 0
            
            # 获取所有轨迹文件并处理其中未处理的轨迹
            for filename in os.listdir(trajectories_dir):
                if filename.endswith('.json'):
                    trajectory_path = os.path.join(trajectories_dir, filename)
                    # 处理文件中所有未处理的轨迹
                    file_processed_count = await self._process_unprocessed_in_file(trajectory_path)
                    processed_count += file_processed_count
            
            logger.info(f"🎯 Unprocessed trajectories completed: {processed_count} new trajectories processed")
            
        except Exception as e:
            logger.error(f"Error processing unprocessed trajectories: {e}")

    async def _process_unprocessed_in_file(self, trajectory_path: str) -> int:
        """处理单个文件中未处理的轨迹，返回处理数量"""
        try:
            logger.info(f"🔍 Checking for unprocessed trajectories in: {trajectory_path}")
            if not os.path.exists(trajectory_path) or os.path.getsize(trajectory_path) == 0:
                logger.info(f"📝 Trajectory file is empty or does not exist: {trajectory_path}")
                return 0
            
            with open(trajectory_path, 'r', encoding='utf-8') as f:
                try:
                    trajectory_data = json.load(f)
                except json.JSONDecodeError as e:
                    logger.error(f"❌ Error decoding JSON from {trajectory_path}: {e}")
                    return 0 #无法解析文件，返回0
            
            processed_count = 0
            new_seed_tasks = []  # 收集新生成的种子任务
            
            # 如果是轨迹列表，处理每一个未处理的轨迹
            if isinstance(trajectory_data, list):
                logger.info(f"📊 Found trajectory collection with {len(trajectory_data)} trajectories")
                for i, single_trajectory in enumerate(trajectory_data):
                    if processed_count >= 10:  # 处理数量限制
                        logger.info(f"⏹️ Reached processing limit of 10 trajectories")
                        break
                    try:
                        trajectory = self._convert_trajectory_format(single_trajectory)
                        if trajectory:
                            # 基于轨迹ID检查是否已处理
                            if not self._is_trajectory_processed(trajectory.task_id):
                                should_process = self._should_process_trajectory(trajectory)
                                logger.info(f"📋 New trajectory {trajectory.task_id}: runtime={trajectory.runtime_id}, success={trajectory.success}, should_process={should_process}")
                                
                                if should_process:
                                    essence = await self._extract_essence(trajectory)
                                    if essence:
                                        self._store_essence(essence)
                                        
                                        # 立即生成种子任务
                                        seed_task = await self._convert_essence_to_seed(essence)
                                        if seed_task:
                                            new_seed_tasks.append(seed_task)
                                            logger.info(f"🌱 Generated seed task from essence: {essence.essence_id}")
                                        
                                        # 标记这个轨迹ID已处理
                                        self._mark_trajectory_processed(trajectory.task_id)
                                        processed_count += 1
                                        logger.info(f"✅ Extracted essence {essence.task_type}/{essence.domain} from trajectory {trajectory.task_id}")
                                    else:
                                        logger.warning(f"❌ Failed to extract essence from trajectory {trajectory.task_id}")
                                        # 即使提取失败也标记为已处理，避免重复尝试
                                        self._mark_trajectory_processed(trajectory.task_id)
                                else:
                                    logger.info(f"⏭️ Skipping trajectory {trajectory.task_id} (not worth processing)")
                                    # 标记为已处理
                                    self._mark_trajectory_processed(trajectory.task_id)
                            else:
                                logger.debug(f"⏭️ Trajectory {trajectory.task_id} already processed")
                    except Exception as e:
                        logger.error(f"❌ Error processing trajectory {i}: {e}")
                
                # 批量保存种子任务
                if new_seed_tasks:
                    await self._append_seed_tasks(new_seed_tasks)
                    logger.info(f"💾 Saved {len(new_seed_tasks)} seed tasks to file")
                
                if processed_count > 0:
                    logger.info(f"🎯 Successfully processed {processed_count} new trajectories from {trajectory_path}")
                return processed_count
                
            else:
                # 单个轨迹对象
                trajectory = self._convert_trajectory_format(trajectory_data)
                if trajectory and not self._is_trajectory_processed(trajectory.task_id):
                    if self._should_process_trajectory(trajectory):
                        essence = await self._extract_essence(trajectory)
                        if essence:
                            self._store_essence(essence)
                            
                            # 立即生成种子任务
                            seed_task = await self._convert_essence_to_seed(essence)
                            if seed_task:
                                await self._append_seed_tasks([seed_task])
                                logger.info(f"🌱 Generated and saved seed task from essence: {essence.essence_id}")
                            
                            self._mark_trajectory_processed(trajectory.task_id)
                            logger.info(f"✅ Extracted essence from single trajectory {trajectory.task_id}")
                            return 1
                    else:
                        self._mark_trajectory_processed(trajectory.task_id)
                
                return 0
        
        except Exception as e:
            logger.error(f"❌ Error processing trajectory file {trajectory_path}: {e}")
            return 0

    async def _process_specific_trajectory(self, filename: str):
        """处理指定的轨迹文件"""
        logger.info(f"🎯 Processing specific trajectory: {filename}")
        
        try:
            trajectories_dir = "/app/output/trajectories"
            trajectory_path = os.path.join(trajectories_dir, filename)
            
            if not os.path.exists(trajectory_path):
                logger.error(f"Trajectory file not found: {filename}")
                return
            
            await self._process_trajectory_file(trajectory_path)
            self._mark_trajectory_processed(filename)
            logger.info(f"✅ Successfully processed specific trajectory: {filename}")
            
        except Exception as e:
            logger.error(f"Error processing specific trajectory {filename}: {e}")

    async def _report_synthesis_status(self):
        """报告合成服务状态"""
        try:
            # 统计种子任务文件
            seed_count = 0
            seed_type_stats = defaultdict(int)
            if os.path.exists(self.seed_tasks_path):
                with open(self.seed_tasks_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            try:
                                task = json.loads(line.strip())
                                seed_count += 1
                                seed_type_stats[task.get('task_type', 'unknown')] += 1
                            except json.JSONDecodeError:
                                continue
            
            # 统计任务本质文件
            essence_count = 0
            essence_type_stats = defaultdict(int)
            essence_domain_stats = defaultdict(int)
            if os.path.exists(self.task_essences_path):
                essences_data = self._load_json_file(self.task_essences_path, [])
                essence_count = len(essences_data)
                for essence in essences_data:
                    essence_type_stats[essence.get('task_type', 'unknown')] += 1
                    essence_domain_stats[essence.get('domain', 'unknown')] += 1
            
            # 统计轨迹集合状态
            collection_exists = os.path.exists(self.trajectories_collection_path)
            collection_size = 0
            if collection_exists:
                try:
                    with open(self.trajectories_collection_path, 'r', encoding='utf-8') as f:
                        collection_data = json.load(f)
                        collection_size = len(collection_data) if isinstance(collection_data, list) else 0
                except:
                    collection_size = 0
            
            processed_count = len(self.processed_trajectories)
            
            status_info = {
                "synthesis_enabled": self.enabled,
                "storage_type": "JSON文件存储",
                "monitoring_enabled": self.auto_monitor_enabled,
                "target_file": self.trajectories_collection_path,
                "collection_exists": collection_exists,
                "collection_size": collection_size,
                "processed_trajectories": processed_count,
                "unprocessed_count": max(0, collection_size - processed_count),
                "total_task_essences": essence_count,
                "essence_type_distribution": dict(essence_type_stats),
                "essence_domain_distribution": dict(essence_domain_stats),
                "total_seed_tasks": seed_count,
                "seed_type_distribution": dict(seed_type_stats),
                "essence_file_path": self.task_essences_path,
                "seed_file_path": self.seed_tasks_path,
                "observer_running": self.observer.is_alive() if self.observer else False,
                "auto_export_seeds": self.auto_export_seeds
            }
            
            logger.info("📊 Synthesis Status Report:")
            for key, value in status_info.items():
                logger.info(f"  {key}: {value}")
                
            # 发布状态到Redis供外部查询
            await self.redis.xadd(
                "synthesis:status",
                {
                    "timestamp": time.time(),
                    "status": json.dumps(status_info)
                }
            )
            
        except Exception as e:
            logger.error(f"Error generating status report: {e}")

    # 保留原有的自动处理方法作为备用
    async def _process_trajectory_feedback(self):
        """处理轨迹反馈，提取任务本质（原自动处理方法，现在作为备用）"""
        logger.info("⚠️  Note: This is the old auto-processing method, now used as backup")
        
        while True:
            try:
                # 扫描轨迹输出目录
                trajectories_dir = "/app/output/trajectories"
                if not os.path.exists(trajectories_dir):
                    await asyncio.sleep(30)
                    continue
                
                # 处理新的轨迹文件
                for filename in os.listdir(trajectories_dir):
                    if filename.endswith('.json'):
                        trajectory_path = os.path.join(trajectories_dir, filename)
                        
                        # 检查是否已处理
                        if not self._is_trajectory_processed(filename):
                            await self._process_trajectory_file(trajectory_path)
                            self._mark_trajectory_processed(filename)
                
                await asyncio.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                logger.error(f"Error processing trajectory feedback: {e}")
                await asyncio.sleep(30)
    
    def _should_process_trajectory(self, trajectory: TrajectoryResult) -> bool:
        """判断轨迹是否值得处理"""
        # 1. 成功的轨迹总是处理
        if trajectory.success:
            return True
        
        # 2. reasoning runtime的轨迹，即使失败也可能有价值（不要求有执行步骤）
        runtime_id = trajectory.runtime_id.lower()
        if 'reasoning' in runtime_id:
            logger.info(f"🧠 Found reasoning trajectory: {trajectory.task_id}")
            return True
        
        # 3. 有执行步骤的轨迹
        if len(trajectory.steps) > 0:
            # 有多个步骤的复杂任务，即使失败也可能有价值
            if len(trajectory.steps) >= 2:
                return True
        
        # 4. 任务描述包含特定关键词
        task_desc = trajectory.task_description.lower()
        valuable_keywords = ['reasoning', '推理', '分析', 'analysis', 'compare', '对比', '研究']
        if any(keyword in task_desc for keyword in valuable_keywords):
            logger.info(f"🔎 Found valuable keywords in task description: {trajectory.task_id}")
            return True
        
        # 5. 有最终结果的轨迹，即使失败也可能有价值
        if trajectory.final_result and len(trajectory.final_result.strip()) > 50:
            logger.info(f"📝 Found trajectory with substantial final result: {trajectory.task_id}")
            return True
        
        return False

    async def _process_trajectory_file(self, trajectory_path: str) -> bool:
        """处理单个轨迹文件，返回处理是否成功"""
        try:
            logger.info(f"🔍 Processing trajectory file: {trajectory_path}")
            with open(trajectory_path, 'r', encoding='utf-8') as f:
                trajectory_data = json.load(f)
            
            processed_count = 0
            
            # 如果是轨迹列表，处理每一个轨迹
            if isinstance(trajectory_data, list):
                logger.info(f"📊 Processing trajectory collection with {len(trajectory_data)} trajectories")
                for i, single_trajectory in enumerate(trajectory_data):
                    if processed_count >= 10:  # 增加处理数量限制
                        logger.info(f"⏹️ Reached processing limit of 10 trajectories")
                        break
                    try:
                        trajectory = self._convert_trajectory_format(single_trajectory)
                        if trajectory:
                            # 增强轨迹处理逻辑：处理更多类型的轨迹
                            should_process = self._should_process_trajectory(trajectory)
                            logger.info(f"📋 Trajectory {trajectory.task_id}: runtime={trajectory.runtime_id}, success={trajectory.success}, should_process={should_process}")
                            
                            if should_process:
                                essence = await self._extract_essence(trajectory)
                                if essence:
                                    self._store_essence(essence)
                                    processed_count += 1
                                    logger.info(f"✅ Extracted essence {essence.task_type}/{essence.domain} from trajectory {trajectory.task_id}")
                                else:
                                    logger.warning(f"❌ Failed to extract essence from trajectory {trajectory.task_id}")
                            else:
                                logger.info(f"⏭️ Skipping trajectory {trajectory.task_id} (not worth processing)")
                    except Exception as e:
                        logger.error(f"❌ Error processing trajectory {i}: {e}")
                
                logger.info(f"🎯 Successfully processed {processed_count} trajectories from collection")
                return processed_count > 0
                
            else:
                # 单个轨迹对象
                trajectory = self._convert_trajectory_format(trajectory_data)
                if trajectory and self._should_process_trajectory(trajectory):
                    essence = await self._extract_essence(trajectory)
                    if essence:
                        self._store_essence(essence)
                        logger.info(f"✅ Extracted essence from single trajectory {trajectory.task_id}")
                        return True
                
                return False
        
        except Exception as e:
            logger.error(f"❌ Error processing trajectory file {trajectory_path}: {e}")
            return False
    
    def _convert_trajectory_format(self, data: Dict) -> Optional[TrajectoryResult]:
        """将轨迹数据转换为TrajectoryResult格式"""
        try:
            logger.debug(f"Attempting to convert trajectory data for task_id: {data.get('task_id', 'Unknown')}, type of data: {type(data)}")
            # 转换steps格式
            converted_steps = []
            steps_list = data.get('steps', [])
            if not isinstance(steps_list, list):
                logger.error(f"Field 'steps' is not a list for task_id: {data.get('task_id', 'Unknown')}. Got {type(steps_list)}. Skipping steps conversion.")
                steps_list = []

            for i, step_data in enumerate(steps_list):
                logger.debug(f"Processing step {i} for task_id: {data.get('task_id', 'Unknown')}: type={type(step_data)}, content='{str(step_data)[:200]}...'")
                
                # 处理ExecutionStep对象
                if hasattr(step_data, 'to_dict'):
                    # 如果是ExecutionStep对象，直接使用
                    converted_steps.append(step_data)
                    continue
                elif isinstance(step_data, str) and step_data.startswith('ExecutionStep('):
                    # 如果是ExecutionStep的字符串表示，跳过（无法安全解析）
                    logger.warning(f"Skipping ExecutionStep string representation for step {i} in task_id: {data.get('task_id', 'Unknown')}")
                    continue
                elif isinstance(step_data, dict):
                    # 如果是字典，转换为ExecutionStep对象
                    converted_step = ExecutionStep(
                        step_id=step_data.get('step_id', 0),
                        action_type=ActionType(step_data.get('action_type', 'code_generation')),
                        action_params=step_data.get('action_params', step_data.get('tool_input', {})),
                        observation=step_data.get('observation', step_data.get('tool_output', '')),
                        success=step_data.get('success', True),
                        thinking=step_data.get('thinking'),
                        execution_code=step_data.get('execution_code'),
                        error_type=self._safe_parse_error_type(step_data.get('error_type')), # 确保是ErrorType枚举
                        error_message=step_data.get('error_message'),
                        timestamp=step_data.get('timestamp', time.time()),
                        duration=step_data.get('duration', 0.0),
                        # llm_interactions 字段在 ExecutionStep 定义中，但原始数据中可能没有，需要处理
                        llm_interactions=[LLMInteraction(**interaction_dict) for interaction_dict in step_data.get('llm_interactions', []) if isinstance(interaction_dict, dict)]
                    )
                    converted_steps.append(converted_step)
                else:
                    logger.error(f"Skipping step {i} for task_id: {data.get('task_id', 'Unknown')} due to unexpected format. Expected dict or ExecutionStep, got {type(step_data)}. Content: {str(step_data)[:200]}")
                    continue
            
            # 创建TrajectoryResult对象
            return TrajectoryResult(
                task_id=data.get('task_id', str(uuid.uuid4())),
                task_name=data.get('task_name', data.get('task_id', 'unknown')),
                task_description=data.get('task_description', ''),
                runtime_id=data.get('runtime_id', 'unknown'),
                success=data.get('success', False),
                steps=converted_steps,
                final_result=data.get('final_result', ''),
                error_type=self._safe_parse_error_type(data.get('error_type')),
                error_message=data.get('error_message'),
                total_duration=data.get('total_duration', 0.0),
                metadata=data.get('metadata', {}),
                created_at=data.get('created_at', time.time())
            )
            
        except Exception as e:
            logger.error(f"Error converting trajectory format: {e}")
            return None
    
    def _safe_parse_error_type(self, error_type_data) -> Optional[ErrorType]:
        """安全解析错误类型"""
        if not error_type_data:
            return None
        
        try:
            # 如果已经是ErrorType实例
            if isinstance(error_type_data, ErrorType):
                return error_type_data
            
            # 如果是字符串
            if isinstance(error_type_data, str):
                # 处理错误序列化的情况，如 'ErrorType.SYSTEM_ERROR'
                if error_type_data.startswith('ErrorType.'):
                    enum_name = error_type_data.replace('ErrorType.', '')
                    # 将大写转换为小写下划线格式
                    error_type_value = enum_name.lower()
                    return ErrorType(error_type_value)
                else:
                    # 直接是枚举值
                    return ErrorType(error_type_data)
            
            return None
        except (ValueError, KeyError):
            logger.warning(f"无法解析错误类型: {error_type_data}")
            return None
    
    async def _extract_essence(self, trajectory: TrajectoryResult) -> Optional[TaskEssence]:
        """使用LLM提取轨迹本质"""
        try:
            # 构建分析提示
            prompt = self._build_extraction_prompt(trajectory)
            
            # 调用LLM
            messages = [{"role": "user", "content": prompt}]
            response = await self.llm_client._call_api(messages)
            
            # 解析响应
            return self._parse_extraction_response(response, trajectory)
            
        except Exception as e:
            logger.error(f"Error extracting essence: {e}")
            return None
    
    def _build_extraction_prompt(self, trajectory: TrajectoryResult) -> str:
        """构建本质提取提示 - 提供完整轨迹信息"""
        # 构建完整的执行步骤信息
        steps_detail = []
        for i, step in enumerate(trajectory.steps, 1):
            step_info = f"""步骤 {i}:
  动作类型: {step.action_type}
  执行参数: {json.dumps(step.action_params, ensure_ascii=False)[:300]}
  执行结果: {step.observation[:500]}{"..." if len(step.observation) > 500 else ""}
  是否成功: {step.success}
  思考过程: {step.thinking[:300] if step.thinking else "无"}{"..." if step.thinking and len(step.thinking) > 300 else ""}
  耗时: {step.duration:.2f}秒"""
            
            if step.error_message:
                step_info += f"\n  错误信息: {step.error_message[:200]}"
            
            steps_detail.append(step_info)
        
        # 提取runtime信息和智能提示
        runtime_analysis = ""
        if hasattr(trajectory, 'runtime_id') and trajectory.runtime_id:
            runtime_id = trajectory.runtime_id.lower()
            if 'reasoning' in runtime_id:
                runtime_analysis = """
这是一个Reasoning Runtime执行的任务，特点：
- 通常涉及多个工具的协同使用（浏览器+代码执行等）
- 需要复杂的决策和推理过程
- 任务目标往往是分析、对比、研究类问题"""
            elif 'web' in runtime_id:
                runtime_analysis = """
这是一个Web Runtime执行的任务，特点：
- 主要使用浏览器进行网页操作
- 涉及信息搜索、网页导航、数据提取
- 任务目标通常是获取特定网页信息"""
            elif 'sandbox' in runtime_id or 'code' in runtime_id:
                runtime_analysis = """
这是一个Code Runtime执行的任务，特点：
- 主要进行Python代码生成和执行
- 解决计算、算法、数据处理问题
- 任务目标通常是实现特定功能或计算"""
        
        # 构建工具使用分析
        tools_used = set()
        for step in trajectory.steps:
            if 'browser' in str(step.action_type).lower():
                tools_used.add("浏览器操作")
            if 'python' in str(step.observation).lower() or 'code' in str(step.action_type).lower():
                tools_used.add("Python代码")
            if 'navigate' in str(step.action_params) or 'url' in str(step.action_params):
                tools_used.add("网页导航")
        
        tools_analysis = f"使用的工具类型: {', '.join(tools_used) if tools_used else '未明确'}"
        
        return f"""请分析以下完整的任务执行轨迹，提取任务的本质特征并生成优化的任务描述：

=== 任务基本信息 ===
任务ID: {trajectory.task_id}
原始描述: {trajectory.task_description}
执行环境: {trajectory.runtime_id}
执行状态: {"成功" if trajectory.success else "失败"}
总步骤数: {len(trajectory.steps)}
总耗时: {trajectory.total_duration:.2f}秒
最终结果: {trajectory.final_result[:400]}{"..." if len(trajectory.final_result) > 400 else ""}

{runtime_analysis}

=== 工具使用分析 ===
{tools_analysis}

=== 完整执行轨迹 ===
{chr(10).join(steps_detail)}

=== 分析要求 ===
请基于以上完整轨迹信息，进行深度分析并提取：

1. **任务类型分类** (task_type):
   - "reasoning": 多工具协同任务，涉及复杂分析、对比研究、决策推理等
   - "web": 纯网页操作任务，专注于信息搜索、网站导航、数据提取等  
   - "code": 纯编程任务，专注于算法实现、计算、数据处理等

2. **任务领域** (domain):
   - algorithm: 算法、数学计算、数据结构
   - data_analysis: 数据分析、统计、可视化
   - web_automation: 网页自动化、信息提取
   - research: 研究调查、对比分析  
   - comparison: 对比评估、竞品分析
   - stock_analysis: 金融分析、股票研究
   - educational: 教育、学习、知识获取
   - 其他合适的领域

3. **优化任务描述** (optimized_description):
   基于轨迹分析，生成一个清晰、具体、可执行的任务描述，要求：
   - 明确说明任务目标
   - 指出需要使用的主要工具或方法
   - 突出任务的核心价值和难点
   - 长度控制在50-100字

4. **复杂度评估** (complexity):
   - simple: 单步骤或简单操作
   - medium: 多步骤协调或中等难度分析
   - complex: 深度分析、多工具集成或高难度推理

5. **关键特征** (key_features):
   列出这个任务的3-5个关键特征

请严格按照以下JSON格式返回分析结果：

{{
  "task_type": "...",
  "domain": "...", 
  "optimized_description": "...",
  "complexity": "...",
  "key_features": ["特征1", "特征2", "特征3"],
  "confidence": 0.9
}}

注意：请确保分析准确、描述清晰、分类合理。"""
    
    def _parse_extraction_response(self, response: str, trajectory: TrajectoryResult) -> Optional[TaskEssence]:
        """解析LLM响应，处理优化后的JSON格式"""
        try:
            # 提取JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                
                # 获取LLM分析的结果
                llm_task_type = parsed.get("task_type", "").lower()
                llm_domain = parsed.get("domain", "general")
                optimized_description = parsed.get("optimized_description", "")
                complexity = parsed.get("complexity", "medium")
                key_features = parsed.get("key_features", [])
                confidence = parsed.get("confidence", 0.8)
                
                # 智能任务类型推断和验证
                final_task_type = self._infer_task_type(trajectory, llm_task_type)
                
                # 智能领域推断和验证
                final_domain = self._infer_domain(trajectory, llm_domain, final_task_type)
                
                # 使用优化后的描述，如果没有则回退到原始描述
                final_query = optimized_description if optimized_description else trajectory.task_description[:50]
                
                # 构建增强的成功模式
                enhanced_success_pattern = {
                    "duration": trajectory.total_duration,
                    "steps_count": len(trajectory.steps),
                    "key_features": key_features,
                    "confidence": confidence,
                    "tools_used": self._extract_tools_from_trajectory(trajectory)
                }
                
                logger.info(f"🧠 Enhanced task analysis:")
                logger.info(f"   Type: {llm_task_type} → {final_task_type}")
                logger.info(f"   Domain: {final_domain}")
                logger.info(f"   Optimized description: {final_query[:80]}...")
                logger.info(f"   Key features: {key_features}")
                logger.info(f"   Confidence: {confidence}")
                
                return TaskEssence(
                    essence_id=f"essence_{int(time.time())}_{trajectory.task_id}",
                    task_type=final_task_type,
                    domain=final_domain,
                    query=final_query,
                    complexity_level=complexity,
                    success_pattern=enhanced_success_pattern,
                    extracted_at=datetime.now().isoformat(),
                    source_trajectory_id=trajectory.task_id
                )
            else:
                logger.error(f"Failed to parse JSON response from LLM for essence {trajectory.task_id}")
                logger.warning(f"Response content: {response[:200]}...")
                return None
                
        except Exception as e:
            logger.error(f"Error parsing enhanced extraction response: {e}")
            logger.warning(f"Response content: {response[:500]}...")
            # 即使解析失败，也尝试基于轨迹特征创建基础本质
            return self._create_fallback_essence(trajectory)
        
        return None
    
    def _extract_tools_from_trajectory(self, trajectory: TrajectoryResult) -> List[str]:
        """从轨迹中提取使用的工具"""
        tools = set()
        
        for step in trajectory.steps:
            # 优先从 action_params 中提取 tool_id
            if step.action_type == ActionType.TOOL_CALL and 'tool_id' in step.action_params:
                tools.add(step.action_params['tool_id'])
            
            # 如果没有明确的 tool_id，则基于 action_type 和 action_params 进行推断
            action_type_str = str(step.action_type).lower()
            
            if 'browser_action' in action_type_str:
                tools.add("browser_navigator") # 使用文档中定义的tool_id
            elif 'code_execution' in action_type_str:
                tools.add("python_executor") # 使用文档中定义的tool_id
            
            # 进一步基于 action_params 中的关键词推断
            if step.action_params:
                params_str = str(step.action_params).lower()
                if 'url' in params_str or 'navigate' in params_str:
                    tools.add("browser_navigator")
                if 'code' in params_str or 'python' in params_str:
                    tools.add("python_executor")
                # 假设有其他工具，例如文件处理工具
                if 'file' in params_str or 'path' in params_str:
                    tools.add("file_processor")
            
            # 基于 observation 识别工具输出 (作为补充)
            if step.observation:
                obs_str = str(step.observation).lower()
                if 'browser' in obs_str or 'page' in obs_str or 'website' in obs_str:
                    tools.add("browser_navigator")
                if 'python' in obs_str or 'execution' in obs_str:
                    tools.add("python_executor")
        
        return list(tools)
    
    def _infer_task_type(self, trajectory: TrajectoryResult, llm_suggestion: str) -> str:
        """智能推断任务类型"""
        # 1. 基于runtime_id的强规则
        if hasattr(trajectory, 'runtime_id') and trajectory.runtime_id:
            runtime_id = trajectory.runtime_id.lower()
            if 'reasoning' in runtime_id:
                return "reasoning"
            elif 'web' in runtime_id:
                return "web"  
            elif 'sandbox' in runtime_id or 'code' in runtime_id:
                return "code"
        
        # 2. 基于任务描述的关键词
        desc = trajectory.task_description.lower()
        reasoning_keywords = ['分析', '对比', '研究', '推理', 'analysis', 'compare', 'research', 'reasoning', '影响']
        web_keywords = ['搜索', '访问', '浏览器', 'search', 'visit', 'browser', 'google', 'github']
        code_keywords = ['计算', '算法', '代码', '函数', 'calculate', 'algorithm', 'function', 'code', '矩阵']
        
        if any(keyword in desc for keyword in reasoning_keywords):
            return "reasoning"
        elif any(keyword in desc for keyword in web_keywords):
            return "web"
        elif any(keyword in desc for keyword in code_keywords):
            return "code"
        
        # 3. 基于执行步骤分析
        if len(trajectory.steps) > 0:
            # 检查是否有浏览器操作
            has_browser = any('browser' in str(step.action_type).lower() or 'navigate' in str(step.action_params) for step in trajectory.steps)
            # 检查是否有代码执行
            has_code = any('code' in str(step.action_type).lower() or 'python' in str(step.observation).lower() for step in trajectory.steps)
            
            if has_browser and has_code:
                return "reasoning"  # 多工具协同
            elif has_browser:
                return "web"
            elif has_code:
                return "code"
        
        # 4. 使用LLM建议（如果有效）
        if llm_suggestion in ['reasoning', 'web', 'code']:
            return llm_suggestion
        
        # 5. 默认值
        return "code"
    
    def _infer_domain(self, trajectory: TrajectoryResult, llm_domain: str, task_type: str) -> str:
        """智能推断任务领域"""
        desc = trajectory.task_description.lower()
        
        # 基于关键词的领域映射
        domain_keywords = {
            'algorithm': ['算法', '计算', '数学', 'algorithm', 'calculate', 'math', '排序', '搜索'],
            'data_analysis': ['数据', '分析', '统计', 'data', 'analysis', 'statistics', '图表'],
            'web_automation': ['网页', '浏览器', '搜索', 'web', 'browser', 'search', 'google'],
            'research': ['研究', '对比', '调查', 'research', 'compare', 'study', '影响'],
            'comparison': ['对比', '比较', 'vs', 'compare', 'comparison', '区别'],
            'stock_analysis': ['股票', '股价', 'stock', 'price', '投资', 'investment']
        }
        
        for domain, keywords in domain_keywords.items():
            if any(keyword in desc for keyword in keywords):
                return domain
        
        # 基于任务类型的默认领域
        type_domain_map = {
            'reasoning': 'research',
            'web': 'web_automation', 
            'code': 'algorithm'
        }
        
        return type_domain_map.get(task_type, llm_domain if llm_domain != "general" else "general")
    
    def _create_fallback_essence(self, trajectory: TrajectoryResult) -> Optional[TaskEssence]:
        """创建备用本质（当LLM解析失败时）"""
        try:
            task_type = self._infer_task_type(trajectory, "")
            domain = self._infer_domain(trajectory, "general", task_type)
            
            return TaskEssence(
                essence_id=f"essence_{int(time.time())}_{trajectory.task_id}",
                task_type=task_type,
                domain=domain,
                query=trajectory.task_description[:20],
                complexity_level="medium",
                success_pattern={"duration": trajectory.total_duration},
                extracted_at=datetime.now().isoformat(),
                source_trajectory_id=trajectory.task_id
            )
        except Exception as e:
            logger.error(f"Failed to create fallback essence: {e}")
            return None
    
    def _store_essence(self, essence: TaskEssence):
        """存储任务本质到JSON文件"""
        try:
            # 读取现有本质
            existing_essences = self._load_json_file(self.task_essences_path, [])
            
            # 添加新本质
            essence_dict = asdict(essence)
            existing_essences.append(essence_dict)
            
            # 保存回文件
            if self._save_json_file(self.task_essences_path, existing_essences):
                logger.info(f"💾 成功保存任务本质: {essence.essence_id}")
                logger.info(f"  类型: {essence.task_type}")
                logger.info(f"  领域: {essence.domain}")
                logger.info(f"  描述: {essence.query[:50]}...")
                logger.info(f"  复杂度: {essence.complexity_level}")
                logger.info(f"  来源轨迹: {essence.source_trajectory_id}")
            else:
                logger.error(f"❌ 保存任务本质失败: {essence.essence_id}")
            
        except Exception as e:
            logger.error(f"❌ 存储任务本质时出错: {e}")

    async def _generate_seeds_from_existing_essences(self):
        """从现有的任务本质生成种子任务"""
        try:
            logger.info("🌱 开始从现有任务本质生成种子任务...")
            
            # 读取现有任务本质
            essences_data = self._load_json_file(self.task_essences_path, [])
            if not essences_data:
                logger.warning("⚠️ 没有找到任务本质数据")
                return
            
            logger.info(f"📊 找到 {len(essences_data)} 个任务本质")
            
            # 转换为TaskEssence对象并生成种子任务
            seed_tasks = []
            for essence_data in essences_data:
                try:
                    # 重构TaskEssence对象
                    essence = TaskEssence(
                        essence_id=essence_data['essence_id'],
                        task_type=essence_data['task_type'],
                        domain=essence_data['domain'],
                        query=essence_data['query'],
                        complexity_level=essence_data['complexity_level'],
                        success_pattern=essence_data['success_pattern'],
                        extracted_at=essence_data['extracted_at'],
                        source_trajectory_id=essence_data['source_trajectory_id']
                    )
                    
                    # 生成种子任务
                    seed_task = await self._convert_essence_to_seed(essence)
                    if seed_task:
                        seed_tasks.append(seed_task)
                        logger.debug(f"✅ 从本质 {essence.essence_id} 生成种子任务")
                    
                except Exception as e:
                    logger.error(f"❌ 处理任务本质时出错: {e}")
                    continue
            
            # 保存生成的种子任务
            if seed_tasks:
                await self._append_seed_tasks(seed_tasks)
                logger.info(f"🎯 成功生成并保存 {len(seed_tasks)} 个种子任务")
                
                # 统计信息
                type_stats = defaultdict(int)
                domain_stats = defaultdict(int)
                for task in seed_tasks:
                    type_stats[task['task_type']] += 1
                    domain_stats[task['domain']] += 1
                
                logger.info(f"📊 种子任务类型分布: {dict(type_stats)}")
                logger.info(f"📊 种子任务领域分布: {dict(domain_stats)}")
            else:
                logger.warning("⚠️ 没有成功生成任何种子任务")
                
        except Exception as e:
            logger.error(f"❌ 从任务本质生成种子任务失败: {e}")

    async def generate_tasks_manually(self, count: int = 3) -> List[TaskSpec]:
        """手动生成指定数量的任务（暂时禁用，因为没有本质存储）"""
        logger.warning("⚠️ 手动任务生成功能已禁用，请使用轨迹处理生成种子任务")
        return []

    async def generate_task_from_specific_essence(self, essence_id: str) -> Optional[TaskSpec]:
        """基于指定的任务本质生成新任务（暂时禁用）"""
        logger.warning("⚠️ 指定本质任务生成功能已禁用，请使用轨迹处理生成种子任务")
        return None
    
    def _get_random_essences(self, count: int) -> List[TaskEssence]:
        """获取随机的种子本质（暂时禁用）"""
        logger.warning("⚠️ 随机本质获取功能已禁用，请使用轨迹处理生成种子任务")
        return []
        
    def _record_generated_task(self, task: TaskSpec, essence_id: str):
        """记录生成的任务（简化版，仅记录日志）"""
        try:
            logger.info(f"✅ 记录生成任务: {task.task_id}")
            logger.info(f"  来源本质: {essence_id}")
            logger.info(f"  任务类型: {task.task_type}")
            logger.info(f"  生成时间: {datetime.now().isoformat()}")
                
        except Exception as e:
            logger.error(f"❌ 记录生成任务时出错: {e}")

    def _is_trajectory_processed(self, trajectory_id: str) -> bool:
        """检查轨迹是否已处理（基于持久化存储）"""
        is_processed = trajectory_id in self.processed_trajectories
        if is_processed:
            logger.debug(f"🔍 轨迹已处理过: {trajectory_id}")
        return is_processed
    
    def _mark_trajectory_processed(self, trajectory_id: str):
        """标记轨迹已处理（持久化到文件）"""
        if trajectory_id not in self.processed_trajectories:
            self.processed_trajectories.add(trajectory_id)
            # 立即保存到文件
            self._save_processed_trajectories()
            logger.info(f"✅ 标记轨迹已处理并保存: {trajectory_id}")
        else:
            logger.debug(f"⚠️ 轨迹已经在处理记录中: {trajectory_id}")
    
    async def _generate_task_from_essence(self, essence: TaskEssence) -> Optional[TaskSpec]:
        """基于本质生成新任务"""
        try:
            # 解析增强的成功模式
            success_pattern = essence.success_pattern
            key_features = success_pattern.get("key_features", [])
            tools_used = success_pattern.get("tools_used", [])
            confidence = success_pattern.get("confidence", 0.8)
            
            # 构建增强的变异提示
            prompt = f"""基于以下高质量任务本质，生成一个相似但创新的新任务：

=== 原任务分析 ===
任务类型: {essence.task_type}
任务领域: {essence.domain}
优化描述: {essence.query}
复杂度等级: {essence.complexity_level}
提取置信度: {confidence}

=== 关键特征 ===
{chr(10).join(f"- {feature}" for feature in key_features)}

=== 工具使用模式 ===
主要工具: {', '.join(tools_used) if tools_used else '未指定'}

=== 任务生成要求 ===
请基于上述分析，创造一个新的同类型任务，要求：

1. **保持核心特征**：
   - 任务类型必须是 {essence.task_type}
   - 领域应该是 {essence.domain} 或相关领域
   - 复杂度保持在 {essence.complexity_level} 级别

2. **创新变化**：
   - 改变具体的目标对象或参数
   - 调整场景设定或应用背景
   - 保持任务的挑战性和价值

3. **实用性要求**：
   - 任务描述清晰具体，可直接执行
   - 说明预期使用的工具和方法
   - 确保任务有明确的成功标准

4. **质量标准**：
   - 任务描述长度60-120字
   - 避免过于简单或过于复杂
   - 确保任务具有实际应用价值

=== 示例格式参考 ===
{essence.task_type}类型任务示例：
- reasoning: "使用浏览器搜索和Python分析，对比分析ChatGPT和Claude在代码生成能力上的差异，从准确性、效率和可读性三个维度进行评估"
- web: "访问GitHub搜索最受欢迎的机器学习项目，筛选star数量超过10k的项目，提取项目名称、简介和主要技术栈信息"  
- code: "实现一个高效的快速排序算法，要求支持自定义比较函数，并添加性能测试代码验证在不同数据规模下的执行效率"

请严格按照以下JSON格式返回：

{{
  "description": "新任务的详细描述",
  "expected_tools": ["工具1", "工具2"],
  "success_criteria": "成功标准描述",
  "estimated_steps": 数字,
  "innovation_points": ["创新点1", "创新点2"]
}}

注意：确保生成的任务既保持原有特征，又具有创新性和实用价值。"""
            
            messages = [{"role": "user", "content": prompt}]
            response = await self.llm_client._call_api(messages)
            
            # 解析响应
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                
                # 构建增强的TaskSpec
                task_id = f"synth_{essence.task_type}_{essence.domain}_{int(time.time())}"
                
                # 确定expected_tools，结合原有工具和新建议
                expected_tools = parsed.get("expected_tools", tools_used if tools_used else ["python_executor"])
                
                # 根据复杂度调整max_steps
                complexity_steps_map = {
                    "simple": 3,
                    "medium": 6, 
                    "complex": 10
                }
                max_steps = complexity_steps_map.get(essence.complexity_level, 5)
                
                # 如果LLM提供了估计步骤数，使用它
                if "estimated_steps" in parsed:
                    max_steps = min(parsed["estimated_steps"], 15)  # 最大不超过15步
                
                logger.info(f"✨ Generated enhanced task:")
                logger.info(f"   Task ID: {task_id}")
                logger.info(f"   Description: {parsed.get('description', '')[:80]}...")
                logger.info(f"   Expected tools: {expected_tools}")
                logger.info(f"   Max steps: {max_steps}")
                
                return TaskSpec(
                    task_id=task_id,
                    task_type=TaskType(essence.task_type),
                    description=parsed.get("description", essence.query),
                    expected_tools=expected_tools,
                    constraints={
                        "success_criteria": parsed.get("success_criteria", ""),
                        "innovation_points": parsed.get("innovation_points", []),
                        "source_essence": essence.essence_id
                    },
                    max_steps=max_steps,
                    priority=1
                )
            else:
                logger.error(f"Failed to parse JSON response from LLM for essence {essence.essence_id}")
                logger.warning(f"Response content: {response[:200]}...")
                return None
        
        except Exception as e:
            logger.error(f"Error generating task from essence {essence.essence_id}: {e}")
        return None
    
    async def _publish_task(self, task: TaskSpec):
        """发布任务到对应队列"""
        queue_mapping = {
            TaskType.CODE: "tasks:code",
            TaskType.WEB: "tasks:web",
            TaskType.REASONING: "tasks:reasoning"
        }
        
        queue_name = queue_mapping.get(task.task_type, "tasks:code")
        
        await self.redis.xadd(
            queue_name,
            {
                "task": task.json(),
                "submitted_at": time.time(),
                "priority": task.priority,
                "source": "synthesis"
            }
        )

async def main():
    """任务合成器主程序"""
    config = {
        "redis_url": os.getenv("REDIS_URL", "redis://redis:6379"),
        "synthesis_enabled": os.getenv("SYNTHESIS_ENABLED", "false").lower() == "true",
        "auto_monitor_trajectories": os.getenv("AUTO_MONITOR_TRAJECTORIES", "true").lower() == "true",
        "auto_export_seeds": os.getenv("AUTO_EXPORT_SEEDS", "true").lower() == "true",
        # "vllm_url": os.getenv("VLLM_URL", "http://vllm:8000") # 用户不使用vLLM，注释掉此配置
    }
    
    # 输出配置信息
    logger.info("🚀 启动基于JSON的任务合成器，配置如下:")
    logger.info(f"  合成器启用: {config['synthesis_enabled']}")
    logger.info(f"  自动轨迹监控: {config['auto_monitor_trajectories']}")
    logger.info(f"  自动种子导出: {config['auto_export_seeds']}")
    logger.info(f"  存储方式: JSON文件")
    
    synthesizer = SynthesisService(config)
    
    try:
        if config["synthesis_enabled"]:
            logger.info("🎯 开始启动任务合成服务...")
            await synthesizer.start()
        else:
            logger.info("⚠️ 任务合成功能已禁用，服务将等待...")
            # 保持服务运行，但不执行合成逻辑
            while True:
                await asyncio.sleep(60)
                logger.info("Synthesis service waiting (disabled)...")
    except KeyboardInterrupt:
        logger.info("🛑 合成服务被中断")
    finally:
        try:
            # 停止文件监控
            if hasattr(synthesizer, 'observer') and synthesizer.observer and synthesizer.observer.is_alive():
                synthesizer.observer.stop()
                synthesizer.observer.join()
                logger.info("📁 文件监控已停止")
            
            # 清理UnifiedToolLibrary管理的资源
            if hasattr(synthesizer, 'tool_library'):
               
               
               
                await synthesizer.tool_library.cleanup()
                logger.info("🧹 UnifiedToolLibrary资源已清理")

            await synthesizer.redis.aclose()  # 使用aclose()替代close()
            logger.info("🔌 Redis连接已关闭")
        except Exception as e:
            logger.warning(f"⚠️ 关闭资源时出错: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())