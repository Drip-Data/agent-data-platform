#!/usr/bin/env python3
"""
Synthesis触发器脚本
用户友好的命令行工具，用于触发各种synthesis操作
"""

import asyncio
import argparse
import json
import logging
import os
import time
import redis.asyncio as redis

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SynthesisTrigger:
    """Synthesis触发器"""
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis_client = None
    
    async def __aenter__(self):
        self.redis_client = redis.from_url(self.redis_url)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.redis_client:
            await self.redis_client.aclose()
    
    async def send_command(self, command: str, **kwargs):
        """发送命令到synthesis服务"""
        try:
            command_data = {"command": command}
            command_data.update(kwargs)
            
            await self.redis_client.xadd("synthesis:commands", command_data)
            logger.info(f"✅ Command sent: {command}")
            
            # 等待一段时间让命令处理完成
            if command != "status":
                logger.info("⏳ Waiting for command to complete...")
                await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"❌ Failed to send command: {e}")
            raise
    
    async def trigger_full_synthesis(self):
        """触发完整的轨迹合成"""
        logger.info("🚀 Triggering full trajectory synthesis...")
        await self.send_command("trigger_synthesis")
        logger.info("✅ Full synthesis triggered")
    
    async def process_new_trajectories(self):
        """只处理新的（未处理的）轨迹"""
        logger.info("🔄 Triggering processing of new trajectories only...")
        await self.send_command("process_trajectories")
        logger.info("✅ New trajectory processing triggered")
    
    async def process_specific_trajectory(self, filename: str):
        """处理指定的轨迹文件"""
        logger.info(f"🎯 Triggering processing of specific trajectory: {filename}")
        await self.send_command(f"process_specific {filename}")
        logger.info(f"✅ Specific trajectory processing triggered: {filename}")
    
    async def generate_tasks(self, count: int = 3):
        """手动生成任务"""
        logger.info(f"⚡ Triggering manual task generation (count: {count})...")
        await self.send_command("generate_tasks", count=str(count))
        logger.info(f"✅ Task generation triggered for {count} tasks")
    
    async def get_status(self):
        """获取synthesis服务状态"""
        logger.info("📊 Requesting synthesis status...")
        await self.send_command("status")
        
        # 等待状态响应
        await asyncio.sleep(1)
        
        try:
            # 读取最新的状态
            result = await self.redis_client.xrevrange("synthesis:status", count=1)
            if result:
                message_id, fields = result[0]
                status_data = json.loads(fields[b'status'].decode('utf-8'))
                
                logger.info("📊 Synthesis Service Status:")
                logger.info("=" * 50)
                for key, value in status_data.items():
                    logger.info(f"  {key}: {value}")
                logger.info("=" * 50)
                
                return status_data
            else:
                logger.warning("No status data available")
                return None
                
        except Exception as e:
            logger.error(f"Failed to read status: {e}")
            return None
    
    async def list_trajectories(self):
        """列出所有轨迹文件"""
        trajectories_dir = "./output/trajectories"
        logger.info(f"📁 Listing trajectories in {trajectories_dir}:")
        
        if not os.path.exists(trajectories_dir):
            logger.warning("Trajectories directory not found")
            return []
        
        trajectory_files = []
        for filename in os.listdir(trajectories_dir):
            if filename.endswith('.json'):
                file_path = os.path.join(trajectories_dir, filename)
                file_stat = os.stat(file_path)
                file_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(file_stat.st_mtime))
                trajectory_files.append((filename, file_time))
                
        trajectory_files.sort(key=lambda x: x[1], reverse=True)  # 按时间排序
        
        if trajectory_files:
            logger.info("Found trajectory files:")
            for i, (filename, timestamp) in enumerate(trajectory_files, 1):
                logger.info(f"  {i:2d}. {filename} (modified: {timestamp})")
        else:
            logger.info("No trajectory files found")
            
        return trajectory_files


async def main():
    parser = argparse.ArgumentParser(
        description="Synthesis触发器 - 手动控制任务合成过程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 查看状态
  python scripts/trigger_synthesis.py status
  
  # 处理所有轨迹
  python scripts/trigger_synthesis.py full
  
  # 只处理新轨迹
  python scripts/trigger_synthesis.py new
  
  # 处理指定轨迹
  python scripts/trigger_synthesis.py specific trajectory_20241220_001.json
  
  # 生成任务
  python scripts/trigger_synthesis.py generate --count 5
  
  # 列出轨迹文件
  python scripts/trigger_synthesis.py list
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
    
    # 设置Redis URL
    redis_url = args.redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
    
    try:
        async with SynthesisTrigger(redis_url) as trigger:
            if args.action == "status":
                await trigger.get_status()
                
            elif args.action == "full":
                await trigger.trigger_full_synthesis()
                
            elif args.action == "new":
                await trigger.process_new_trajectories()
                
            elif args.action == "specific":
                if not args.target:
                    logger.error("❌ Specific action requires a target filename")
                    return 1
                await trigger.process_specific_trajectory(args.target)
                
            elif args.action == "generate":
                await trigger.generate_tasks(args.count)
                
            elif args.action == "list":
                await trigger.list_trajectories()
                
        logger.info("🎉 Operation completed successfully")
        return 0
        
    except Exception as e:
        logger.error(f"❌ Operation failed: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main())) 