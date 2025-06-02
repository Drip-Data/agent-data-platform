#!/usr/bin/env python3
"""
Synthesis数据库预初始化脚本
确保在主服务启动前数据库已经完全准备好
"""

import os
import sqlite3
import logging
import time
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_synthesis_database():
    """预初始化synthesis数据库"""
    db_path = os.getenv("SYNTHESIS_DB", "/app/output/synthesis.db")
    max_retries = 10
    retry_delay = 2
    
    logger.info(f"Initializing synthesis database at {db_path}")
    
    for attempt in range(max_retries):
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            
            # 初始化数据库
            with sqlite3.connect(db_path, timeout=30) as conn:
                # 设置数据库参数
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA cache_size=10000")
                conn.execute("PRAGMA busy_timeout=30000")  # 30秒超时
                
                # 创建任务本质表
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS task_essences (
                        essence_id TEXT PRIMARY KEY,
                        task_type TEXT NOT NULL,
                        domain TEXT NOT NULL,
                        query TEXT NOT NULL,
                        complexity_level TEXT NOT NULL,
                        success_pattern TEXT NOT NULL,
                        extracted_at TEXT NOT NULL,
                        source_trajectory_id TEXT NOT NULL
                    )
                ''')
                
                # 创建生成任务表
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS generated_tasks (
                        task_id TEXT PRIMARY KEY,
                        source_essence_id TEXT NOT NULL,
                        task_spec TEXT NOT NULL,
                        generated_at TEXT NOT NULL,
                        executed BOOLEAN DEFAULT FALSE
                    )
                ''')
                
                # 创建索引以提高查询性能
                conn.execute('CREATE INDEX IF NOT EXISTS idx_task_type ON task_essences(task_type)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_domain ON task_essences(domain)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_extracted_at ON task_essences(extracted_at)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_source_essence ON generated_tasks(source_essence_id)')
                
                # 验证表结构
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                
                required_tables = ['task_essences', 'generated_tasks']
                for table in required_tables:
                    if table not in tables:
                        raise Exception(f"Required table {table} not found")
                
                # 测试读写权限
                test_id = f"test_init_{int(time.time())}"
                conn.execute('''
                    INSERT OR IGNORE INTO task_essences 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    test_id, "test", "test", "Database init test", 
                    "simple", "{}", datetime.now().isoformat(), "test"
                ))
                
                # 验证插入成功
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM task_essences WHERE essence_id = ?", 
                    (test_id,)
                )
                if cursor.fetchone()[0] == 0:
                    raise Exception("Failed to insert test record")
                
                # 清理测试数据
                conn.execute("DELETE FROM task_essences WHERE essence_id = ?", (test_id,))
                
                conn.commit()
                
            logger.info(f"Database initialization completed successfully (attempt {attempt + 1})")
            
            # 最终验证
            with sqlite3.connect(db_path, timeout=10) as conn:
                conn.execute("SELECT COUNT(*) FROM task_essences LIMIT 1")
                conn.execute("SELECT COUNT(*) FROM generated_tasks LIMIT 1")
            
            logger.info("Database verification passed")
            return True
            
        except Exception as e:
            logger.warning(f"Database initialization attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, 10)  # 递增延时，最大10秒
            else:
                logger.error(f"Failed to initialize database after {max_retries} attempts")
                return False
    
    return False


def cleanup_old_processed_files():
    """清理旧的处理状态文件"""
    processed_file = "/app/output/processed_trajectories.json"
    
    try:
        if os.path.exists(processed_file):
            # 备份现有文件
            backup_file = f"{processed_file}.backup.{int(time.time())}"
            os.rename(processed_file, backup_file)
            logger.info(f"Backed up existing processed file to {backup_file}")
        
        # 创建空的处理状态文件
        os.makedirs(os.path.dirname(processed_file), exist_ok=True)
        with open(processed_file, 'w') as f:
            f.write('{}')
        
        logger.info("Created fresh processed trajectories file")
        
    except Exception as e:
        logger.warning(f"Failed to setup processed file: {e}")


def verify_environment():
    """验证环境变量和目录"""
    required_dirs = [
        "/app/output",
        "/app/output/trajectories"
    ]
    
    for dir_path in required_dirs:
        os.makedirs(dir_path, exist_ok=True)
        logger.info(f"Ensured directory exists: {dir_path}")
    
    # 检查环境变量
    synthesis_enabled = os.getenv("SYNTHESIS_ENABLED", "false").lower() == "true"
    logger.info(f"Synthesis enabled: {synthesis_enabled}")
    
    if synthesis_enabled:
        required_env = ["REDIS_URL", "GEMINI_API_KEY"]
        missing_env = []
        
        for env_var in required_env:
            if not os.getenv(env_var):
                missing_env.append(env_var)
        
        if missing_env:
            logger.warning(f"Missing environment variables: {missing_env}")
        else:
            logger.info("All required environment variables are set")


if __name__ == "__main__":
    logger.info("Starting synthesis database pre-initialization...")
    
    try:
        # 验证环境
        verify_environment()
        
        # 清理旧文件
        cleanup_old_processed_files()
        
        # 初始化数据库
        if init_synthesis_database():
            logger.info("✅ Synthesis database pre-initialization completed successfully")
            exit(0)
        else:
            logger.error("❌ Synthesis database pre-initialization failed")
            exit(1)
            
    except Exception as e:
        logger.error(f"❌ Pre-initialization script failed: {e}")
        exit(1) 