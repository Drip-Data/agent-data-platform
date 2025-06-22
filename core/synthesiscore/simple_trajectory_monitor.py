#!/usr/bin/env python3
"""
简化轨迹监控器 - 自动监控轨迹文件变化并生成种子任务
绕过复杂的Redis配置，专注于核心功能
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)


class SimpleTrajectoryFileHandler(FileSystemEventHandler):
    """简化的轨迹文件事件处理器"""
    
    def __init__(self, monitor):
        self.monitor = monitor
        self.last_processed = {}
        
    def on_modified(self, event):
        """文件修改事件"""
        if event.is_directory:
            return
            
        if event.src_path.endswith('trajectories_collection.json'):
            # 避免频繁触发，设置最小间隔
            current_time = time.time()
            last_time = self.last_processed.get(event.src_path, 0)
            
            if current_time - last_time > 2.0:  # 2秒间隔
                self.last_processed[event.src_path] = current_time
                logger.info(f"📁 检测到轨迹文件变化: {event.src_path}")
                
                # 使用线程池执行异步任务
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        self.monitor.process_trajectory_changes(event.src_path)
                    )
                finally:
                    loop.close()


class SimpleTrajectoryMonitor:
    """简化轨迹监控器 - 专注于文件监控和种子任务生成"""
    
    def __init__(self, trajectories_dir: str = None, seed_tasks_file: str = None):
        # 路径配置 - 使用动态路径替代硬编码
        from core.utils.path_utils import get_output_dir
        
        self.trajectories_dir = trajectories_dir or str(get_output_dir("trajectories"))
        self.seed_tasks_file = seed_tasks_file or str(get_output_dir() / "seed_tasks.jsonl")
        self.trajectories_collection_file = os.path.join(self.trajectories_dir, "trajectories_collection.json")
        self.processed_trajectories_file = os.path.join(self.trajectories_dir, "..", "processed_trajectories.json")
        
        # 文件监控
        self.observer = Observer()
        self.file_handler = SimpleTrajectoryFileHandler(self)
        
        # 已处理轨迹记录
        self.processed_trajectories = self._load_processed_trajectories()
        
        logger.info(f"🔧 SimpleTrajectoryMonitor初始化完成")
        logger.info(f"📂 监控目录: {self.trajectories_dir}")
        logger.info(f"📝 种子文件: {self.seed_tasks_file}")
    
    async def initialize(self):
        """初始化监控器"""
        try:
            # 确保目录和文件存在
            os.makedirs(os.path.dirname(self.seed_tasks_file), exist_ok=True)
            os.makedirs(self.trajectories_dir, exist_ok=True)
            
            # 处理现有轨迹
            await self.process_existing_trajectories()
            
            logger.info("✅ SimpleTrajectoryMonitor初始化完成")
            
        except Exception as e:
            logger.error(f"❌ SimpleTrajectoryMonitor初始化失败: {e}")
            raise
    
    async def start_monitoring(self):
        """开始监控轨迹文件"""
        try:
            # 设置文件监控
            self.observer.schedule(
                self.file_handler,
                path=self.trajectories_dir,
                recursive=False
            )
            
            # 启动监控
            self.observer.start()
            logger.info(f"👁️ 开始监控轨迹文件变化: {self.trajectories_dir}")
            
        except Exception as e:
            logger.error(f"❌ 启动文件监控失败: {e}")
            raise
    
    async def stop_monitoring(self):
        """停止监控"""
        try:
            if self.observer.is_alive():
                self.observer.stop()
                self.observer.join()
                logger.info("🛑 轨迹文件监控已停止")
            
        except Exception as e:
            logger.error(f"❌ 停止监控失败: {e}")
    
    async def process_existing_trajectories(self):
        """处理现有轨迹"""
        logger.info("🔄 检查并处理现有轨迹...")
        
        if os.path.exists(self.trajectories_collection_file):
            await self.process_trajectory_changes(self.trajectories_collection_file)
        else:
            logger.info("📝 没有现有轨迹文件")
    
    async def process_trajectory_changes(self, file_path: str):
        """处理轨迹文件变化 - 使用简化的生成器"""
        logger.info(f"🔄 处理轨迹文件: {file_path}")
        
        try:
            # 使用简化的种子任务生成器
            from .simple_seed_generator import SimpleSeedGenerator
            
            generator = SimpleSeedGenerator(
                trajectories_file=file_path,
                seed_tasks_file=self.seed_tasks_file,
                processed_file=self.processed_trajectories_file
            )
            
            # 生成种子任务
            result = generator.process_trajectories()
            
            if result["success"]:
                logger.info(f"✅ 轨迹处理完成，生成种子任务: {result['new_tasks']} 个")
                
                # 更新内存中的已处理记录
                self.processed_trajectories = generator.processed_trajectories
            else:
                logger.error(f"❌ 轨迹处理失败: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"❌ 处理轨迹变化失败: {e}")
    
    def _load_processed_trajectories(self) -> set:
        """加载已处理轨迹记录"""
        try:
            if os.path.exists(self.processed_trajectories_file):
                with open(self.processed_trajectories_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict) and 'processed' in data:
                        return set(data['processed'])
                    elif isinstance(data, list):
                        return set(data)
            return set()
            
        except Exception as e:
            logger.error(f"❌ 加载已处理轨迹记录失败: {e}")
            return set()
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            # 读取种子任务文件统计
            seed_count = 0
            if os.path.exists(self.seed_tasks_file):
                with open(self.seed_tasks_file, 'r', encoding='utf-8') as f:
                    seed_count = sum(1 for line in f if line.strip())
            
            return {
                "processed_trajectories": len(self.processed_trajectories),
                "total_seed_tasks": seed_count,
                "files": {
                    "trajectories_file": self.trajectories_collection_file,
                    "seed_tasks_file": self.seed_tasks_file,
                    "processed_record": self.processed_trajectories_file
                },
                "monitoring_status": self.observer.is_alive() if hasattr(self, 'observer') else False
            }
            
        except Exception as e:
            logger.error(f"❌ 获取统计信息失败: {e}")
            return {}


# 全局监控器实例
_simple_monitor = None

def get_simple_monitor():
    """获取全局简化监控器实例"""
    global _simple_monitor
    if _simple_monitor is None:
        _simple_monitor = SimpleTrajectoryMonitor()
    return _simple_monitor

async def initialize_simple_monitor():
    """初始化并启动简化监控器"""
    monitor = get_simple_monitor()
    await monitor.initialize()
    await monitor.start_monitoring()
    return monitor

async def stop_simple_monitor():
    """停止简化监控器"""
    global _simple_monitor
    if _simple_monitor:
        await _simple_monitor.stop_monitoring()