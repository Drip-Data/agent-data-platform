#!/usr/bin/env python3
"""
并发和超时控制测试
验证请求限制、超时处理和系统健康监控功能
"""

import asyncio
import logging
import time
import unittest
from unittest.mock import AsyncMock, patch
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_servers.deepsearch_server.deepsearch_tool_unified import DeepSearchToolUnified
from mcp_servers.deepsearch_server.request_optimizer import RequestOptimizer, LLMRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestConcurrencyTimeout(unittest.TestCase):
    """并发和超时控制测试"""
    
    def setUp(self):
        """测试设置"""
        self.config = {
            "cache_enabled": True,
            "max_concurrent_requests": 2,  # 设置较小的并发限制便于测试
            "default_timeout": 5.0,        # 设置较短的超时便于测试
            "batch_size": 2
        }
        
        # Mock LLM客户端
        self.mock_llm_client = AsyncMock()
        self.mock_llm_client._call_api = AsyncMock()
    
    async def test_concurrent_request_limiting(self):
        """测试并发请求限制"""
        
        # 创建慢响应的mock
        async def slow_response(messages):
            await asyncio.sleep(2)  # 模拟慢响应
            return f"慢响应结果: {time.time()}"
        
        with patch('mcp_servers.deepsearch_server.deepsearch_tool_unified.LLMClient') as MockLLMClient:
            mock_client = AsyncMock()
            mock_client._call_api = slow_response
            MockLLMClient.return_value = mock_client
            
            tool = DeepSearchToolUnified(self.config)
            optimizer = tool.request_optimizer
            
            # 创建多个并发请求
            requests = []
            for i in range(5):  # 超过并发限制的请求数
                request = LLMRequest(
                    task_type="test",
                    prompt=f"并发测试请求 {i}",
                    priority=1,
                    timeout=10.0
                )
                requests.append(request)
            
            # 并发执行请求
            start_time = time.time()
            tasks = [optimizer.execute_request(req) for req in requests]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            execution_time = time.time() - start_time
            
            # 验证结果
            self.assertEqual(len(results), 5)
            
            # 检查统计信息
            stats = optimizer.get_stats()
            logger.info(f"✅ 并发限制测试完成")
            logger.info(f"   - 执行时间: {execution_time:.2f}s")
            logger.info(f"   - 并发限制命中次数: {stats['concurrent_limit_hits']}")
            logger.info(f"   - 最大并发达到: {stats['max_concurrent_reached']}")
            
            # 验证并发限制生效
            self.assertLessEqual(stats['max_concurrent_reached'], self.config['max_concurrent_requests'])
    
    async def test_timeout_handling(self):
        """测试超时处理"""
        
        # 创建超时响应的mock
        async def timeout_response(messages):
            await asyncio.sleep(10)  # 超过配置的超时时间
            return "永远不会返回的结果"
        
        with patch('mcp_servers.deepsearch_server.deepsearch_tool_unified.LLMClient') as MockLLMClient:
            mock_client = AsyncMock()
            mock_client._call_api = timeout_response
            MockLLMClient.return_value = mock_client
            
            tool = DeepSearchToolUnified(self.config)
            optimizer = tool.request_optimizer
            
            # 创建会超时的请求
            request = LLMRequest(
                task_type="timeout_test",
                prompt="这个请求会超时",
                priority=1,
                timeout=2.0  # 短超时时间
            )
            
            # 执行请求并期待超时
            start_time = time.time()
            with self.assertRaises(TimeoutError):
                await optimizer.execute_request(request)
            
            execution_time = time.time() - start_time
            
            # 验证超时时间合理
            self.assertLess(execution_time, 5.0)  # 应该在超时时间内失败
            
            # 检查超时统计
            stats = optimizer.get_stats()
            self.assertGreater(stats['timeout_errors'], 0)
            
            logger.info(f"✅ 超时处理测试完成")
            logger.info(f"   - 执行时间: {execution_time:.2f}s")
            logger.info(f"   - 超时错误次数: {stats['timeout_errors']}")
    
    async def test_health_monitoring(self):
        """测试健康监控功能"""
        
        # 创建混合响应的mock（部分成功，部分超时）
        call_count = 0
        async def mixed_response(messages):
            nonlocal call_count
            call_count += 1
            
            if call_count % 3 == 0:  # 每第3个请求超时
                await asyncio.sleep(10)
                return "超时响应"
            else:
                await asyncio.sleep(0.1)
                return f"正常响应 #{call_count}"
        
        with patch('mcp_servers.deepsearch_server.deepsearch_tool_unified.LLMClient') as MockLLMClient:
            mock_client = AsyncMock()
            mock_client._call_api = mixed_response
            MockLLMClient.return_value = mock_client
            
            tool = DeepSearchToolUnified(self.config)
            optimizer = tool.request_optimizer
            
            # 执行多个请求以生成统计数据
            requests = []
            for i in range(6):
                request = LLMRequest(
                    task_type="health_test",
                    prompt=f"健康监控测试 {i}",
                    priority=1,
                    timeout=2.0
                )
                requests.append(request)
            
            # 执行请求（期待部分失败）
            results = []
            for req in requests:
                try:
                    result = await optimizer.execute_request(req)
                    results.append(result)
                except TimeoutError:
                    results.append(None)  # 超时请求
            
            # 检查健康状态
            health_status = optimizer.get_health_status()
            
            logger.info(f"✅ 健康监控测试完成")
            logger.info(f"   - 健康状态: {health_status['status']}")
            logger.info(f"   - 健康评分: {health_status['health_score']}")
            logger.info(f"   - 超时率: {health_status['timeout_rate_percent']}%")
            logger.info(f"   - 活跃请求: {health_status['active_requests']}")
            
            # 验证健康监控功能
            self.assertIn(health_status['status'], ['healthy', 'degraded', 'unhealthy'])
            self.assertIsInstance(health_status['health_score'], (int, float))
            self.assertGreaterEqual(health_status['health_score'], 0)
            self.assertLessEqual(health_status['health_score'], 100)
    
    async def test_graceful_completion_waiting(self):
        """测试优雅的完成等待"""
        
        # 创建有延迟的响应
        async def delayed_response(messages):
            await asyncio.sleep(1)
            return f"延迟响应: {time.time()}"
        
        with patch('mcp_servers.deepsearch_server.deepsearch_tool_unified.LLMClient') as MockLLMClient:
            mock_client = AsyncMock()
            mock_client._call_api = delayed_response
            MockLLMClient.return_value = mock_client
            
            tool = DeepSearchToolUnified(self.config)
            optimizer = tool.request_optimizer
            
            # 启动一些后台请求
            background_tasks = []
            for i in range(3):
                request = LLMRequest(
                    task_type="background",
                    prompt=f"后台请求 {i}",
                    priority=1
                )
                task = asyncio.create_task(optimizer.execute_request(request))
                background_tasks.append(task)
            
            # 稍等让请求开始
            await asyncio.sleep(0.5)
            
            # 等待所有请求完成
            start_time = time.time()
            
            # 直接等待所有任务完成
            await asyncio.gather(*background_tasks, return_exceptions=True)
            
            # 然后等待优化器清理
            await optimizer.wait_for_completion(timeout=5.0)
            completion_time = time.time() - start_time
            
            # 验证所有任务都完成了
            all_done = all(task.done() for task in background_tasks)
            
            logger.info(f"✅ 优雅完成等待测试")
            logger.info(f"   - 等待时间: {completion_time:.2f}s")
            logger.info(f"   - 所有任务完成: {all_done}")
            logger.info(f"   - 剩余活跃请求: {optimizer._active_requests}")
            
            # 验证完成状态
            self.assertTrue(all_done)
            self.assertEqual(optimizer._active_requests, 0)
    
    async def test_integration_with_deepsearch_tool(self):
        """测试与DeepSearch工具的集成"""
        
        # 快速响应的mock
        def quick_response(messages):
            content = messages[0]["content"]
            if "搜索查询" in content:
                return '{"queries": ["集成测试查询"], "rationale": "integration test"}'
            else:
                return "快速集成测试响应"
        
        with patch('mcp_servers.deepsearch_server.deepsearch_tool_unified.LLMClient') as MockLLMClient:
            mock_client = AsyncMock()
            mock_client._call_api = AsyncMock(side_effect=quick_response)
            MockLLMClient.return_value = mock_client
            
            tool = DeepSearchToolUnified(self.config)
            
            # 执行研究任务
            result = await tool.quick_research("集成测试：并发和超时控制")
            
            # 验证结果包含性能统计
            self.assertTrue(result["success"])
            self.assertIn("performance_stats", result)
            
            performance_stats = result["performance_stats"]
            self.assertIn("optimization_stats", performance_stats)
            
            # 获取健康状态
            health_status = tool.get_health_status()
            optimization_stats = tool.get_optimization_stats()
            
            logger.info(f"✅ DeepSearch工具集成测试完成")
            logger.info(f"   - 研究成功: {result['success']}")
            logger.info(f"   - 健康状态: {health_status.get('status', 'unknown')}")
            logger.info(f"   - 优化统计: {optimization_stats}")
            
            # 验证集成功能
            self.assertIsInstance(health_status, dict)
            self.assertIsInstance(optimization_stats, dict)

async def run_async_tests():
    """运行异步测试"""
    test_instance = TestConcurrencyTimeout()
    test_instance.setUp()
    
    logger.info("🚀 开始并发和超时控制测试")
    
    try:
        # 运行各项测试
        await test_instance.test_concurrent_request_limiting()
        await test_instance.test_timeout_handling()
        await test_instance.test_health_monitoring()
        await test_instance.test_graceful_completion_waiting()
        await test_instance.test_integration_with_deepsearch_tool()
        
        logger.info("🎉 所有并发和超时控制测试通过")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        raise

if __name__ == "__main__":
    # 运行异步测试
    asyncio.run(run_async_tests())
    
    print("\n📊 并发和超时控制测试完成")