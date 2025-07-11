#!/usr/bin/env python3
"""
DeepSearch Server 综合测试套件
测试深度搜索服务器的所有功能、错误处理和配置一致性
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

try:
    from mcp_servers.deepsearch_server.main import DeepSearchMCPServer
    from mcp_servers.deepsearch_server.deepsearch_tool_unified import DeepSearchToolUnified
    from core.config_manager import ConfigManager
    from core.llm_client import LLMClient
except ImportError as e:
    print(f"Import error: {e}")
    print("Please ensure all required modules are available")
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DeepSearchServerTester:
    """DeepSearch Server 综合测试器"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.server = None
        self.test_results = []
        self.start_time = None
        
    async def setup_test_environment(self):
        """设置测试环境"""
        logger.info("🔧 Setting up DeepSearch server test environment...")
        
        try:
            # Initialize server
            self.server = DeepSearchMCPServer(self.config_manager)
            logger.info("✅ DeepSearch server initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize DeepSearch server: {e}")
            raise
        
        logger.info("✅ DeepSearch test environment setup complete")
        
    async def cleanup_test_environment(self):
        """清理测试环境"""
        logger.info("🧹 Cleaning up DeepSearch test environment...")
        
        # 目前无需特殊清理操作
        
        logger.info("✅ DeepSearch test environment cleanup complete")
        
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
    
    async def test_server_initialization(self):
        """测试服务器初始化"""
        logger.info("🧪 Testing server initialization...")
        
        test_cases = [
            {
                "case": "basic_initialization",
                "description": "基础初始化测试"
            },
            {
                "case": "config_loading",
                "description": "配置加载测试"
            },
            {
                "case": "llm_client_setup",
                "description": "LLM客户端设置测试"
            }
        ]
        
        for test_case in test_cases:
            start_time = time.time()
            try:
                case_name = test_case["case"]
                
                if case_name == "basic_initialization":
                    # 检查服务器基本属性
                    success = (
                        hasattr(self.server, 'config_manager') and
                        hasattr(self.server, 'server_name') and
                        hasattr(self.server, 'server_id') and
                        self.server.server_id == "deepsearch"
                    )
                    
                elif case_name == "config_loading":
                    # 检查配置加载
                    llm_config = self.config_manager.get_llm_config()
                    success = (
                        llm_config is not None and
                        hasattr(llm_config, 'provider')
                    )
                    
                elif case_name == "llm_client_setup":
                    # 测试LLM客户端创建
                    llm_config = self.config_manager.get_llm_config()
                    llm_client = LLMClient(llm_config)
                    success = llm_client is not None
                    
                duration = time.time() - start_time
                
                self.log_test_result(
                    "Server Initialization",
                    test_case["description"],
                    success,
                    duration,
                    {"case": case_name}
                )
                
            except Exception as e:
                duration = time.time() - start_time
                self.log_test_result(
                    "Server Initialization",
                    test_case["description"],
                    False,
                    duration,
                    error=str(e)
                )
    
    async def test_action_execution(self):
        """测试动作执行"""
        logger.info("🧪 Testing action execution...")
        
        test_actions = [
            {
                "action": "research",
                "parameters": {"question": "什么是人工智能？"},
                "description": "基础研究测试"
            },
            {
                "action": "quick_research", 
                "parameters": {"question": "Python编程语言的特点"},
                "description": "快速研究测试"
            },
            {
                "action": "comprehensive_research",
                "parameters": {
                    "question": "机器学习在医疗领域的应用",
                    "topic_focus": "医疗诊断"
                },
                "description": "全面研究测试"
            }
        ]
        
        for test_action in test_actions:
            start_time = time.time()
            try:
                result = await self.server.handle_tool_action(
                    test_action["action"],
                    test_action["parameters"]
                )
                
                # 检查结果结构
                success = (
                    isinstance(result, dict) and
                    "success" in result and
                    "data" in result
                )
                
                if success and result.get("success"):
                    # 检查返回数据质量
                    data = result.get("data", {})
                    success = (
                        isinstance(data, dict) and
                        "answer" in data and
                        len(str(data.get("answer", ""))) > 50  # 确保有实质内容
                    )
                
                duration = time.time() - start_time
                
                self.log_test_result(
                    "Action Execution",
                    test_action["description"],
                    success,
                    duration,
                    {
                        "action": test_action["action"],
                        "parameters": test_action["parameters"],
                        "result_success": result.get("success"),
                        "result_size": len(str(result.get("data", {})))
                    }
                )
                
            except Exception as e:
                duration = time.time() - start_time
                self.log_test_result(
                    "Action Execution",
                    test_action["description"],
                    False,
                    duration,
                    error=str(e)
                )
    
    async def test_parameter_handling(self):
        """测试参数处理"""
        logger.info("🧪 Testing parameter handling...")
        
        test_cases = [
            {
                "case": "parameter_mapping",
                "action": "research",
                "parameters": {"query": "测试查询"},  # 使用query而非question
                "description": "参数映射测试(query->question)"
            },
            {
                "case": "parameter_mapping_task",
                "action": "research", 
                "parameters": {"task_description": "分析AI发展趋势"},  # 使用task_description
                "description": "参数映射测试(task_description->question)"
            },
            {
                "case": "optional_parameters",
                "action": "research",
                "parameters": {
                    "question": "机器学习算法",
                    "max_loops": 2,
                    "reasoning_model": "gemini-1.5-pro"
                },
                "description": "可选参数测试"
            },
            {
                "case": "missing_required_param",
                "action": "research",
                "parameters": {},  # 缺少必需参数
                "description": "缺少必需参数测试",
                "expect_failure": True
            },
            {
                "case": "invalid_action",
                "action": "invalid_research_action",
                "parameters": {"question": "测试"},
                "description": "无效动作测试",
                "expect_failure": True
            }
        ]
        
        for test_case in test_cases:
            start_time = time.time()
            try:
                result = await self.server.handle_tool_action(
                    test_case["action"],
                    test_case["parameters"]
                )
                
                expect_failure = test_case.get("expect_failure", False)
                
                if expect_failure:
                    # 应该失败的测试
                    success = not result.get("success", False)
                else:
                    # 应该成功的测试
                    success = result.get("success", False)
                
                duration = time.time() - start_time
                
                self.log_test_result(
                    "Parameter Handling",
                    test_case["description"],
                    success,
                    duration,
                    {
                        "case": test_case["case"],
                        "expect_failure": expect_failure,
                        "actual_success": result.get("success"),
                        "error_message": result.get("error_message", "")
                    }
                )
                
            except Exception as e:
                duration = time.time() - start_time
                expect_failure = test_case.get("expect_failure", False)
                
                # 对于预期失败的测试，异常也算成功
                success = expect_failure
                
                self.log_test_result(
                    "Parameter Handling",
                    test_case["description"],
                    success,
                    duration,
                    error=str(e) if not expect_failure else None
                )
    
    async def test_error_handling(self):
        """测试错误处理"""
        logger.info("🧪 Testing error handling...")
        
        # 模拟各种错误场景
        error_scenarios = [
            {
                "scenario": "llm_client_failure",
                "description": "LLM客户端失败处理",
                "mock_target": "core.llm_client.LLMClient.call",
                "mock_side_effect": Exception("Simulated LLM failure")
            },
            {
                "scenario": "json_parsing_error",
                "description": "JSON解析错误处理",
                "mock_target": "json.loads",
                "mock_side_effect": json.JSONDecodeError("Invalid JSON", "", 0)
            }
        ]
        
        for scenario in error_scenarios:
            start_time = time.time()
            try:
                with patch(scenario["mock_target"], side_effect=scenario["mock_side_effect"]):
                    result = await self.server.handle_tool_action(
                        "research",
                        {"question": "测试错误处理"}
                    )
                    
                    # 错误应该被正确处理，返回失败结果而不是抛出异常
                    success = (
                        isinstance(result, dict) and
                        not result.get("success", True) and
                        "error_message" in result
                    )
                
                duration = time.time() - start_time
                
                self.log_test_result(
                    "Error Handling",
                    scenario["description"],
                    success,
                    duration,
                    {
                        "scenario": scenario["scenario"],
                        "error_caught": not result.get("success", True),
                        "error_message": result.get("error_message", "")
                    }
                )
                
            except Exception as e:
                duration = time.time() - start_time
                # 如果还是抛出异常，说明错误处理不够好
                self.log_test_result(
                    "Error Handling",
                    scenario["description"],
                    False,
                    duration,
                    error=str(e)
                )
    
    async def test_configuration_consistency(self):
        """测试配置一致性"""
        logger.info("🧪 Testing configuration consistency...")
        
        start_time = time.time()
        try:
            # 读取service.json
            service_json_path = project_root / "mcp_servers" / "deepsearch_server" / "service.json"
            unified_config_path = project_root / "config" / "unified_tool_definitions.yaml"
            
            consistency_checks = {}
            
            if service_json_path.exists():
                with open(service_json_path, 'r', encoding='utf-8') as f:
                    service_config = json.load(f)
                
                # 检查基本配置
                consistency_checks.update({
                    "service_id_matches": service_config.get("service_id") == "deepsearch",
                    "port_defined": "port" in service_config,
                    "capabilities_defined": "capabilities" in service_config,
                    "actions_count": len(service_config.get("capabilities", [])) >= 3
                })
                
                # 检查动作定义
                capabilities = service_config.get("capabilities", [])
                action_names = [cap.get("name") for cap in capabilities]
                expected_actions = ["research", "quick_research", "comprehensive_research"]
                
                consistency_checks.update({
                    "all_actions_present": all(action in action_names for action in expected_actions)
                })
            else:
                consistency_checks["service_json_exists"] = False
            
            if unified_config_path.exists():
                import yaml
                with open(unified_config_path, 'r', encoding='utf-8') as f:
                    unified_config = yaml.safe_load(f)
                
                deepsearch_config = unified_config.get("tools", {}).get("deepsearch", {})
                
                consistency_checks.update({
                    "unified_config_exists": True,
                    "unified_id_matches": deepsearch_config.get("id") == "deepsearch",
                    "unified_actions_defined": "actions" in deepsearch_config
                })
            else:
                consistency_checks["unified_config_exists"] = False
            
            # 总体一致性评分
            consistency_score = sum(consistency_checks.values()) / len(consistency_checks)
            success = consistency_score >= 0.8
            
            duration = time.time() - start_time
            
            self.log_test_result(
                "Configuration Consistency",
                "配置文件一致性检查",
                success,
                duration,
                {
                    "consistency_score": consistency_score,
                    "checks": consistency_checks,
                    "missing_checks": [k for k, v in consistency_checks.items() if not v]
                }
            )
            
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result(
                "Configuration Consistency",
                "配置文件一致性检查",
                False,
                duration,
                error=str(e)
            )
    
    async def test_tool_implementation_consistency(self):
        """测试工具实现一致性"""
        logger.info("🧪 Testing tool implementation consistency...")
        
        start_time = time.time()
        try:
            # 检查工具实现文件
            tool_files_checks = {}
            
            # 检查统一工具实现
            unified_tool_path = project_root / "mcp_servers" / "deepsearch_server" / "deepsearch_tool_unified.py"
            if unified_tool_path.exists():
                tool_files_checks["unified_tool_exists"] = True
                
                # 创建工具实例测试
                try:
                    llm_config = self.config_manager.get_llm_config()
                    llm_client = LLMClient(llm_config)
                    tool = DeepSearchToolUnified(llm_client)
                    
                    tool_files_checks.update({
                        "tool_instantiation": True,
                        "has_research_method": hasattr(tool, 'research'),
                        "has_quick_research_method": hasattr(tool, 'quick_research'),
                        "has_comprehensive_research_method": hasattr(tool, 'comprehensive_research')
                    })
                except Exception as e:
                    tool_files_checks["tool_instantiation"] = False
                    tool_files_checks["instantiation_error"] = str(e)
            else:
                tool_files_checks["unified_tool_exists"] = False
            
            # 检查原始工具实现
            original_tool_path = project_root / "mcp_servers" / "deepsearch_server" / "deepsearch_tool.py"
            tool_files_checks["original_tool_exists"] = original_tool_path.exists()
            
            consistency_score = sum(v for v in tool_files_checks.values() if isinstance(v, bool)) / sum(1 for v in tool_files_checks.values() if isinstance(v, bool))
            success = consistency_score >= 0.8
            
            duration = time.time() - start_time
            
            self.log_test_result(
                "Tool Implementation Consistency",
                "工具实现一致性检查",
                success,
                duration,
                {
                    "consistency_score": consistency_score,
                    "checks": tool_files_checks
                }
            )
            
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result(
                "Tool Implementation Consistency",
                "工具实现一致性检查",
                False,
                duration,
                error=str(e)
            )
    
    async def test_performance_benchmarks(self):
        """测试性能基准"""
        logger.info("🧪 Testing performance benchmarks...")
        
        benchmark_tests = [
            {
                "test": "simple_research_speed",
                "action": "quick_research",
                "parameters": {"question": "什么是Python?"},
                "max_time": 30.0,  # 30秒内完成
                "description": "简单研究速度测试"
            },
            {
                "test": "complex_research_speed", 
                "action": "comprehensive_research",
                "parameters": {
                    "question": "人工智能在医疗诊断中的应用和挑战",
                    "topic_focus": "医疗AI"
                },
                "max_time": 60.0,  # 60秒内完成
                "description": "复杂研究速度测试"
            }
        ]
        
        for benchmark in benchmark_tests:
            start_time = time.time()
            try:
                result = await self.server.handle_tool_action(
                    benchmark["action"],
                    benchmark["parameters"]
                )
                
                duration = time.time() - start_time
                
                # 检查是否在时间限制内完成且成功
                success = (
                    duration <= benchmark["max_time"] and
                    result.get("success", False)
                )
                
                self.log_test_result(
                    "Performance Benchmarks",
                    benchmark["description"],
                    success,
                    duration,
                    {
                        "test": benchmark["test"],
                        "max_time": benchmark["max_time"],
                        "actual_time": duration,
                        "within_limit": duration <= benchmark["max_time"],
                        "result_success": result.get("success")
                    }
                )
                
            except Exception as e:
                duration = time.time() - start_time
                self.log_test_result(
                    "Performance Benchmarks",
                    benchmark["description"],
                    False,
                    duration,
                    error=str(e)
                )
    
    async def run_all_tests(self):
        """运行所有测试"""
        logger.info("🚀 Starting comprehensive DeepSearch server tests...")
        self.start_time = time.time()
        
        try:
            # 设置环境
            await self.setup_test_environment()
            
            # 运行所有测试套件
            await self.test_server_initialization()
            await self.test_action_execution()
            await self.test_parameter_handling()
            await self.test_error_handling()
            await self.test_configuration_consistency()
            await self.test_tool_implementation_consistency()
            await self.test_performance_benchmarks()
            
        finally:
            # 清理环境
            await self.cleanup_test_environment()
        
        # 生成测试报告
        self.generate_test_report()
        
        return self.calculate_overall_success_rate()
    
    def calculate_overall_success_rate(self):
        """计算总体成功率"""
        if not self.test_results:
            return False
            
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r['success'])
        
        return passed_tests / total_tests >= 0.7  # 70%成功率
    
    def generate_test_report(self):
        """生成测试报告"""
        total_time = time.time() - self.start_time if self.start_time else 0
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r['success'])
        failed_tests = total_tests - passed_tests
        
        print("\n" + "="*80)
        print("🔍 DEEPSEARCH SERVER TEST REPORT")
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
        
        # 性能分析
        perf_results = [r for r in self.test_results if "Performance" in r['test_name']]
        if perf_results:
            avg_time = sum(r['duration'] for r in perf_results) / len(perf_results)
            print(f"  ⚡ Average response time: {avg_time:.2f}s")
            
        # 配置问题
        config_results = [r for r in self.test_results if "Configuration" in r['test_name']]
        config_issues = [r for r in config_results if not r['success']]
        if config_issues:
            print(f"  ⚠️  Configuration issues detected: {len(config_issues)}")
            
        # 错误处理
        error_results = [r for r in self.test_results if "Error Handling" in r['test_name']]
        error_success_rate = sum(1 for r in error_results if r['success']) / len(error_results) if error_results else 0
        print(f"  🛡️  Error handling success rate: {error_success_rate*100:.1f}%")
        
        # 保存详细结果
        results_file = project_root / "test_results_deepsearch_server.json"
        with open(results_file, 'w') as f:
            json.dump({
                'test_summary': {
                    'total_tests': total_tests,
                    'passed_tests': passed_tests,
                    'failed_tests': failed_tests,
                    'success_rate': passed_tests/total_tests*100,
                    'total_time': total_time,
                    'test_timestamp': datetime.now().isoformat()
                },
                'detailed_results': self.test_results
            }, f, indent=2)
        
        print(f"\n📁 Detailed results saved to: {results_file}")
        print("="*80)


# Pytest integration
@pytest.mark.asyncio
async def test_deepsearch_server_comprehensive():
    """Pytest wrapper for comprehensive DeepSearch tests"""
    tester = DeepSearchServerTester()
    success = await tester.run_all_tests()
    assert success, "Some DeepSearch server tests failed"


# Standalone execution
async def main():
    """Main function for standalone execution"""
    tester = DeepSearchServerTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())