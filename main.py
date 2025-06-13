#!/usr/bin/env python3
"""
Agent Data Platform - Main Entry Point (无Docker版本)
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.toolscore.core_manager import CoreManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/toolscore.log', mode='a')
    ]
)

logger = logging.getLogger(__name__)

async def main():
    """主启动函数"""
    logger.info("启动 Agent Data Platform (无Docker版本)...")
    
    try:
        # 创建必要目录
        os.makedirs('logs', exist_ok=True)
        os.makedirs('output/trajectories', exist_ok=True)
        os.makedirs('config', exist_ok=True)
        os.makedirs('data', exist_ok=True)
        
        # 初始化核心管理器
        core_manager = CoreManager()
        await core_manager.initialize()
        
        # 创建并初始化工具库（避免循环依赖）
        from core.toolscore.unified_tool_library import UnifiedToolLibrary
        tool_library = UnifiedToolLibrary(redis_url="redis://localhost:6379")
        await tool_library.initialize()
        
        # 注入工具库到监控API
        core_manager.monitoring_api.tool_library = tool_library
        
        # 启动服务
        await core_manager.start()
        
        logger.info("Agent Data Platform 启动成功！")
        logger.info("服务地址: http://localhost:8080")
        logger.info("WebSocket地址: ws://localhost:8081")
        logger.info("监控地址: http://localhost:8082")
        logger.info("按 Ctrl+C 停止服务")
        
        # 保持服务运行
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到停止信号，正在关闭服务...")
            
    except Exception as e:
        logger.error(f"启动失败: {e}")
        sys.exit(1)
    finally:
        # 清理资源
        try:
            await core_manager.stop()
            logger.info("Agent Data Platform 已停止")
        except Exception as e:
            logger.error(f"停止服务时出错: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("服务已停止")
    except Exception as e:
        logger.error(f"运行时错误: {e}")
        sys.exit(1)