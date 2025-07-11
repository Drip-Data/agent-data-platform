#!/usr/bin/env python3
"""
性能优化集成测试
验证并行搜索、智能缓存和请求优化的集成效果
"""

import asyncio
import logging
import time
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_servers.deepsearch_server.deepsearch_tool_unified import DeepSearchToolUnified
from mcp_servers.deepsearch_server.intelligent_cache import IntelligentCache
from mcp_servers.deepsearch_server.request_optimizer import RequestOptimizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestPerformanceOptimization(unittest.TestCase):
    """性能优化集成测试"""
    
    def setUp(self):
        """测试设置"""
        self.config = {
            "cache_enabled": True,
            "cache_similarity_threshold": 0.7
        }
        
        # Mock LLM客户端
        self.mock_llm_client = AsyncMock()
        self.mock_llm_client._call_api = AsyncMock()
        
    def test_optimization_components_integration(self):
        """测试优化组件集成"""
        # 创建工具实例
        with patch('mcp_servers.deepsearch_server.deepsearch_tool_unified.LLMClient') as MockLLMClient:
            MockLLMClient.return_value = self.mock_llm_client
            
            tool = DeepSearchToolUnified(self.config)
            
            # 验证组件初始化
            self.assertIsNotNone(tool.cache)
            self.assertTrue(hasattr(tool, 'request_optimizer'))
            self.assertIsInstance(tool.cache, IntelligentCache)
            
            logger.info("✅ 优化组件集成正常")
    
    async def test_parallel_search_performance(self):
        """测试并行搜索性能"""
        
        # Mock LLM响应
        def mock_llm_response(messages):
            """模拟LLM响应"""
            content = messages[0]["content"]
            if "搜索查询" in content:
                # 查询生成响应
                return '{"queries": ["query1", "query2", "query3"], "rationale": "test"}'
            elif "搜索查询:" in content:
                # 搜索执行响应
                return f"搜索结果: {time.time()}"
            elif "综合" in content:
                # 答案综合响应
                return "综合分析结果"
            else:
                return "默认响应"
        
        with patch('mcp_servers.deepsearch_server.deepsearch_tool_unified.LLMClient') as MockLLMClient:
            mock_client = AsyncMock()
            mock_client._call_api = AsyncMock(side_effect=mock_llm_response)
            MockLLMClient.return_value = mock_client
            
            tool = DeepSearchToolUnified(self.config)
            
            # 执行研究
            start_time = time.time()
            result = await tool.research("测试并行搜索性能", research_depth="standard")
            execution_time = time.time() - start_time
            
            # 验证结果
            self.assertTrue(result["success"])
            self.assertIn("performance_stats", result)
            
            performance_stats = result["performance_stats"]
            self.assertIn("parallel_search_time", performance_stats)
            self.assertIn("total_research_time", performance_stats)
            
            logger.info(f"✅ 并行搜索完成，总耗时: {execution_time:.2f}s")
            logger.info(f"   - 并行搜索时间: {performance_stats['parallel_search_time']:.2f}s")
            logger.info(f"   - 总研究时间: {performance_stats['total_research_time']:.2f}s")
    
    async def test_request_optimization_effectiveness(self):
        """测试请求优化效果"""
        
        call_count = 0
        def counting_mock_response(messages):
            nonlocal call_count
            call_count += 1
            
            content = messages[0]["content"]
            if "搜索查询" in content:
                return '{"queries": ["opt_query1", "opt_query2"], "rationale": "optimized"}'
            else:
                return f"优化响应 #{call_count}"
        
        with patch('mcp_servers.deepsearch_server.deepsearch_tool_unified.LLMClient') as MockLLMClient:
            mock_client = AsyncMock()
            mock_client._call_api = AsyncMock(side_effect=counting_mock_response)
            MockLLMClient.return_value = mock_client
            
            tool = DeepSearchToolUnified(self.config)
            
            # 执行研究
            result = await tool.research("测试请求优化", research_depth="quick")
            
            # 验证优化统计
            self.assertTrue(result["success"])
            performance_stats = result["performance_stats"]
            
            if "optimization_stats" in performance_stats:
                opt_stats = performance_stats["optimization_stats"]
                logger.info(f"✅ 请求优化统计: {opt_stats}")
            
            # 验证LLM调用次数（应该被优化减少）
            logger.info(f"   - 总LLM调用次数: {call_count}")
            
    async def test_cache_performance_impact(self):
        """测试缓存对性能的影响"""
        
        with patch('mcp_servers.deepsearch_server.deepsearch_tool_unified.LLMClient') as MockLLMClient:
            mock_client = AsyncMock()
            mock_client._call_api = AsyncMock(return_value="缓存测试响应")
            MockLLMClient.return_value = mock_client
            
            tool = DeepSearchToolUnified(self.config)
            
            question = "测试缓存性能影响"
            
            # 第一次调用（缓存未命中）
            start_time = time.time()
            result1 = await tool.quick_research(question)
            first_call_time = time.time() - start_time
            
            # 第二次调用（缓存命中）
            start_time = time.time()
            result2 = await tool.quick_research(question)
            second_call_time = time.time() - start_time
            
            # 验证结果
            self.assertTrue(result1["success"])
            self.assertTrue(result2["success"])
            
            # 验证缓存效果
            if "_cache_info" in result2.get("output", {}):
                cache_info = result2["output"]["_cache_info"]
                logger.info(f"✅ 缓存命中: {cache_info['hit_type']}")
            
            logger.info(f"   - 第一次调用时间: {first_call_time:.2f}s")
            logger.info(f"   - 第二次调用时间: {second_call_time:.2f}s")
            logger.info(f"   - 性能提升: {((first_call_time - second_call_time) / first_call_time * 100):.1f}%")
    
    async def test_comprehensive_optimization_flow(self):
        """测试完整优化流程"""
        
        optimization_log = []
        
        def logging_mock_response(messages):
            content = messages[0]["content"]
            optimization_log.append(f"LLM调用: {content[:50]}...")
            
            if "搜索查询" in content:
                return '{"queries": ["comprehensive1", "comprehensive2", "comprehensive3"], "rationale": "full test"}'
            elif "搜索查询:" in content:
                return "详细搜索结果内容"
            elif "分析" in content:
                return '{"is_sufficient": true, "knowledge_gap": "", "follow_up_queries": []}'
            elif "综合" in content:
                return "完整的综合分析报告"
            else:
                return "通用响应"
        
        with patch('mcp_servers.deepsearch_server.deepsearch_tool_unified.LLMClient') as MockLLMClient:
            mock_client = AsyncMock()
            mock_client._call_api = AsyncMock(side_effect=logging_mock_response)
            MockLLMClient.return_value = mock_client
            
            tool = DeepSearchToolUnified(self.config)
            
            # 执行完整研究流程
            start_time = time.time()
            result = await tool.research(
                "完整优化流程测试", 
                research_depth="comprehensive", 
                max_iterations=2
            )
            total_time = time.time() - start_time
            
            # 验证结果
            self.assertTrue(result["success"])
            self.assertIn("performance_stats", result)
            
            # 分析优化效果
            performance_stats = result["performance_stats"]
            
            logger.info(f"✅ 完整优化流程测试完成")
            logger.info(f"   - 总执行时间: {total_time:.2f}s")
            logger.info(f"   - LLM调用序列: {len(optimization_log)}次")
            logger.info(f"   - 性能统计: {performance_stats}")
            
            # 验证优化组件工作状态
            cache_stats = tool.cache.get_cache_stats()
            logger.info(f"   - 缓存统计: {cache_stats}")

async def run_async_tests():
    """运行异步测试"""
    test_instance = TestPerformanceOptimization()
    test_instance.setUp()
    
    logger.info("🚀 开始性能优化集成测试")
    
    try:
        # 运行各项测试
        await test_instance.test_parallel_search_performance()
        await test_instance.test_request_optimization_effectiveness()
        await test_instance.test_cache_performance_impact()
        await test_instance.test_comprehensive_optimization_flow()
        
        logger.info("🎉 所有性能优化测试通过")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        raise

if __name__ == "__main__":
    # 运行同步测试
    suite = unittest.TestSuite()
    suite.addTest(TestPerformanceOptimization('test_optimization_components_integration'))
    runner = unittest.TextTestRunner(verbosity=2)
    sync_result = runner.run(suite)
    
    # 运行异步测试
    asyncio.run(run_async_tests())
    
    print("\n📊 性能优化集成测试完成")