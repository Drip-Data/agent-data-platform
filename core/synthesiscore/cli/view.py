#!/usr/bin/env python3
"""
Synthesis数据库查看工具命令行入口
"""

import sys
from ..view_synthesis_db import view_essences, view_generated_tasks, view_statistics

def main():
    """命令行入口点"""
    import argparse
    
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
            
        return 0
            
    except FileNotFoundError:
        print(f"❌ 数据库文件不存在: {args.db}")
        return 1
    except Exception as e:
        print(f"❌ 查看数据库时出错: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 