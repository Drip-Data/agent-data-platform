#!/usr/bin/env python3
"""
用户控制的任务生成工具
支持查看任务本质、手动生成任务、基于特定本质生成等功能
"""

import os
import sys
import asyncio
import sqlite3
import json
import argparse
from datetime import datetime

# 添加core模块到路径
sys.path.append('/app')
from .synthesis import SimpleSynthesizer, TaskEssence
from ..interfaces import TaskSpec, TaskType

class TaskGenerator:
    def __init__(self):
        self.config = {
            "redis_url": os.getenv("REDIS_URL", "redis://redis:6379"),
            "synthesis_db": "/app/output/synthesis.db",
            "synthesis_enabled": True,
            "vllm_url": os.getenv("VLLM_URL", "http://vllm:8000")
        }
        self.synthesizer = SimpleSynthesizer(self.config)
    
    def list_essences(self, domain_filter=None):
        """列出所有任务本质"""
        print("\n📚 数据库中的任务本质:")
        print("=" * 80)
        
        with sqlite3.connect(self.config["synthesis_db"]) as conn:
            if domain_filter:
                cursor = conn.execute('''
                    SELECT essence_id, task_type, domain, query, complexity_level, source_trajectory_id 
                    FROM task_essences WHERE domain = ? ORDER BY extracted_at DESC
                ''', (domain_filter,))
            else:
                cursor = conn.execute('''
                    SELECT essence_id, task_type, domain, query, complexity_level, source_trajectory_id 
                    FROM task_essences ORDER BY domain, extracted_at DESC
                ''')
            
            current_domain = None
            for row in cursor.fetchall():
                essence_id, task_type, domain, query, complexity, source = row
                
                if domain != current_domain:
                    if current_domain is not None:
                        print()
                    print(f"\n🔸 {domain.upper()} 领域:")
                    current_domain = domain
                
                print(f"  📋 {essence_id}")
                print(f"     查询: {query}")
                print(f"     类型: {task_type} | 复杂度: {complexity} | 源: {source}")
    
    def show_statistics(self):
        """显示统计信息"""
        print("\n📊 任务合成器统计:")
        print("=" * 50)
        
        with sqlite3.connect(self.config["synthesis_db"]) as conn:
            # 任务本质统计
            cursor = conn.execute('''
                SELECT domain, COUNT(*) as count 
                FROM task_essences 
                GROUP BY domain 
                ORDER BY count DESC
            ''')
            
            print("\n🧠 任务本质分布:")
            for domain, count in cursor.fetchall():
                print(f"  {domain}: {count} 个")
            
            # 生成任务统计
            cursor = conn.execute('SELECT COUNT(*) FROM generated_tasks')
            total_generated = cursor.fetchone()[0]
            
            cursor = conn.execute('''
                SELECT DATE(generated_at) as date, COUNT(*) as count 
                FROM generated_tasks 
                GROUP BY DATE(generated_at) 
                ORDER BY date DESC 
                LIMIT 5
            ''')
            
            print(f"\n🚀 已生成任务: {total_generated} 个")
            print("最近生成记录:")
            for date, count in cursor.fetchall():
                print(f"  {date}: {count} 个")
    
    async def generate_random_tasks(self, count=3):
        """随机生成指定数量的任务"""
        print(f"\n🎲 开始随机生成 {count} 个任务...")
        
        try:
            generated_tasks = await self.synthesizer.generate_tasks_manually(count)
            
            if generated_tasks:
                print(f"\n✅ 成功生成 {len(generated_tasks)} 个任务:")
                for task in generated_tasks:
                    print(f"  🆔 {task.task_id}")
                    print(f"     描述: {task.description}")
                    print(f"     类型: {task.task_type}")
                    print()
                
                await self._show_queue_status()
            else:
                print("❌ 没有生成任何任务")
                
        except Exception as e:
            print(f"❌ 生成任务时出错: {e}")
        finally:
            await self.synthesizer.redis.aclose()
    
    async def generate_from_essence(self, essence_id):
        """基于特定本质生成任务"""
        print(f"\n🎯 基于本质 {essence_id} 生成任务...")
        
        try:
            # 先显示本质信息
            with sqlite3.connect(self.config["synthesis_db"]) as conn:
                cursor = conn.execute('''
                    SELECT domain, query, complexity_level 
                    FROM task_essences WHERE essence_id = ?
                ''', (essence_id,))
                
                row = cursor.fetchone()
                if not row:
                    print(f"❌ 找不到本质 {essence_id}")
                    return
                
                domain, query, complexity = row
                print(f"📋 本质信息: {domain} - {query} ({complexity})")
            
            # 生成任务
            new_task = await self.synthesizer.generate_task_from_specific_essence(essence_id)
            
            if new_task:
                print(f"\n✅ 成功生成任务:")
                print(f"  🆔 {new_task.task_id}")
                print(f"     描述: {new_task.description}")
                print(f"     类型: {new_task.task_type}")
                
                await self._show_queue_status()
            else:
                print("❌ 任务生成失败")
                
        except Exception as e:
            print(f"❌ 生成任务时出错: {e}")
        finally:
            await self.synthesizer.redis.aclose()
    
    async def generate_math_task(self):
        """专门生成数学计算任务"""
        print("\n🧮 生成数学计算任务...")
        
        # 查找数学相关的本质
        with sqlite3.connect(self.config["synthesis_db"]) as conn:
            cursor = conn.execute('''
                SELECT essence_id FROM task_essences 
                WHERE domain IN ('mathematics', 'algorithm') 
                AND (query LIKE '%计算%' OR query LIKE '%数学%' OR query LIKE '%算%')
                ORDER BY RANDOM() LIMIT 1
            ''')
            
            row = cursor.fetchone()
            if row:
                essence_id = row[0]
                await self.generate_from_essence(essence_id)
            else:
                print("❌ 找不到数学相关的任务本质")
    
    async def _show_queue_status(self):
        """显示队列状态"""
        print("\n📊 当前队列状态:")
        try:
            import redis.asyncio as redis
            redis_client = redis.from_url(self.config["redis_url"])
            
            for queue in ["tasks:code", "tasks:web", "tasks:reasoning"]:
                length = await redis_client.xlen(queue)
                print(f"  {queue}: {length} 个任务")
            
            await redis_client.aclose()
        except Exception as e:
            print(f"无法检查队列状态: {e}")

async def generate_tasks(count: int = 3, db_path: str = "/app/output/synthesis.db", redis_url: str = None):
    """
    生成任务的便捷包装函数
    
    Args:
        count: 生成任务的数量
        db_path: 数据库路径
        redis_url: Redis连接URL
    
    Returns:
        List[TaskSpec]: 生成的任务列表
    """
    from .synthesis import SimpleSynthesizer
    
    config = {
        "redis_url": redis_url or os.getenv("REDIS_URL", "redis://redis:6379"),
        "synthesis_db": db_path,
        "synthesis_enabled": True,
        "vllm_url": os.getenv("VLLM_URL", "http://vllm:8000")
    }
    
    synthesizer = SimpleSynthesizer(config)
    try:
        tasks = await synthesizer.generate_tasks_manually(count)
        return tasks
    finally:
        if hasattr(synthesizer, 'redis'):
            await synthesizer.redis.aclose()

def main():
    parser = argparse.ArgumentParser(description="用户控制的任务生成工具")
    parser.add_argument("action", choices=["list", "stats", "generate", "essence", "math"], 
                       help="操作类型")
    parser.add_argument("--count", type=int, default=3, help="生成任务数量")
    parser.add_argument("--domain", type=str, help="过滤特定领域")
    parser.add_argument("--essence-id", type=str, help="指定本质ID")
    
    args = parser.parse_args()
    
    generator = TaskGenerator()
    
    print("🔬 任务生成工具")
    print("=" * 60)
    
    if args.action == "list":
        generator.list_essences(args.domain)
    
    elif args.action == "stats":
        generator.show_statistics()
    
    elif args.action == "generate":
        asyncio.run(generator.generate_random_tasks(args.count))
    
    elif args.action == "essence":
        if not args.essence_id:
            print("❌ 请使用 --essence-id 指定本质ID")
            return
        asyncio.run(generator.generate_from_essence(args.essence_id))
    
    elif args.action == "math":
        asyncio.run(generator.generate_math_task())

if __name__ == "__main__":
    main() 