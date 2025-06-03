#!/usr/bin/env python3
"""
任务合成器插件 - 独立模块入口
这是对agent-data-platform项目的扩展插件，可以独立部署
"""

import os
import asyncio
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class SynthesisPlugin:
    """任务合成器插件 - 可插拔模块"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or self._load_default_config()
        self.synthesizer = None
        
    def _load_default_config(self) -> Dict:
        """加载默认配置"""
        return {
            "redis_url": os.getenv("REDIS_URL", "redis://redis:6379"),
            "synthesis_db": os.getenv("SYNTHESIS_DB", "/app/output/synthesis.db"),
            "synthesis_enabled": os.getenv("SYNTHESIS_ENABLED", "false").lower() == "true",
            "vllm_url": os.getenv("VLLM_URL", "http://vllm:8000"),
            "plugin_mode": True  # 标识为插件模式
        }
    
    async def initialize(self):
        """初始化插件"""
        if not self.config.get("synthesis_enabled", False):
            logger.info("Synthesis plugin is disabled")
            return False
            
        try:
            from .synthesis import SimpleSynthesizer
            self.synthesizer = SimpleSynthesizer(self.config)
            logger.info("Synthesis plugin initialized successfully")
            return True
        except ImportError as e:
            logger.error(f"Failed to import synthesis module: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize synthesis plugin: {e}")
            return False
    
    async def start(self):
        """启动插件"""
        if not self.synthesizer:
            logger.warning("Synthesizer not initialized, skipping plugin start")
            return
            
        logger.info("Starting synthesis plugin...")
        await self.synthesizer.start()
    
    async def stop(self):
        """停止插件"""
        if self.synthesizer:
            logger.info("Stopping synthesis plugin...")
            try:
                await self.synthesizer.redis.aclose()
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {e}")
    
    async def generate_tasks_manually(self, count: int = 3):
        """手动生成任务 - 插件接口"""
        if not self.synthesizer:
            logger.error("Synthesizer not initialized")
            return []
            
        return await self.synthesizer.generate_tasks_manually(count)
    
    def get_status(self) -> Dict:
        """获取插件状态"""
        return {
            "plugin_name": "synthesis",
            "enabled": self.config.get("synthesis_enabled", False),
            "initialized": self.synthesizer is not None,
            "config": {
                "synthesis_db": self.config.get("synthesis_db"),
                "redis_url": self.config.get("redis_url")
            }
        }


async def main():
    """插件独立运行入口"""
    logging.basicConfig(level=logging.INFO)
    
    plugin = SynthesisPlugin()
    
    if await plugin.initialize():
        try:
            await plugin.start()
        except KeyboardInterrupt:
            logger.info("Synthesis plugin interrupted")
        finally:
            await plugin.stop()
    else:
        logger.info("Synthesis plugin failed to initialize, exiting...")


if __name__ == "__main__":
    asyncio.run(main()) 