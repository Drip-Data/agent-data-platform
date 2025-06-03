#!/usr/bin/env python3
"""
Synthesis触发工具命令行入口
"""

import sys
import asyncio
from ..trigger_synthesis import SynthesisTrigger

def main():
    """命令行入口点"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Synthesis触发器 - 手动控制任务合成过程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 查看状态
  python -m core.synthesiscore.cli.trigger status
  
  # 处理所有轨迹
  python -m core.synthesiscore.cli.trigger full
  
  # 只处理新轨迹
  python -m core.synthesiscore.cli.trigger new
  
  # 处理指定轨迹
  python -m core.synthesiscore.cli.trigger specific trajectory_20241220_001.json
  
  # 生成任务
  python -m core.synthesiscore.cli.trigger generate --count 5
  
  # 列出轨迹文件
  python -m core.synthesiscore.cli.trigger list
        """
    )
    
    parser.add_argument(
        "action",
        choices=["status", "full", "new", "specific", "generate", "list"],
        help="要执行的操作"
    )
    
    parser.add_argument(
        "target",
        nargs="?",
        help="目标文件名（用于specific操作）"
    )
    
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="生成任务的数量（用于generate操作）"
    )
    
    parser.add_argument(
        "--redis-url",
        default=None,
        help="Redis连接URL（默认从环境变量REDIS_URL读取）"
    )
    
    args = parser.parse_args()
    
    try:
        async def run():
            async with SynthesisTrigger(args.redis_url) as trigger:
                if args.action == "status":
                    await trigger.get_status()
                    
                elif args.action == "full":
                    await trigger.trigger_full_synthesis()
                    
                elif args.action == "new":
                    await trigger.process_new_trajectories()
                    
                elif args.action == "specific":
                    if not args.target:
                        print("❌ Specific action requires a target filename")
                        return 1
                    await trigger.process_specific_trajectory(args.target)
                    
                elif args.action == "generate":
                    await trigger.generate_tasks(args.count)
                    
                elif args.action == "list":
                    await trigger.list_trajectories()
                    
            print("🎉 Operation completed successfully")
            return 0
            
        return asyncio.run(run())
        
    except Exception as e:
        print(f"❌ Operation failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 