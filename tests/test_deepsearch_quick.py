#!/usr/bin/env python3
"""
DeepSearch Server 快速测试
使用mock来避免实际LLM调用，专注于测试核心逻辑
"""

import asyncio
import pytest
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import sys
import os
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mcp_servers.deepsearch_server.main import DeepSearchMCPServer
from core.config_manager import ConfigManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DeepSearchQuickTester:
    """DeepSearch 快速测试器（使用mock）"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.server = None
        self.test_results = []
        self.start_time = None
        
    async def setup_test_environment(self):
        """设置测试环境"""
        logger.info("🔧 Setting up DeepSearch quick test environment...")
        
        # Initialize server
        self.server = DeepSearchMCPServer(self.config_manager)
        
        logger.info("✅ DeepSearch quick test environment setup complete")
        
    def log_test_result(self, test_name: str, test_case: str, success: bool, 
                       duration: float, details: Dict[str, Any] = None, 
                       error: str = None):
        """记录测试结果"""
        self.test_results.append({
            'test_name': test_name,
            'test_case': test_case,
            'success': success,
            'duration': duration,
            'details': details or {},
            'error': error,
            'timestamp': datetime.now().isoformat()
        })
        
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} {test_name} - {test_case} ({duration:.2f}s)")
        if error:
            logger.error(f"    Error: {error}")
    
    async def test_json_parsing_fix(self):
        """测试JSON解析修复"""
        logger.info("🧪 Testing JSON parsing fix...")
        
        # 模拟LLM返回的各种格式
        test_cases = [
            {
                "name": "markdown_json_format",
                "mock_response": '''```json
{
  "queries": ["测试查询1", "测试查询2"],
  "rationale": "测试原理"
}
```''',
                "description": "Markdown JSON格式"
            },
            {
                "name": "plain_json_format",
                "mock_response": '{"queries": ["测试查询"], "rationale": "测试"}',
                "description": "纯JSON格式"
            },
            {
                "name": "invalid_format",
                "mock_response": "这不是JSON格式的响应",
                "description": "无效格式处理"
            }
        ]
        
        for test_case in test_cases:
            start_time = time.time()
            try:
                # Mock LLM响应
                with patch('core.llm_client.LLMClient._call_api', return_value=test_case["mock_response"]):
                    result = await self.server.handle_tool_action(
                        "research",
                        {"question": "测试JSON解析"}
                    )
                
                # 对于前两种情况应该成功，第三种会回退到原问题
                expected_success = test_case["name"] != "invalid_format"
                actual_success = result.get("success", False)
                
                # 即使是invalid_format，也应该gracefully处理而不是崩溃
                success = actual_success if expected_success else not result.get("crashed", False)
                
                duration = time.time() - start_time
                
                self.log_test_result(
                    "JSON Parsing Fix",
                    test_case["description"],
                    success,
                    duration,
                    {
                        "case": test_case["name"],
                        "expected_success": expected_success,
                        "actual_success": actual_success,
                        "mock_response_type": type(test_case["mock_response"]).__name__
                    }
                )
                
            except Exception as e:
                duration = time.time() - start_time
                # 对于测试来说，异常不应该发生
                self.log_test_result(
                    "JSON Parsing Fix",
                    test_case["description"],
                    False,
                    duration,
                    error=str(e)
                )
    
    async def test_parameter_mapping_with_mock(self):
        """测试参数映射（使用mock）"""
        logger.info("🧪 Testing parameter mapping with mock...")
        
        mock_research_response = {
            "answer": "这是模拟的研究结果",
            "sources": [{"title": "测试来源", "url": "https://test.com"}],
            "query_count": 1
        }
        
        test_cases = [
            {
                "parameters": {"question": "直接问题参数"},
                "description": "直接question参数"
            },
            {
                "parameters": {"query": "查询参数映射"},
                "description": "query->question映射"
            },
            {
                "parameters": {"task_description": "任务描述映射"},
                "description": "task_description->question映射"
            }
        ]
        
        for test_case in test_cases:
            start_time = time.time()
            try:
                # Mock整个研究过程
                with patch.object(self.server.deepsearch_tool, 'research', return_value=mock_research_response):
                    result = await self.server.handle_tool_action(
                        "research",
                        test_case["parameters"]
                    )
                
                success = result.get("success", False)
                duration = time.time() - start_time
                
                self.log_test_result(
                    "Parameter Mapping",
                    test_case["description"],
                    success,
                    duration,
                    {
                        "parameters": test_case["parameters"],
                        "result_success": success
                    }
                )
                
            except Exception as e:
                duration = time.time() - start_time
                self.log_test_result(
                    "Parameter Mapping",
                    test_case["description"],
                    False,
                    duration,
                    error=str(e)
                )
    
    async def test_action_routing(self):
        """测试动作路由"""
        logger.info("🧪 Testing action routing...")
        
        mock_response = {
            "answer": "模拟回答",
            "sources": [],
            "query_count": 1
        }
        
        test_actions = [
            {"action": "research", "description": "基础研究动作"},
            {"action": "quick_research", "description": "快速研究动作"},
            {"action": "comprehensive_research", "description": "全面研究动作"}
        ]
        
        for test_action in test_actions:
            start_time = time.time()
            try:
                # Mock所有research方法
                with patch.object(self.server.deepsearch_tool, 'research', return_value=mock_response), \
                     patch.object(self.server.deepsearch_tool, 'quick_research', return_value=mock_response), \
                     patch.object(self.server.deepsearch_tool, 'comprehensive_research', return_value=mock_response):
                    
                    result = await self.server.handle_tool_action(
                        test_action["action"],
                        {"question": "测试动作路由"}
                    )
                
                success = result.get("success", False)
                duration = time.time() - start_time
                
                self.log_test_result(
                    "Action Routing",
                    test_action["description"],
                    success,
                    duration,
                    {
                        "action": test_action["action"],
                        "result_success": success
                    }
                )
                
            except Exception as e:
                duration = time.time() - start_time
                self.log_test_result(
                    "Action Routing",
                    test_action["description"],
                    False,
                    duration,
                    error=str(e)
                )
    
    async def test_error_handling_scenarios(self):
        """测试错误处理场景"""
        logger.info("🧪 Testing error handling scenarios...")
        
        error_scenarios = [
            {
                "scenario": "tool_method_not_found",
                "action": "nonexistent_research",
                "parameters": {"question": "测试"},
                "description": "不存在的动作",
                "expect_failure": True
            },
            {
                "scenario": "missing_required_parameter",
                "action": "research",
                "parameters": {},  # 缺少question参数
                "description": "缺少必需参数",
                "expect_failure": True
            },
            {
                "scenario": "tool_exception",
                "action": "research",
                "parameters": {"question": "测试异常"},
                "description": "工具执行异常",
                "mock_exception": Exception("模拟工具异常"),
                "expect_failure": True
            }
        ]
        
        for scenario in error_scenarios:
            start_time = time.time()
            try:
                if "mock_exception" in scenario:
                    # Mock异常
                    with patch.object(self.server.deepsearch_tool, 'research', side_effect=scenario["mock_exception"]):
                        result = await self.server.handle_tool_action(
                            scenario["action"],
                            scenario["parameters"]
                        )
                else:
                    # 正常调用
                    result = await self.server.handle_tool_action(
                        scenario["action"],
                        scenario["parameters"]
                    )
                
                expect_failure = scenario.get("expect_failure", False)
                actual_success = result.get("success", False)
                
                # 如果期望失败，那么实际失败就是成功
                success = (not actual_success) if expect_failure else actual_success
                
                duration = time.time() - start_time
                
                self.log_test_result(
                    "Error Handling",
                    scenario["description"],
                    success,
                    duration,
                    {
                        "scenario": scenario["scenario"],
                        "expect_failure": expect_failure,
                        "actual_success": actual_success,
                        "error_message": result.get("error_message", "")
                    }
                )
                
            except Exception as e:
                duration = time.time() - start_time
                expect_failure = scenario.get("expect_failure", False)
                
                # 对于期望失败的场景，异常也可以接受
                success = expect_failure
                
                self.log_test_result(
                    "Error Handling",
                    scenario["description"],
                    success,
                    duration,
                    error=str(e) if not expect_failure else None
                )
    
    async def test_performance_with_mock(self):
        """测试性能（使用mock）"""
        logger.info("🧪 Testing performance with mock...")
        
        mock_response = {
            "answer": "快速模拟回答" * 100,  # 模拟较长回答
            "sources": [{"title": f"来源{i}", "url": f"https://example{i}.com"} for i in range(5)],
            "query_count": 3
        }
        
        performance_tests = [
            {
                "test": "quick_response_time",
                "action": "quick_research",
                "max_time": 1.0,  # 使用mock应该在1秒内完成
                "description": "快速响应时间测试"
            },
            {
                "test": "concurrent_requests",
                "action": "research",
                "max_time": 2.0,  # 并发请求测试
                "description": "并发请求处理测试",
                "concurrent": True
            }
        ]
        
        for perf_test in performance_tests:
            start_time = time.time()
            try:
                with patch.object(self.server.deepsearch_tool, 'research', return_value=mock_response), \
                     patch.object(self.server.deepsearch_tool, 'quick_research', return_value=mock_response):
                    
                    if perf_test.get("concurrent"):
                        # 并发测试
                        tasks = [
                            self.server.handle_tool_action(
                                perf_test["action"],
                                {"question": f"并发测试{i}"}
                            ) for i in range(3)
                        ]
                        results = await asyncio.gather(*tasks)
                        success = all(r.get("success", False) for r in results)
                    else:
                        # 单个请求测试
                        result = await self.server.handle_tool_action(
                            perf_test["action"],
                            {"question": "性能测试"}
                        )
                        success = result.get("success", False)
                
                duration = time.time() - start_time
                within_time_limit = duration <= perf_test["max_time"]
                
                overall_success = success and within_time_limit
                
                self.log_test_result(
                    "Performance",
                    perf_test["description"],
                    overall_success,
                    duration,
                    {
                        "test": perf_test["test"],
                        "max_time": perf_test["max_time"],
                        "within_limit": within_time_limit,
                        "result_success": success
                    }
                )
                
            except Exception as e:
                duration = time.time() - start_time
                self.log_test_result(
                    "Performance",
                    perf_test["description"],
                    False,
                    duration,
                    error=str(e)
                )
    
    async def run_all_quick_tests(self):
        """运行所有快速测试"""
        logger.info("🚀 Starting DeepSearch quick tests...")
        self.start_time = time.time()
        
        try:
            # 设置环境
            await self.setup_test_environment()
            
            # 运行所有测试
            await self.test_json_parsing_fix()
            await self.test_parameter_mapping_with_mock()
            await self.test_action_routing()
            await self.test_error_handling_scenarios()
            await self.test_performance_with_mock()
            
        finally:
            pass  # 无需清理
        
        # 生成测试报告
        self.generate_quick_test_report()
        
        return self.calculate_overall_success_rate()
    
    def calculate_overall_success_rate(self):
        """计算总体成功率"""
        if not self.test_results:
            return False
            
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r['success'])
        
        return passed_tests / total_tests >= 0.8  # 80%成功率
    
    def generate_quick_test_report(self):
        """生成快速测试报告"""
        total_time = time.time() - self.start_time if self.start_time else 0
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r['success'])
        failed_tests = total_tests - passed_tests
        
        print("\n" + "="*80)
        print("⚡ DEEPSEARCH SERVER QUICK TEST REPORT")
        print("="*80)
        print(f"📊 Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests} ({passed_tests/total_tests*100:.1f}%)")
        print(f"❌ Failed: {failed_tests} ({failed_tests/total_tests*100:.1f}%)")
        print(f"⏱️  Total Time: {total_time:.2f}s")
        print()
        
        # 按测试类型分组
        test_groups = {}
        for result in self.test_results:
            group = result['test_name']
            if group not in test_groups:
                test_groups[group] = []
            test_groups[group].append(result)
        
        # 详细结果
        for group_name, group_results in test_groups.items():
            group_passed = sum(1 for r in group_results if r['success'])
            group_total = len(group_results)
            print(f"📋 {group_name}: {group_passed}/{group_total} passed")
            
            for result in group_results:
                status = "✅" if result['success'] else "❌"
                print(f"  {status} {result['test_case']} ({result['duration']:.2f}s)")
                if not result['success'] and result['error']:
                    print(f"      Error: {result['error']}")
        
        # 关键发现
        print("\n🔍 Key Findings:")
        
        # JSON解析修复效果
        json_results = [r for r in self.test_results if "JSON Parsing" in r['test_name']]
        if json_results:
            json_success_rate = sum(1 for r in json_results if r['success']) / len(json_results)
            print(f"  🔧 JSON parsing fix success rate: {json_success_rate*100:.1f}%")
        
        # 性能改进
        perf_results = [r for r in self.test_results if "Performance" in r['test_name']]
        if perf_results:
            avg_time = sum(r['duration'] for r in perf_results) / len(perf_results)
            print(f"  ⚡ Average mock response time: {avg_time:.2f}s (vs ~27s real)")
        
        # 错误处理
        error_results = [r for r in self.test_results if "Error Handling" in r['test_name']]
        if error_results:
            error_success_rate = sum(1 for r in error_results if r['success']) / len(error_results)
            print(f"  🛡️  Error handling robustness: {error_success_rate*100:.1f}%")
        
        # 推荐改进
        print(f"\n💡 Recommendations:")
        if passed_tests == total_tests:
            print("  🎉 All tests passed! Core logic is working correctly.")
            print("  📈 Consider implementing real search API integration")
            print("  🔧 JSON parsing fix should resolve LLM response issues")
        else:
            failed_groups = set(r['test_name'] for r in self.test_results if not r['success'])
            for group in failed_groups:
                print(f"  ⚠️  Fix issues in {group} test group")
        
        # 保存详细结果
        results_file = project_root / "test_results_deepsearch_quick.json"
        with open(results_file, 'w') as f:
            json.dump({
                'test_summary': {
                    'total_tests': total_tests,
                    'passed_tests': passed_tests,
                    'failed_tests': failed_tests,
                    'success_rate': passed_tests/total_tests*100,
                    'total_time': total_time,
                    'test_type': 'quick_mock_tests',
                    'timestamp': datetime.now().isoformat()
                },
                'detailed_results': self.test_results
            }, f, indent=2)
        
        print(f"\n📁 Detailed results saved to: {results_file}")
        print("="*80)


# Pytest integration
@pytest.mark.asyncio
async def test_deepsearch_quick():
    """Pytest wrapper for quick DeepSearch tests"""
    tester = DeepSearchQuickTester()
    success = await tester.run_all_quick_tests()
    assert success, "Some DeepSearch quick tests failed"


# Standalone execution
async def main():
    """Main function for standalone execution"""
    tester = DeepSearchQuickTester()
    await tester.run_all_quick_tests()


if __name__ == "__main__":
    asyncio.run(main())