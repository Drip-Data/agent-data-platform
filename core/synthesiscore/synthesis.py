#!/usr/bin/env python3
"""
简单任务合成器MVP - 集成到现有系统
复用现有LLM客户端，实现基础的轨迹反馈和任务生成
"""

import asyncio
import json
import logging
import os
import time
import sqlite3
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import redis.asyncio as redis
import threading
from pathlib import Path
from collections import defaultdict
import uuid

from ..interfaces import TaskSpec, TrajectoryResult, TaskType, ExecutionStep, ActionType, ErrorType
from ..llm_client import LLMClient

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

class SimpleSynthesizer:
    """简单任务合成器 - MVP版本"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.redis = redis.from_url(config["redis_url"])
        self.llm_client = LLMClient(config)
        self.db_path = config.get("synthesis_db", "/app/output/synthesis.db")
        self.enabled = config.get("synthesis_enabled", False)
        self.processed_json_path = "/app/output/processed_trajectories.json"
        self._processed_lock = threading.Lock()
        self._ensure_processed_json()
        
        # 初始化数据库
        self._init_database()
    
    def _init_database(self):
        """初始化SQLite数据库，带重试机制"""
        max_retries = 5
        retry_delay = 2  # 秒
        
        for attempt in range(max_retries):
            try:
                os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
                
                with sqlite3.connect(self.db_path) as conn:
                    # 设置数据库参数提高稳定性
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA synchronous=NORMAL")
                    conn.execute("PRAGMA cache_size=10000")
                    
                    # 创建任务本质表
                    conn.execute('''
                        CREATE TABLE IF NOT EXISTS task_essences (
                            essence_id TEXT PRIMARY KEY,
                            task_type TEXT,
                            domain TEXT,
                            query TEXT,
                            complexity_level TEXT,
                            success_pattern TEXT,
                            extracted_at TEXT,
                            source_trajectory_id TEXT
                        )
                    ''')
                    
                    # 创建生成任务表
                    conn.execute('''
                        CREATE TABLE IF NOT EXISTS generated_tasks (
                            task_id TEXT PRIMARY KEY,
                            source_essence_id TEXT,
                            task_spec TEXT,
                            generated_at TEXT,
                            executed BOOLEAN DEFAULT FALSE
                        )
                    ''')
                    
                    # 验证表是否创建成功
                    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = [row[0] for row in cursor.fetchall()]
                    
                    if 'task_essences' not in tables or 'generated_tasks' not in tables:
                        raise Exception("Failed to create required tables")
                    
                    # 测试写入权限
                    conn.execute("INSERT OR IGNORE INTO task_essences VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                               ("test_init", "test", "test", "test", "test", "{}", 
                                datetime.now().isoformat(), "test"))
                    conn.execute("DELETE FROM task_essences WHERE essence_id = ?", ("test_init",))
                    
                    conn.commit()
                    
                logger.info(f"Database initialized successfully at {self.db_path}")
                return
                
            except Exception as e:
                logger.warning(f"Database initialization attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                else:
                    raise Exception(f"Failed to initialize database after {max_retries} attempts: {e}")

    def _verify_database_ready(self) -> bool:
        """验证数据库是否准备就绪"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 检查表是否存在且可用
                conn.execute("SELECT COUNT(*) FROM task_essences LIMIT 1")
                conn.execute("SELECT COUNT(*) FROM generated_tasks LIMIT 1")
                return True
        except Exception as e:
            logger.error(f"Database verification failed: {e}")
            return False

    async def start(self):
        """启动合成器，等待触发指令而非自动处理"""
        if not self.enabled:
            logger.info("Task synthesis is disabled")
            return
            
        logger.info("Starting simple task synthesizer...")
        
        # 等待数据库初始化完成
        max_wait = 30  # 最大等待30秒
        wait_interval = 2
        elapsed = 0
        
        while elapsed < max_wait:
            if self._verify_database_ready():
                logger.info("Database verification passed, ready for manual synthesis")
                break
            
            logger.info(f"Waiting for database initialization... ({elapsed}s/{max_wait}s)")
            await asyncio.sleep(wait_interval)
            elapsed += wait_interval
        else:
            logger.error("Database initialization timeout, exiting")
            return
        
        # 启动指令监听器，而非自动处理
        await self._listen_for_synthesis_commands()

    async def _listen_for_synthesis_commands(self):
        """监听合成指令"""
        logger.info("🎯 Synthesis service ready - waiting for manual triggers")
        logger.info("Available trigger methods:")
        logger.info("1. Redis command: XADD synthesis:commands command trigger_synthesis")
        logger.info("2. Redis command: XADD synthesis:commands command process_trajectories")
        logger.info("3. Redis command: XADD synthesis:commands command process_specific trajectory_file.json")
        
        while True:
            try:
                # 监听synthesis:commands队列
                streams = {"synthesis:commands": "$"}
                result = await self.redis.xread(streams, count=1, block=5000)  # 5秒超时
                
                if result:
                    for stream_name, messages in result:
                        for message_id, fields in messages:
                            await self._handle_synthesis_command(fields)
                            # 确认处理完成
                            await self.redis.xdel("synthesis:commands", message_id)
                
            except Exception as e:
                logger.error(f"Error listening for synthesis commands: {e}")
                await asyncio.sleep(10)

    async def _handle_synthesis_command(self, command_fields: dict):
        """处理合成指令"""
        try:
            command = command_fields.get(b'command', b'').decode('utf-8')
            logger.info(f"📨 Received synthesis command: {command}")
            
            if command == "trigger_synthesis":
                # 触发完整的轨迹处理
                await self._process_all_trajectories_once()
                
            elif command == "process_trajectories":
                # 处理所有未处理的轨迹
                await self._process_unprocessed_trajectories()
                
            elif command.startswith("process_specific"):
                # 处理指定的轨迹文件
                parts = command.split(" ", 1)
                if len(parts) > 1:
                    filename = parts[1]
                    await self._process_specific_trajectory(filename)
                    
            elif command == "generate_tasks":
                # 手动生成任务
                count = int(command_fields.get(b'count', b'3').decode('utf-8'))
                tasks = await self.generate_tasks_manually(count)
                logger.info(f"Generated {len(tasks)} tasks manually")
                
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
            trajectories_dir = "/app/output/trajectories"
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
            trajectories_dir = "/app/output/trajectories"
            if not os.path.exists(trajectories_dir):
                logger.warning("Trajectories directory not found")
                return
            
            processed_count = 0
            
            # 获取所有未处理的轨迹
            for filename in os.listdir(trajectories_dir):
                if filename.endswith('.json') and not self._is_trajectory_processed(filename):
                    trajectory_path = os.path.join(trajectories_dir, filename)
                    await self._process_trajectory_file(trajectory_path)
                    self._mark_trajectory_processed(filename)
                    processed_count += 1
                    logger.info(f"✅ Processed new trajectory: {filename}")
            
            logger.info(f"🎯 Unprocessed trajectories completed: {processed_count} new trajectories processed")
            
        except Exception as e:
            logger.error(f"Error processing unprocessed trajectories: {e}")

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
            # 统计数据库中的本质数量
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM task_essences")
                essence_count = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT COUNT(*) FROM generated_tasks")
                generated_count = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT task_type, COUNT(*) FROM task_essences GROUP BY task_type")
                type_distribution = dict(cursor.fetchall())
            
            # 统计处理的轨迹数量
            processed = self._load_processed()
            processed_count = len(processed)
            
            # 统计轨迹目录中的文件数量
            trajectories_dir = "/app/output/trajectories"
            total_trajectories = 0
            if os.path.exists(trajectories_dir):
                total_trajectories = len([f for f in os.listdir(trajectories_dir) if f.endswith('.json')])
            
            status_info = {
                "synthesis_enabled": self.enabled,
                "database_ready": self._verify_database_ready(),
                "total_essences": essence_count,
                "generated_tasks": generated_count,
                "essence_distribution": type_distribution,
                "processed_trajectories": processed_count,
                "total_trajectory_files": total_trajectories,
                "unprocessed_count": total_trajectories - processed_count
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
    
    async def _process_trajectory_file(self, trajectory_path: str):
        """处理单个轨迹文件"""
        try:
            with open(trajectory_path, 'r', encoding='utf-8') as f:
                trajectory_data = json.load(f)
            
            # 如果是轨迹列表，处理每一个轨迹
            if isinstance(trajectory_data, list):
                logger.info(f"Processing trajectory collection with {len(trajectory_data)} trajectories")
                for i, single_trajectory in enumerate(trajectory_data):
                    if i >= 5:  # 限制处理前5个轨迹
                        break
                    try:
                        trajectory = self._convert_trajectory_format(single_trajectory)
                        if trajectory and trajectory.success:
                            essence = await self._extract_essence(trajectory)
                            if essence:
                                self._store_essence(essence)
                                logger.info(f"Extracted essence from trajectory {trajectory.task_id}")
                    except Exception as e:
                        logger.error(f"Error processing trajectory {i}: {e}")
            else:
                # 单个轨迹对象
                trajectory = self._convert_trajectory_format(trajectory_data)
                if trajectory and trajectory.success:
                    essence = await self._extract_essence(trajectory)
                    if essence:
                        self._store_essence(essence)
                        logger.info(f"Extracted essence from trajectory {trajectory.task_id}")
        
        except Exception as e:
            logger.error(f"Error processing trajectory file {trajectory_path}: {e}")
    
    def _convert_trajectory_format(self, data: Dict) -> Optional[TrajectoryResult]:
        """将轨迹数据转换为TrajectoryResult格式"""
        try:
            # 转换steps格式
            converted_steps = []
            for step_data in data.get('steps', []):
                # 映射字段名称
                converted_step = ExecutionStep(
                    step_id=step_data.get('step_id', 0),
                    action_type=ActionType(step_data.get('action_type', 'code_generation')),
                    action_params=step_data.get('tool_input', {}),
                    observation=step_data.get('tool_output', ''),
                    success=step_data.get('success', True),
                    thinking=step_data.get('thinking'),
                    execution_code=step_data.get('execution_code'),
                    error_type=ErrorType(step_data['error_type']) if step_data.get('error_type') else None,
                    error_message=step_data.get('error_message'),
                    timestamp=step_data.get('timestamp', time.time()),
                    duration=step_data.get('duration', 0.0)
                )
                converted_steps.append(converted_step)
            
            # 创建TrajectoryResult对象
            return TrajectoryResult(
                task_id=data.get('task_id', str(uuid.uuid4())),
                task_name=data.get('task_name', data.get('task_id', 'unknown')),
                task_description=data.get('task_description', ''),
                runtime_id=data.get('runtime_id', 'unknown'),
                success=data.get('success', False),
                steps=converted_steps,
                final_result=data.get('final_result', ''),
                error_type=ErrorType(data['error_type']) if data.get('error_type') else None,
                error_message=data.get('error_message'),
                total_duration=data.get('total_duration', 0.0),
                metadata=data.get('metadata', {}),
                created_at=data.get('created_at', time.time())
            )
            
        except Exception as e:
            logger.error(f"Error converting trajectory format: {e}")
            return None
    
    async def _extract_essence(self, trajectory: TrajectoryResult) -> Optional[TaskEssence]:
        """使用LLM提取轨迹本质"""
        try:
            # 构建分析提示
            prompt = self._build_extraction_prompt(trajectory)
            
            # 调用LLM
            response = await self.llm_client._call_api(prompt)
            
            # 解析响应
            return self._parse_extraction_response(response, trajectory)
            
        except Exception as e:
            logger.error(f"Error extracting essence: {e}")
            return None
    
    def _build_extraction_prompt(self, trajectory: TrajectoryResult) -> str:
        """构建本质提取提示"""
        # 简化轨迹信息
        steps_summary = []
        for i, step in enumerate(trajectory.steps[:3]):  # 只取前3步
            steps_summary.append(f"步骤{i+1}: {step.action_type} - {step.observation[:100]}...")
        
        return f"""分析以下任务执行轨迹，提取任务本质信息：

任务ID: {trajectory.task_id}
执行成功: {trajectory.success}
总耗时: {trajectory.total_duration:.1f}秒
最终结果: {trajectory.final_result[:200]}...

执行步骤:
{chr(10).join(steps_summary)}

请提取：
1. task_type: 任务类型 (code/web/reasoning)
2. domain: 领域 (algorithm/data_processing/web_automation/search等)
3. query: 核心任务描述（20字以内）
4. complexity: 复杂度 (simple/medium/complex)

返回JSON格式：
{{"task_type": "...", "domain": "...", "query": "...", "complexity": "..."}}"""
    
    def _parse_extraction_response(self, response: str, trajectory: TrajectoryResult) -> Optional[TaskEssence]:
        """解析LLM响应"""
        try:
            # 提取JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                
                return TaskEssence(
                    essence_id=f"essence_{int(time.time())}_{trajectory.task_id}",
                    task_type=parsed.get("task_type", "code"),
                    domain=parsed.get("domain", "general"),
                    query=parsed.get("query", "基础任务"),
                    complexity_level=parsed.get("complexity", "medium"),
                    success_pattern={"duration": trajectory.total_duration},
                    extracted_at=datetime.now().isoformat(),
                    source_trajectory_id=trajectory.task_id
                )
        except Exception as e:
            logger.error(f"Error parsing extraction response: {e}")
        
        return None
    
    def _store_essence(self, essence: TaskEssence):
        """存储任务本质到数据库，带重试机制"""
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                with sqlite3.connect(self.db_path, timeout=10) as conn:
                    # 确保数据库连接正常
                    conn.execute("PRAGMA journal_mode=WAL")
                    
                    conn.execute('''
                        INSERT OR REPLACE INTO task_essences 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        essence.essence_id,
                        essence.task_type,
                        essence.domain,
                        essence.query,
                        essence.complexity_level,
                        json.dumps(essence.success_pattern),
                        essence.extracted_at,
                        essence.source_trajectory_id
                    ))
                    
                    conn.commit()
                    logger.info(f"Successfully stored essence {essence.essence_id}")
                    return
                    
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower() or "no such table" in str(e).lower():
                    logger.warning(f"Database operation failed (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        # 尝试重新初始化数据库
                        if "no such table" in str(e).lower():
                            try:
                                self._init_database()
                            except Exception as init_e:
                                logger.error(f"Failed to re-initialize database: {init_e}")
                        continue
                else:
                    logger.error(f"Database error: {e}")
                    break
            except Exception as e:
                logger.error(f"Unexpected error storing essence: {e}")
                break
        
        logger.error(f"Failed to store essence {essence.essence_id} after {max_retries} attempts")
    
    async def generate_tasks_manually(self, count: int = 3) -> List[TaskSpec]:
        """手动生成指定数量的任务"""
        generated_tasks = []
        
        try:
            # 获取种子数据
            essences = self._get_random_essences(count)
            if not essences:
                logger.warning("No task essences available for generation")
                return generated_tasks
            
            # 为每个essence生成变异任务
            for essence in essences:
                new_task = await self._generate_task_from_essence(essence)
                if new_task:
                    await self._publish_task(new_task)
                    self._record_generated_task(new_task, essence.essence_id)
                    generated_tasks.append(new_task)
                    logger.info(f"Generated new task: {new_task.task_id}")
            
            return generated_tasks
            
        except Exception as e:
            logger.error(f"Error generating manual tasks: {e}")
            return generated_tasks

    async def generate_task_from_specific_essence(self, essence_id: str) -> Optional[TaskSpec]:
        """基于指定的任务本质生成新任务"""
        try:
            # 从数据库获取指定的本质
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT * FROM task_essences WHERE essence_id = ?
                ''', (essence_id,))
                
                row = cursor.fetchone()
                if not row:
                    logger.warning(f"Essence {essence_id} not found")
                    return None
                
                essence = TaskEssence(
                    essence_id=row[0],
                    task_type=row[1],
                    domain=row[2],
                    query=row[3],
                    complexity_level=row[4],
                    success_pattern=json.loads(row[5]),
                    extracted_at=row[6],
                    source_trajectory_id=row[7]
                )
            
            # 生成任务
            new_task = await self._generate_task_from_essence(essence)
            if new_task:
                await self._publish_task(new_task)
                self._record_generated_task(new_task, essence.essence_id)
                logger.info(f"Generated task {new_task.task_id} from essence {essence_id}")
                return new_task
            
        except Exception as e:
            logger.error(f"Error generating task from essence {essence_id}: {e}")
        
        return None
    
    def _get_random_essences(self, count: int) -> List[TaskEssence]:
        """获取随机的种子本质，带错误处理"""
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                with sqlite3.connect(self.db_path, timeout=10) as conn:
                    cursor = conn.execute('''
                        SELECT * FROM task_essences 
                        ORDER BY RANDOM() 
                        LIMIT ?
                    ''', (count,))
                    
                    essences = []
                    for row in cursor.fetchall():
                        essences.append(TaskEssence(
                            essence_id=row[0],
                            task_type=row[1],
                            domain=row[2],
                            query=row[3],
                            complexity_level=row[4],
                            success_pattern=json.loads(row[5]),
                            extracted_at=row[6],
                            source_trajectory_id=row[7]
                        ))
                    
                    return essences
                    
            except sqlite3.OperationalError as e:
                logger.warning(f"Database read failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    logger.error(f"Failed to read essences after {max_retries} attempts")
                    return []
            except Exception as e:
                logger.error(f"Unexpected error reading essences: {e}")
                return []
        
        return []
    
    async def _generate_task_from_essence(self, essence: TaskEssence) -> Optional[TaskSpec]:
        """基于本质生成新任务"""
        try:
            # 构建变异提示
            prompt = f"""基于以下任务本质，生成一个相似但不同的新任务：

原任务类型: {essence.task_type}
原任务领域: {essence.domain}
原任务描述: {essence.query}
复杂度: {essence.complexity_level}

请生成一个新的类似任务，要求：
1. 保持相同的任务类型和领域
2. 适当调整参数或场景
3. 保持相似的复杂度

返回JSON格式：
{{"description": "新任务描述", "expected_tools": ["工具列表"]}}"""
            
            response = await self.llm_client._call_api(prompt)
            
            # 解析响应
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                
                # 构建TaskSpec
                task_id = f"synth_{int(time.time())}_{essence.essence_id.split('_')[-1]}"
                
                return TaskSpec(
                    task_id=task_id,
                    task_type=TaskType(essence.task_type),
                    description=parsed.get("description", essence.query),
                    expected_tools=parsed.get("expected_tools", ["python_executor"]),
                    constraints={},
                    max_steps=5,
                    priority=1
                )
        
        except Exception as e:
            logger.error(f"Error generating task from essence: {e}")
        
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
    
    def _record_generated_task(self, task: TaskSpec, essence_id: str):
        """记录生成的任务，带重试机制"""
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                with sqlite3.connect(self.db_path, timeout=10) as conn:
                    conn.execute('''
                        INSERT OR REPLACE INTO generated_tasks 
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        task.task_id,
                        essence_id,
                        task.json(),
                        datetime.now().isoformat(),
                        False
                    ))
                    conn.commit()
                    logger.info(f"Successfully recorded generated task {task.task_id}")
                    return
                    
            except sqlite3.OperationalError as e:
                logger.warning(f"Database write failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    logger.error(f"Failed to record task {task.task_id} after {max_retries} attempts")
            except Exception as e:
                logger.error(f"Unexpected error recording task {task.task_id}: {e}")
                break
    
    def _ensure_processed_json(self):
        """确保集中标记文件存在"""
        if not os.path.exists(self.processed_json_path):
            with open(self.processed_json_path, 'w', encoding='utf-8') as f:
                json.dump({}, f)
    
    def _load_processed(self) -> dict:
        with self._processed_lock:
            try:
                with open(self.processed_json_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
    
    def _save_processed(self, processed: dict):
        with self._processed_lock:
            with open(self.processed_json_path, 'w', encoding='utf-8') as f:
                json.dump(processed, f, ensure_ascii=False, indent=2)
    
    def _is_trajectory_processed(self, filename: str) -> bool:
        """检查轨迹是否已处理（集中管理）"""
        processed = self._load_processed()
        return filename in processed
    
    def _mark_trajectory_processed(self, filename: str):
        """标记轨迹已处理（集中管理）"""
        processed = self._load_processed()
        processed[filename] = int(time.time())
        self._save_processed(processed)

async def main():
    """任务合成器主程序"""
    config = {
        "redis_url": os.getenv("REDIS_URL", "redis://redis:6379"),
        "synthesis_db": os.getenv("SYNTHESIS_DB", "/app/output/synthesis.db"),
        "synthesis_enabled": os.getenv("SYNTHESIS_ENABLED", "false").lower() == "true",
        "vllm_url": os.getenv("VLLM_URL", "http://vllm:8000")
    }
    
    synthesizer = SimpleSynthesizer(config)
    
    try:
        if config["synthesis_enabled"]:
            logger.info("Starting task synthesis service...")
            await synthesizer.start()
        else:
            logger.info("Task synthesis is disabled, service will wait...")
            # 保持服务运行，但不执行合成逻辑
            while True:
                await asyncio.sleep(60)
                logger.info("Synthesis service waiting (disabled)...")
    except KeyboardInterrupt:
        logger.info("Synthesis service interrupted")
    finally:
        try:
            await synthesizer.redis.aclose()  # 使用aclose()替代close()
        except Exception as e:
            logger.warning(f"Error closing Redis connection: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main()) 