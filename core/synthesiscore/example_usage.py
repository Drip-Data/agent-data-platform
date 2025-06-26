#!/usr/bin/env python3
"""
Enhanced SynthesisCore Usage Example - 增强合成核心使用示例
演示如何使用所有新的改进功能
"""

import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, List, Any

# 假设的导入 - 实际使用时需要根据项目结构调整
from core.interfaces import TrajectoryResult, ExecutionStep
from core.llm_client import LLMClient  # 假设存在
from core.toolscore.mcp_client import MCPToolClient  # 假设存在

from .enhanced_synthesis_controller import EnhancedSynthesisController
from .enhanced_interfaces import AtomicTask, TaskType, TaskDifficulty

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MockLLMClient:
    """模拟LLM客户端 - 用于测试"""
    
    async def generate_reasoning(self, task_description: str, available_tools: List[str] = None, 
                               execution_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """模拟LLM推理生成"""
        await asyncio.sleep(0.1)  # 模拟网络延迟
        
        # 简单的模拟响应
        if "similarity" in task_description.lower():
            return {"thinking": "0.75"}
        elif "score" in task_description.lower():
            return {"thinking": '{"score": 0.8, "feedback": "质量良好"}'}
        elif "search" in task_description.lower():
            return {"thinking": '{"search_queries": ["相关信息查询", "背景资料搜索"]}'}
        else:
            return {"thinking": "这是一个模拟的LLM响应"}


class MockMCPClient:
    """模拟MCP客户端 - 用于测试"""
    
    async def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """模拟工具调用"""
        await asyncio.sleep(0.2)  # 模拟工具执行时间
        
        if tool_name == "deepsearch":
            return {
                "results": [
                    {
                        "title": "相关文档标题",
                        "snippet": "这是搜索结果的摘要内容",
                        "url": "https://example.com/doc1"
                    }
                ]
            }
        else:
            return {"result": "模拟工具执行结果"}


def create_mock_trajectory() -> TrajectoryResult:
    """创建模拟轨迹"""
    steps = [
        ExecutionStep(
            step_id="step_1",
            tool_name="search",
            parameters={"query": "Python异步编程"},
            result="找到了关于Python异步编程的相关资料",
            execution_time=1.5,
            success=True
        ),
        ExecutionStep(
            step_id="step_2", 
            tool_name="summarize",
            parameters={"content": "异步编程文档内容"},
            result="总结：异步编程是一种提高程序性能的重要技术",
            execution_time=2.0,
            success=True
        )
    ]
    
    return TrajectoryResult(
        trajectory_id="traj_001",
        task_id="task_001",
        user_id="user_001",
        steps=steps,
        final_result="成功完成了关于Python异步编程的学习任务",
        is_successful=True,
        total_execution_time=3.5,
        task_complexity_score=0.7,
        processing_time_seconds=3.5,
        error_message=None
    )


async def example_basic_usage():
    """基础使用示例"""
    logger.info("🚀 开始基础使用示例")
    
    # 1. 初始化组件
    llm_client = MockLLMClient()
    mcp_client = MockMCPClient()
    
    # 2. 创建增强合成控制器
    controller = EnhancedSynthesisController(
        llm_client=llm_client,
        mcp_client=mcp_client,
        enable_real_time=True
    )
    
    # 3. 注册回调函数
    def on_task_generated(tasks):
        logger.info(f"📝 生成了 {len(tasks)} 个新任务")
    
    def on_quality_report(report):
        logger.info(f"📊 质量报告: 通过率 {report.get('processing_summary', {}).get('verification_pass_rate', 0):.3f}")
    
    controller.register_callback("task_generated", on_task_generated)
    controller.register_callback("quality_report", on_quality_report)
    
    # 4. 启动控制器
    await controller.start()
    
    try:
        # 5. 处理单个轨迹
        trajectory = create_mock_trajectory()
        result = await controller.process_trajectory(trajectory)
        
        logger.info(f"✅ 轨迹处理结果: {result['success']}")
        if result['success']:
            logger.info(f"📊 生成任务统计: {result['task_generation']}")
            logger.info(f"🎯 质量评估: {result['quality_assessment']}")
        
        # 6. 查看状态
        status = controller.get_status()
        logger.info(f"📈 控制器状态: 任务池大小 {status['task_pool_size']['total']}")
        
        # 7. 等待一段时间，观察实时扩展
        logger.info("⏱️ 等待实时扩展处理...")
        await asyncio.sleep(5)
        
        # 8. 查看最终状态
        final_status = controller.get_status()
        logger.info(f"📊 最终状态: {final_status['session_metrics']['total_tasks_generated']} 个任务已生成")
        
    finally:
        # 9. 停止控制器
        await controller.stop()
    
    logger.info("✅ 基础使用示例完成")


async def example_batch_processing():
    """批量处理示例"""
    logger.info("🚀 开始批量处理示例")
    
    # 初始化
    llm_client = MockLLMClient()
    mcp_client = MockMCPClient()
    controller = EnhancedSynthesisController(llm_client, mcp_client, enable_real_time=False)
    
    await controller.start()
    
    try:
        # 创建多个模拟轨迹
        trajectories = []
        for i in range(5):
            trajectory = create_mock_trajectory()
            trajectory.trajectory_id = f"batch_traj_{i+1}"
            trajectory.task_id = f"batch_task_{i+1}"
            trajectories.append(trajectory)
        
        # 批量处理
        logger.info(f"🔄 开始批量处理 {len(trajectories)} 个轨迹")
        start_time = asyncio.get_event_loop().time()
        
        results = await controller.batch_process_trajectories(trajectories, max_concurrent=3)
        
        end_time = asyncio.get_event_loop().time()
        processing_time = end_time - start_time
        
        # 统计结果
        successful_count = len(results)
        total_tasks_generated = sum(r['task_generation']['total_generated'] for r in results)
        avg_quality_score = sum(r['quality_assessment']['average_quality_score'] for r in results) / len(results)
        
        logger.info(f"✅ 批量处理完成:")
        logger.info(f"   - 处理时间: {processing_time:.2f} 秒")
        logger.info(f"   - 成功率: {successful_count}/{len(trajectories)}")
        logger.info(f"   - 总生成任务: {total_tasks_generated}")
        logger.info(f"   - 平均质量分数: {avg_quality_score:.3f}")
        
    finally:
        await controller.stop()
    
    logger.info("✅ 批量处理示例完成")


async def example_adaptive_configuration():
    """自适应配置示例"""
    logger.info("🚀 开始自适应配置示例")
    
    llm_client = MockLLMClient()
    mcp_client = MockMCPClient()
    controller = EnhancedSynthesisController(llm_client, mcp_client)
    
    await controller.start()
    
    try:
        # 查看初始配置
        initial_config = controller.export_configuration()
        logger.info(f"📋 初始配置:")
        logger.info(f"   - 深度阈值: {initial_config['adaptive_config']['depth_config']['superset_confidence_threshold']}")
        logger.info(f"   - 宽度阈值: {initial_config['adaptive_config']['width_config']['semantic_similarity_threshold']}")
        logger.info(f"   - 批处理大小: {initial_config['adaptive_config']['batch_config']['batch_size']}")
        
        # 处理一些轨迹以触发自适应调整
        for i in range(10):
            trajectory = create_mock_trajectory()
            trajectory.trajectory_id = f"adaptive_traj_{i+1}"
            
            # 模拟不同的成功率
            if i < 3:  # 前几个任务模拟较低成功率
                trajectory.is_successful = False
            
            await controller.process_trajectory(trajectory)
            
            # 每处理几个轨迹后查看配置变化
            if (i + 1) % 3 == 0:
                current_config = controller.export_configuration()
                current_success_rate = controller.adaptive_config.get_current_success_rate()
                logger.info(f"🔧 第 {i+1} 轮后:")
                logger.info(f"   - 当前成功率: {current_success_rate:.3f}")
                logger.info(f"   - 深度阈值: {current_config['adaptive_config']['depth_config']['superset_confidence_threshold']:.3f}")
                logger.info(f"   - 宽度阈值: {current_config['adaptive_config']['width_config']['semantic_similarity_threshold']:.3f}")
        
        # 查看最终配置
        final_config = controller.export_configuration()
        logger.info(f"📊 最终配置:")
        logger.info(f"   - 深度阈值变化: {initial_config['adaptive_config']['depth_config']['superset_confidence_threshold']:.3f} → {final_config['adaptive_config']['depth_config']['superset_confidence_threshold']:.3f}")
        logger.info(f"   - 宽度阈值变化: {initial_config['adaptive_config']['width_config']['semantic_similarity_threshold']:.3f} → {final_config['adaptive_config']['width_config']['semantic_similarity_threshold']:.3f}")
        
    finally:
        await controller.stop()
    
    logger.info("✅ 自适应配置示例完成")


async def example_performance_monitoring():
    """性能监控示例"""
    logger.info("🚀 开始性能监控示例")
    
    llm_client = MockLLMClient()
    mcp_client = MockMCPClient()
    controller = EnhancedSynthesisController(llm_client, mcp_client, enable_real_time=True)
    
    await controller.start()
    
    # 启动监控
    if controller.real_time_manager:
        monitoring_task = asyncio.create_task(
            controller.real_time_manager.start_monitoring(interval_seconds=2)
        )
    
    try:
        # 模拟持续的轨迹处理
        for i in range(8):
            trajectory = create_mock_trajectory()
            trajectory.trajectory_id = f"monitor_traj_{i+1}"
            
            result = await controller.process_trajectory(trajectory)
            logger.info(f"📈 处理轨迹 {i+1}: 生成 {result['task_generation']['total_generated']} 个任务")
            
            # 每次处理后短暂等待
            await asyncio.sleep(1)
        
        # 等待监控数据收集
        await asyncio.sleep(5)
        
        # 生成监控报告
        if controller.real_time_manager:
            monitoring_report = controller.real_time_manager.get_monitoring_report()
            logger.info(f"📊 监控报告:")
            logger.info(f"   - 监控时长: {monitoring_report.get('monitoring_period', {}).get('data_points', 0)} 个数据点")
            logger.info(f"   - 平均成功率: {monitoring_report.get('trends', {}).get('average_success_rate', 0):.3f}")
            logger.info(f"   - 平均队列大小: {monitoring_report.get('trends', {}).get('average_queue_size', 0):.1f}")
            
            recommendations = monitoring_report.get('recommendations', [])
            if recommendations:
                logger.info(f"💡 监控建议:")
                for rec in recommendations:
                    logger.info(f"   - {rec}")
        
        # 获取性能摘要
        performance = controller.get_performance_summary()
        logger.info(f"🎯 性能摘要:")
        logger.info(f"   - 处理轨迹: {performance['total_trajectories_processed']}")
        logger.info(f"   - 生成任务: {performance['total_tasks_generated']}")
        logger.info(f"   - 生成效率: {performance['generation_efficiency']:.2f}")
        logger.info(f"   - 验证通过率: {performance['verification_pass_rate']:.3f}")
        
    finally:
        # 停止监控
        if controller.real_time_manager:
            controller.real_time_manager.stop_monitoring()
            monitoring_task.cancel()
        
        await controller.stop()
    
    logger.info("✅ 性能监控示例完成")


async def main():
    """主函数 - 运行所有示例"""
    logger.info("🎉 开始Enhanced SynthesisCore功能演示")
    
    try:
        # 运行各种示例
        await example_basic_usage()
        await asyncio.sleep(2)
        
        await example_batch_processing()
        await asyncio.sleep(2)
        
        await example_adaptive_configuration()
        await asyncio.sleep(2)
        
        await example_performance_monitoring()
        
    except Exception as e:
        logger.error(f"❌ 示例运行失败: {e}")
        raise
    
    logger.info("🎉 所有示例演示完成！")


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())