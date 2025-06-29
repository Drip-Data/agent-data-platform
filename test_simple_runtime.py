#!/usr/bin/env python3
"""
简化运行时测试脚本
测试 simple_runtime 的 XML streaming 功能
"""

import asyncio
import logging
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config_manager import ConfigManager
from core.llm_client import LLMClient
from runtimes.reasoning.toolscore_client import ToolScoreClient
from runtimes.reasoning.simple_runtime import SimpleReasoningRuntime
from core.interfaces import TaskSpec, TaskType

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_simple_runtime():
    """测试简化运行时"""
    try:
        logger.info("🚀 开始测试简化运行时...")
        
        # 1. 初始化配置管理器
        config_manager = ConfigManager(config_dir="config")
        
        # 2. 初始化LLM客户端
        llm_client = LLMClient(config_manager.get_llm_config())
        
        # 3. 初始化ToolScore客户端
        toolscore_client = ToolScoreClient("http://localhost:8082")
        
        # 4. 创建简化运行时实例 (启用XML streaming)
        runtime = SimpleReasoningRuntime(
            config_manager=config_manager,
            llm_client=llm_client,
            toolscore_client=toolscore_client,
            xml_streaming_mode=True
        )
        
        logger.info(f"✅ 简化运行时创建完成，ID: {runtime.runtime_id}")
        
        # 5. 初始化运行时
        await runtime.initialize()
        logger.info("✅ 运行时初始化完成")
        
        # 6. 健康检查
        health = await runtime.health_check()
        logger.info(f"🏥 健康检查结果: {health}")
        
        # 7. 测试能力查询
        capabilities = await runtime.capabilities()
        logger.info(f"🛠️ 运行时能力: {capabilities}")
        
        # 8. 创建测试任务
        test_task = TaskSpec(
            task_id="test-simple-runtime",
            task_type=TaskType.REASONING,
            description="写一个简单的Python函数来计算斐波那契数列的第n项，并测试该函数",
            max_steps=3
        )
        
        logger.info(f"📋 创建测试任务: {test_task.description}")
        
        # 9. 执行任务
        logger.info("🎯 开始执行任务...")
        result = await runtime.execute(test_task)
        
        # 10. 显示结果
        logger.info("🎉 任务执行完成！")
        logger.info(f"✅ 成功状态: {result.success}")
        logger.info(f"⏱️ 执行时间: {result.total_duration:.2f}秒")
        logger.info(f"📝 最终结果: {result.final_result}")
        
        if result.metadata and result.metadata.get('output_format') == 'raw_xml_streaming':
            logger.info("🔥 原始XML轨迹已输出到控制台")
            
        # 11. 清理资源
        await runtime.cleanup()
        logger.info("🧹 资源清理完成")
        
        return result.success
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        return False

async def main():
    """主函数"""
    logger.info("🔬 简化运行时测试开始...")
    
    success = await test_simple_runtime()
    
    if success:
        logger.info("✅ 所有测试通过！")
        sys.exit(0)
    else:
        logger.error("❌ 测试失败")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())