#!/usr/bin/env python3
"""
Synthesis任务生成工具命令行入口
"""

import sys
import asyncio
from ..generate_tasks import generate_tasks

def main():
    """命令行入口点"""
    import argparse
    
    parser = argparse.ArgumentParser(description="生成新的合成任务")
    parser.add_argument("--count", type=int, default=3, help="生成任务的数量")
    parser.add_argument("--db", default="output/synthesis.db", help="数据库路径")
    parser.add_argument("--redis-url", default=None, help="Redis连接URL")
    
    args = parser.parse_args()
    
    try:
        async def run():
            tasks = await generate_tasks(
                count=args.count,
                db_path=args.db,
                redis_url=args.redis_url
            )
            print(f"✅ 成功生成 {len(tasks)} 个任务")
            return 0
            
        return asyncio.run(run())
        
    except Exception as e:
        print(f"❌ 任务生成失败: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 