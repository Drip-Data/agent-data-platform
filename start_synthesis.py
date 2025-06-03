#!/usr/bin/env python3
"""
Synthesis服务启动脚本
只启动synthesis worker，专注于轨迹处理和任务生成
"""

import os
import sys
import asyncio
import logging

# 添加当前目录到Python路径
sys.path.insert(0, '/app')

def setup_logging():
    """设置日志"""
    # 创建日志目录
    os.makedirs('/app/output/logs', exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('/app/output/logs/synthesis.log')
        ]
    )
    return logging.getLogger(__name__)

def main():
    """主函数"""
    logger = setup_logging()
    logger.info("🚀 启动 Synthesis Worker...")
    logger.info("📁 使用JSON文件存储模式")
    
    try:
        # 直接运行synthesis模块
        from core.synthesiscore.synthesis import main as synthesis_main
        asyncio.run(synthesis_main())
    except KeyboardInterrupt:
        logger.info("👋 收到停止信号，正在关闭...")
    except Exception as e:
        logger.error(f"❌ Synthesis Worker运行失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 