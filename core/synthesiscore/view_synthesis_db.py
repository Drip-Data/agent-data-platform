#!/usr/bin/env python3
"""
查看synthesis数据库内容的工具脚本
"""

import sqlite3
import json
import argparse
from datetime import datetime
from typing import Dict, Any


def format_timestamp(ts_str: str) -> str:
    """格式化时间戳"""
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return ts_str


def view_essences(db_path: str, limit: int = None):
    """查看任务本质"""
    print("📋 任务本质 (Task Essences)")
    print("=" * 80)
    
    with sqlite3.connect(db_path) as conn:
        query = """
        SELECT essence_id, task_type, domain, query, complexity_level, 
               extracted_at, source_trajectory_id 
        FROM task_essences 
        ORDER BY extracted_at DESC
        """
        if limit:
            query += f" LIMIT {limit}"
            
        cursor = conn.execute(query)
        
        for i, row in enumerate(cursor.fetchall(), 1):
            essence_id, task_type, domain, query, complexity, extracted_at, source_id = row
            
            print(f"{i:2d}. {essence_id}")
            print(f"    类型: {task_type}")
            print(f"    领域: {domain}")
            print(f"    描述: {query}")
            print(f"    复杂度: {complexity}")
            print(f"    提取时间: {format_timestamp(extracted_at)}")
            print(f"    源轨迹: {source_id}")
            print()


def view_generated_tasks(db_path: str, limit: int = None):
    """查看生成的任务"""
    print("🚀 生成的任务 (Generated Tasks)")
    print("=" * 80)
    
    with sqlite3.connect(db_path) as conn:
        query = """
        SELECT task_id, source_essence_id, task_spec, generated_at, executed
        FROM generated_tasks 
        ORDER BY generated_at DESC
        """
        if limit:
            query += f" LIMIT {limit}"
            
        cursor = conn.execute(query)
        
        for i, row in enumerate(cursor.fetchall(), 1):
            task_id, source_essence_id, task_spec, generated_at, executed = row
            
            try:
                spec = json.loads(task_spec)
                description = spec.get('description', 'N/A')
                task_type = spec.get('task_type', 'N/A')
                tools = spec.get('expected_tools', [])
            except:
                description = "解析失败"
                task_type = "N/A"
                tools = []
            
            print(f"{i:2d}. {task_id}")
            print(f"    类型: {task_type}")
            print(f"    描述: {description}")
            print(f"    工具: {', '.join(tools) if tools else '无'}")
            print(f"    源本质: {source_essence_id}")
            print(f"    生成时间: {format_timestamp(generated_at)}")
            print(f"    已执行: {'是' if executed else '否'}")
            print()


def view_statistics(db_path: str):
    """查看统计信息"""
    print("📊 统计信息 (Statistics)")
    print("=" * 80)
    
    with sqlite3.connect(db_path) as conn:
        # 本质统计
        cursor = conn.execute("SELECT COUNT(*) FROM task_essences")
        total_essences = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT task_type, COUNT(*) FROM task_essences GROUP BY task_type")
        essence_by_type = dict(cursor.fetchall())
        
        cursor = conn.execute("SELECT domain, COUNT(*) FROM task_essences GROUP BY domain")
        essence_by_domain = dict(cursor.fetchall())
        
        # 生成任务统计
        cursor = conn.execute("SELECT COUNT(*) FROM generated_tasks")
        total_generated = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM generated_tasks WHERE executed = 1")
        executed_tasks = cursor.fetchone()[0]
        
        print(f"总本质数: {total_essences}")
        print(f"总生成任务数: {total_generated}")
        print(f"已执行任务数: {executed_tasks}")
        print()
        
        print("按类型分布:")
        for task_type, count in essence_by_type.items():
            print(f"  {task_type}: {count}")
        print()
        
        print("按领域分布:")
        for domain, count in essence_by_domain.items():
            print(f"  {domain}: {count}")
        print()


def main():
    parser = argparse.ArgumentParser(description="查看synthesis数据库内容")
    parser.add_argument("--db", default="output/synthesis.db", help="数据库路径")
    parser.add_argument("--essences", action="store_true", help="显示任务本质")
    parser.add_argument("--tasks", action="store_true", help="显示生成任务")
    parser.add_argument("--stats", action="store_true", help="显示统计信息")
    parser.add_argument("--limit", type=int, help="限制显示数量")
    parser.add_argument("--all", action="store_true", help="显示所有信息")
    
    args = parser.parse_args()
    
    if not any([args.essences, args.tasks, args.stats, args.all]):
        args.all = True
    
    try:
        if args.all or args.stats:
            view_statistics(args.db)
            
        if args.all or args.essences:
            view_essences(args.db, args.limit)
            
        if args.all or args.tasks:
            view_generated_tasks(args.db, args.limit)
            
    except FileNotFoundError:
        print(f"❌ 数据库文件不存在: {args.db}")
    except Exception as e:
        print(f"❌ 查看数据库时出错: {e}")


if __name__ == "__main__":
    main() 