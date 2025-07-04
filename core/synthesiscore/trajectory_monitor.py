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
        """文件修改事件 - 监控实际的轨迹文件格式"""
        if event.is_directory:
            return
            
        # 监控实际的轨迹文件：trajectories_YYYY-MM-DD.jsonl
        if (event.src_path.endswith('.jsonl') and 
            'trajectories_' in os.path.basename(event.src_path) and
            os.path.basename(event.src_path).startswith('trajectories_')):
            
            # 避免频繁触发，设置最小间隔
            current_time = time.time()
            last_time = self.last_processed.get(event.src_path, 0)
            
            if current_time - last_time > 5.0:  # 5秒间隔，避免处理过于频繁
                self.last_processed[event.src_path] = current_time
                logger.info(f"📁 检测到轨迹文件变化: {event.src_path}")
                logger.info(f"🚀 启动TaskCraft任务合成流程...")
                
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
            # 设置文件监控 - 递归监控包括grouped子目录
            self.observer.schedule(
                self.file_handler,
                path=self.trajectories_dir,
                recursive=True  # 启用递归监控，监控grouped/YYYY-MM-DD/子目录
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
        """处理现有轨迹 - 扫描grouped目录下的所有.jsonl文件"""
        logger.info("🔄 检查并处理现有轨迹...")
        
        # 扫描grouped目录下的所有轨迹文件
        grouped_dir = os.path.join(self.trajectories_dir, "grouped")
        if os.path.exists(grouped_dir):
            for date_dir in os.listdir(grouped_dir):
                date_path = os.path.join(grouped_dir, date_dir)
                if os.path.isdir(date_path):
                    for file_name in os.listdir(date_path):
                        if (file_name.startswith('trajectories_') and 
                            file_name.endswith('.jsonl')):
                            file_path = os.path.join(date_path, file_name)
                            logger.info(f"📁 发现现有轨迹文件: {file_path}")
                            await self.process_trajectory_changes(file_path)
        else:
            logger.info("📝 没有现有轨迹文件")
    
    async def process_trajectory_changes(self, file_path: str):
        """处理轨迹文件变化 - 使用SynthesisEngine进行LLM驱动的任务生成"""
        logger.info(f"🔄 处理轨迹文件: {file_path}")
        
        try:
            # 使用SynthesisEngine进行真正的TaskCraft算法处理
            from .synthesis_engine import SynthesisEngine
            from core.llm_client import LLMClient
            
            # 初始化LLM客户端
            llm_client = await self._initialize_llm_client()
            if not llm_client:
                logger.error("❌ LLM客户端初始化失败，无法进行智能任务生成")
                return
            
            # 创建 SynthesisEngine，使用专门的SynthesisTask目录
            engine = SynthesisEngine(
                llm_client=llm_client,
                storage_dir="output/SynthesisTask"
            )
            
            # 加载轨迹数据
            trajectories_data = await self._load_trajectories_data(file_path)
            if not trajectories_data:
                logger.warning("⚠️ 没有找到有效的轨迹数据")
                return
            
            # 执行TaskCraft算法进行任务合成
            logger.info(f"🤖 开始执行TaskCraft算法，处理 {len(trajectories_data)} 个轨迹")
            result = await engine.synthesize_from_trajectories(
                trajectories_data=trajectories_data,
                generate_depth_extensions=True,
                generate_width_extensions=True,
                max_atomic_tasks=10
            )
            
            if result and result.total_tasks_generated > 0:
                logger.info(f"✅ TaskCraft任务合成完成:")
                logger.info(f"  原子任务: {len(result.atomic_tasks)} 个")
                logger.info(f"  深度扩展: {len(result.depth_extended_tasks)} 个")
                logger.info(f"  宽度扩展: {len(result.width_extended_tasks)} 个")
                logger.info(f"  有效任务: {result.valid_tasks_count}/{result.total_tasks_generated}")
                
                # 更新已处理记录
                await self._update_processed_trajectories(result.source_trajectories)
                
                # 导出为传统的seed_tasks.jsonl格式（向后兼容）
                await self._export_to_seed_tasks(result)
            else:
                logger.warning("⚠️ 没有生成有效的任务")
                
        except Exception as e:
            logger.error(f"❌ 处理轨迹变化失败: {e}")
            import traceback
            traceback.print_exc()
    
    async def _initialize_llm_client(self):
        """初始化LLM客户端"""
        try:
            from core.llm_client import LLMClient
            from core.unified_tool_manager import UnifiedToolManager
            import yaml
            import os
            
            # 读取LLM配置
            config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "llm_config.yaml")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f)
                    
                    # 使用统一的LLM配置格式
                    default_provider = config_data.get('default_provider', 'gemini')
                    provider_config = config_data.get('llm_providers', {}).get(default_provider, {})
                    
                    llm_config = {
                        'provider': default_provider,
                        'model': provider_config.get('model', 'gemini-2.5-flash-lite-preview-06-17'),
                        'api_key': provider_config.get('api_key', ''),
                        'temperature': provider_config.get('temperature', 0.2),
                        'max_tokens': provider_config.get('max_tokens', 8192)
                    }
                    
                    if default_provider == 'gemini' and provider_config.get('api_base'):
                        llm_config['api_base'] = provider_config['api_base']
            else:
                logger.warning("⚠️ LLM配置文件不存在，使用默认配置")
                # 使用默认配置
                llm_config = {
                    'provider': 'gemini',
                    'model': 'gemini-2.5-flash-lite-preview-06-17',
                    'temperature': 0.2
                }
            
            # 创建tool_manager实例
            tool_manager = UnifiedToolManager()
            
            # 创建LLM客户端
            client = LLMClient(config=llm_config, tool_manager=tool_manager)
            logger.info("✅ LLM客户端初始化成功")
            return client
                
        except Exception as e:
            logger.error(f"❌ LLM客户端初始化失败: {e}")
            return None
    
    async def _load_trajectories_data(self, file_path: str) -> List[Dict]:
        """加载轨迹数据 - 支持JSONL格式"""
        try:
            trajectories = []
            
            # 检查是否是JSONL文件
            if file_path.endswith('.jsonl'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                trajectory = json.loads(line)
                                trajectories.append(trajectory)
                            except json.JSONDecodeError as e:
                                logger.warning(f"⚠️ 跳过无效的JSONL行: {e}")
                                continue
            else:
                # 处理JSON格式
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if isinstance(data, dict) and 'trajectories' in data:
                    trajectories = data['trajectories']
                elif isinstance(data, list):
                    trajectories = data
                else:
                    logger.error("❌ 轨迹文件格式无效")
                    return []
            
            # 过滤出未处理的轨迹
            new_trajectories = []
            for traj in trajectories:
                traj_id = traj.get('task_id', f"traj_{hash(str(traj))}")
                if traj_id not in self.processed_trajectories:
                    new_trajectories.append(traj)
            
            logger.info(f"📊 加载轨迹数据: 总计{len(trajectories)}个，新增{len(new_trajectories)}个")
            return new_trajectories
            
        except Exception as e:
            logger.error(f"❌ 加载轨迹数据失败: {e}")
            return []
    
    async def _update_processed_trajectories(self, trajectory_ids: List[str]):
        """更新已处理轨迹记录"""
        try:
            # 更新内存记录
            self.processed_trajectories.update(trajectory_ids)
            
            # 保存到文件
            data = {
                "processed": list(self.processed_trajectories),
                "last_updated": datetime.now().isoformat(),
                "total_count": len(self.processed_trajectories)
            }
            
            with open(self.processed_trajectories_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            logger.debug(f"📝 更新已处理轨迹记录: {len(trajectory_ids)} 个新增")
            
        except Exception as e:
            logger.error(f"❌ 更新已处理轨迹记录失败: {e}")
    
    async def _export_to_seed_tasks(self, synthesis_result):
        """导出任务为传统的seed_tasks.jsonl格式（向后兼容）"""
        try:
            from datetime import datetime
            
            # 合并所有任务
            all_tasks = []
            
            # 导出原子任务
            for task in synthesis_result.atomic_tasks:
                seed_task = {
                    "task_id": task.task_id,
                    "question": task.question,
                    "expected_answer": task.answer.answer,
                    "task_type": task.task_type.value,
                    "domain": task.domain,
                    "requires_tool": task.requires_tool,
                    "expected_tools": task.expected_tools,
                    "complexity": "atomic",
                    "source": "synthesis_engine",
                    "created_at": task.created_at.isoformat()
                }
                all_tasks.append(seed_task)
            
            # 导出深度扩展任务
            for task in synthesis_result.depth_extended_tasks:
                seed_task = {
                    "task_id": task.task_id,
                    "question": task.combined_question,
                    "expected_answer": task.combined_answer,
                    "task_type": task.base_task.task_type.value,
                    "domain": task.base_task.domain,
                    "requires_tool": True,
                    "expected_tools": task.base_task.expected_tools,
                    "complexity": "depth_extended",
                    "base_task_id": task.base_task.task_id,
                    "source": "synthesis_engine",
                    "created_at": task.created_at.isoformat()
                }
                all_tasks.append(seed_task)
            
            # 导出宽度扩展任务
            for task in synthesis_result.width_extended_tasks:
                seed_task = {
                    "task_id": task.task_id,
                    "question": task.merged_question,
                    "expected_answer": task.merged_answer,
                    "task_type": "composite",
                    "domain": "multi_domain",
                    "requires_tool": True,
                    "expected_tools": list(set(tool for comp_task in task.component_tasks for tool in comp_task.expected_tools)),
                    "complexity": "width_extended",
                    "component_task_ids": [comp_task.task_id for comp_task in task.component_tasks],
                    "source": "synthesis_engine",
                    "created_at": task.created_at.isoformat()
                }
                all_tasks.append(seed_task)
            
            # 追加写入seed_tasks.jsonl文件
            with open(self.seed_tasks_file, 'a', encoding='utf-8') as f:
                for task in all_tasks:
                    f.write(json.dumps(task, ensure_ascii=False) + '\n')
            
            logger.info(f"📄 导出 {len(all_tasks)} 个任务到 seed_tasks.jsonl")
            
        except Exception as e:
            logger.error(f"❌ 导出seed_tasks失败: {e}")
    
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