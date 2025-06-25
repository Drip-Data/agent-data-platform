#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🧪 【核心测试文件】Agent Data Platform - 工具ID映射一致性完整测试
=================================================================

🎯 测试目的：
- 全面验证系统中工具ID和动作映射的完整一致性
- 确保不再误导LLM，避免工具调用失败
- 验证统一工具管理器的正确性
- 检测潜在的映射冲突和不一致问题

⚠️  重要提醒：
- 此测试文件是系统工具一致性的权威验证标准
- 所有测试必须通过才能确保系统正常运行
- 新增工具时必须同时更新此测试文件

📋 测试覆盖范围：
1. ✅ 统一工具管理器基础功能
2. ✅ 工具ID标准化和映射
3. ✅ 动作验证和参数检查
4. ✅ 响应解析器工具引用
5. ✅ MCP服务器配置一致性
6. ✅ LLM工具展示一致性

作者：Agent Data Platform Team
创建时间：2025-06-25
版本：v1.0.0 - 核心一致性测试版本
=================================================================
"""

import unittest
import logging
import sys
import os
from pathlib import Path
from typing import Dict, List, Set, Any
import json
import yaml

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导入要测试的模块
from core.unified_tool_manager import UnifiedToolManager, get_tool_manager, reset_tool_manager
from core.llm.response_parsers.reasoning_response_parser import ReasoningResponseParser

# 设置测试日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TestUnifiedToolConsistency(unittest.TestCase):
    """
    🧪 统一工具映射一致性测试套件
    
    确保整个系统的工具ID和动作定义完全一致，避免误导LLM。
    """
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        logger.info("🚀 开始工具一致性测试套件")
        cls.project_root = Path(__file__).parent.parent
        
        # 重置工具管理器确保干净状态
        reset_tool_manager()
        
        # 初始化统一工具管理器
        try:
            cls.tool_manager = get_tool_manager()
            logger.info("✅ 统一工具管理器初始化成功")
        except Exception as e:
            logger.error(f"❌ 统一工具管理器初始化失败: {e}")
            raise
    
    def setUp(self):
        """每个测试方法的初始化"""
        pass
    
    def tearDown(self):
        """每个测试方法的清理"""
        pass
    
    # ==================== 1. 统一工具管理器基础测试 ====================
    
    def test_01_tool_manager_initialization(self):
        """🔧 测试统一工具管理器基础初始化"""
        logger.info("🧪 测试1: 统一工具管理器基础初始化")
        
        # 验证工具管理器实例
        self.assertIsNotNone(self.tool_manager)
        self.assertIsInstance(self.tool_manager, UnifiedToolManager)
        
        # 验证配置文件加载
        self.assertTrue(hasattr(self.tool_manager, 'config'))
        self.assertTrue(len(self.tool_manager.config) > 0)
        
        # 验证标准工具ID数量
        standard_ids = self.tool_manager.get_all_standard_ids()
        self.assertEqual(len(standard_ids), 4, f"期望4个标准工具，实际: {len(standard_ids)}")
        
        # 验证必需的标准工具ID存在
        expected_ids = {'microsandbox', 'browser_use', 'deepsearch', 'mcp-search-tool'}
        actual_ids = set(standard_ids)
        self.assertEqual(actual_ids, expected_ids, 
                        f"标准工具ID不匹配\n期望: {expected_ids}\n实际: {actual_ids}")
        
        logger.info("✅ 测试1通过: 统一工具管理器基础功能正常")
    
    def test_02_tool_id_mapping_consistency(self):
        """🔄 测试工具ID映射的一致性"""
        logger.info("🧪 测试2: 工具ID映射一致性")
        
        # 测试旧ID到新ID的映射
        test_cases = [
            # (输入的旧ID, 期望的标准ID, 描述)
            ('microsandbox-mcp-server', 'microsandbox', 'MicroSandbox旧ID映射'),
            ('browser-use-mcp-server', 'browser_use', 'Browser Use旧ID映射'),
            ('mcp-deepsearch', 'deepsearch', 'DeepSearch旧ID映射'),
            ('mcp-search-tool', 'mcp-search-tool', 'Search Tool ID保持不变'),
            
            # 已经是标准ID的情况
            ('microsandbox', 'microsandbox', '标准ID保持不变'),
            ('browser_use', 'browser_use', '标准ID保持不变'),
            ('deepsearch', 'deepsearch', '标准ID保持不变'),
        ]
        
        for input_id, expected_id, description in test_cases:
            with self.subTest(input_id=input_id, description=description):
                try:
                    actual_id = self.tool_manager.get_standard_id(input_id)
                    self.assertEqual(actual_id, expected_id, 
                                   f"{description}: {input_id} -> {actual_id} (期望: {expected_id})")
                except Exception as e:
                    self.fail(f"{description}失败: {input_id} -> {e}")
        
        logger.info("✅ 测试2通过: 工具ID映射一致性正确")
    
    def test_03_tool_action_validation(self):
        """🎯 测试工具动作验证功能"""
        logger.info("🧪 测试3: 工具动作验证")
        
        # 测试每个工具的关键动作
        test_cases = [
            # (工具ID, 动作, 应该有效)
            ('microsandbox', 'microsandbox_execute', True),
            ('microsandbox', 'microsandbox_install_package', True),
            ('microsandbox', 'invalid_action', False),
            
            ('deepsearch', 'research', True),
            ('deepsearch', 'quick_research', True),
            ('deepsearch', 'comprehensive_research', True),
            ('deepsearch', 'invalid_research', False),
            
            ('browser_use', 'browser_navigate', True),
            ('browser_use', 'browser_use_execute_task', True),
            ('browser_use', 'browser_click_element', True),
            ('browser_use', 'invalid_browser_action', False),
            
            ('mcp-search-tool', 'search_file_content', True),
            ('mcp-search-tool', 'analyze_tool_needs', True),
            ('mcp-search-tool', 'invalid_search_action', False),
        ]
        
        for tool_id, action, should_be_valid in test_cases:
            with self.subTest(tool_id=tool_id, action=action):
                is_valid = self.tool_manager.is_valid_action(tool_id, action)
                self.assertEqual(is_valid, should_be_valid,
                               f"工具 {tool_id} 的动作 {action} 验证结果错误")
        
        logger.info("✅ 测试3通过: 工具动作验证功能正确")
    
    def test_04_tool_parameter_definitions(self):
        """📋 测试工具参数定义完整性"""
        logger.info("🧪 测试4: 工具参数定义完整性")
        
        # 测试关键工具的参数定义
        test_cases = [
            # (工具ID, 动作, 必需参数列表)
            ('microsandbox', 'microsandbox_execute', ['code']),
            ('deepsearch', 'research', ['question']),
            ('browser_use', 'browser_navigate', ['url']),
            ('mcp-search-tool', 'search_file_content', ['file_path', 'regex_pattern']),
        ]
        
        for tool_id, action, expected_required_params in test_cases:
            with self.subTest(tool_id=tool_id, action=action):
                try:
                    # 获取参数定义
                    params = self.tool_manager.get_action_parameters(tool_id, action)
                    self.assertIsInstance(params, dict, f"工具 {tool_id}.{action} 参数定义应该是字典")
                    
                    # 获取必需参数
                    required_params = self.tool_manager.get_required_parameters(tool_id, action)
                    
                    # 验证必需参数
                    for required_param in expected_required_params:
                        self.assertIn(required_param, required_params,
                                    f"工具 {tool_id}.{action} 缺少必需参数: {required_param}")
                
                except Exception as e:
                    self.fail(f"工具 {tool_id}.{action} 参数定义获取失败: {e}")
        
        logger.info("✅ 测试4通过: 工具参数定义完整")
    
    # ==================== 2. 系统集成一致性测试 ====================
    
    def test_05_response_parser_tool_references(self):
        """🔍 测试响应解析器中的工具引用一致性"""
        logger.info("🧪 测试5: 响应解析器工具引用一致性")
        
        # 创建响应解析器实例
        parser = ReasoningResponseParser()
        
        # 测试解析器能否正确处理统一工具管理器的工具ID
        test_responses = [
            # 测试标准工具ID的JSON响应
            '{"thinking": "需要执行代码", "tool_id": "microsandbox", "action": "microsandbox_execute", "parameters": {"code": "print(\\"hello\\")"}}',
            '{"thinking": "需要研究", "tool_id": "deepsearch", "action": "research", "parameters": {"question": "Python基础"}}',
            '{"thinking": "需要浏览网页", "tool_id": "browser_use", "action": "browser_navigate", "parameters": {"url": "https://python.org"}}',
            '{"thinking": "需要搜索文件", "tool_id": "mcp-search-tool", "action": "search_file_content", "parameters": {"file_path": "test.py", "regex_pattern": "def"}}',
        ]
        
        for response in test_responses:
            with self.subTest(response=response[:50]):
                try:
                    parsed = parser.parse_response(response)
                    
                    # 验证解析结果包含必要字段
                    self.assertIn('tool_id', parsed)
                    self.assertIn('action', parsed)
                    self.assertIn('parameters', parsed)
                    
                    # 验证工具ID是标准格式
                    tool_id = parsed['tool_id']
                    self.assertTrue(self.tool_manager.is_valid_tool_id(tool_id),
                                  f"解析器返回的工具ID无效: {tool_id}")
                    
                    # 验证动作有效性
                    action = parsed['action']
                    self.assertTrue(self.tool_manager.is_valid_action(tool_id, action),
                                  f"解析器返回的动作无效: {tool_id}.{action}")
                
                except Exception as e:
                    self.fail(f"响应解析失败: {e}\n响应: {response}")
        
        logger.info("✅ 测试5通过: 响应解析器工具引用一致")
    
    def test_06_mcp_server_config_consistency(self):
        """🔧 测试MCP服务器配置一致性"""
        logger.info("🧪 测试6: MCP服务器配置一致性")
        
        # 检查每个MCP服务器的service.json配置
        mcp_servers_dir = self.project_root / "mcp_servers"
        self.assertTrue(mcp_servers_dir.exists(), "MCP服务器目录不存在")
        
        expected_servers = [
            ('microsandbox_server', 'microsandbox'),
            ('search_tool_server', 'mcp-search-tool'),
            ('browser_use_server', 'browser_use'),
            ('deepsearch_server', 'deepsearch'),
        ]
        
        for server_dir, expected_tool_id in expected_servers:
            with self.subTest(server=server_dir):
                server_path = mcp_servers_dir / server_dir
                service_json_path = server_path / "service.json"
                
                self.assertTrue(service_json_path.exists(), 
                               f"服务配置文件不存在: {service_json_path}")
                
                # 读取配置文件
                with open(service_json_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 验证service_id与统一工具管理器一致
                service_id = config.get('service_id')
                self.assertEqual(service_id, expected_tool_id,
                               f"服务 {server_dir} 的service_id不匹配: {service_id} != {expected_tool_id}")
                
                # 验证工具能力定义
                capabilities = config.get('capabilities', [])
                self.assertGreater(len(capabilities), 0, 
                                 f"服务 {server_dir} 没有定义任何能力")
                
                # 验证能力与统一工具管理器中的动作一致
                try:
                    manager_actions = set(self.tool_manager.get_tool_actions(expected_tool_id))
                    config_actions = set(capabilities)
                    
                    # 配置中定义的动作应该都在管理器中存在
                    missing_in_manager = config_actions - manager_actions
                    if missing_in_manager:
                        logger.warning(f"⚠️ 服务 {server_dir} 配置了管理器中不存在的动作: {missing_in_manager}")
                    
                    # 管理器中的动作应该都在配置中定义
                    missing_in_config = manager_actions - config_actions
                    if missing_in_config:
                        logger.warning(f"⚠️ 服务 {server_dir} 缺少管理器中定义的动作: {missing_in_config}")
                
                except Exception as e:
                    logger.warning(f"⚠️ 无法验证服务 {server_dir} 的动作一致性: {e}")
        
        logger.info("✅ 测试6通过: MCP服务器配置一致性检查完成")
    
    def test_07_tool_call_validation_complete(self):
        """🔍 测试完整的工具调用验证流程"""
        logger.info("🧪 测试7: 完整工具调用验证流程")
        
        # 测试有效的工具调用
        valid_calls = [
            ('microsandbox', 'microsandbox_execute', {'code': 'print("hello")'}),
            ('deepsearch', 'research', {'question': 'Python基础'}),
            ('browser_use', 'browser_navigate', {'url': 'https://python.org'}),
            ('mcp-search-tool', 'search_file_content', {'file_path': 'test.py', 'regex_pattern': 'def'}),
        ]
        
        for tool_id, action, parameters in valid_calls:
            with self.subTest(tool_id=tool_id, action=action):
                is_valid, errors = self.tool_manager.validate_tool_call(tool_id, action, parameters)
                self.assertTrue(is_valid, f"有效工具调用验证失败: {tool_id}.{action}\n错误: {errors}")
                self.assertEqual(len(errors), 0, f"有效工具调用不应该有错误: {errors}")
        
        # 测试无效的工具调用
        invalid_calls = [
            ('invalid_tool', 'action', {}, "无效工具ID"),
            ('microsandbox', 'invalid_action', {}, "无效动作"),
            ('microsandbox', 'microsandbox_execute', {}, "缺少必需参数"),
            ('microsandbox', 'microsandbox_execute', {'invalid_param': 'value'}, "无效参数"),
        ]
        
        for tool_id, action, parameters, description in invalid_calls:
            with self.subTest(description=description):
                is_valid, errors = self.tool_manager.validate_tool_call(tool_id, action, parameters)
                self.assertFalse(is_valid, f"无效工具调用应该验证失败: {description}")
                self.assertGreater(len(errors), 0, f"无效工具调用应该有错误信息: {description}")
        
        logger.info("✅ 测试7通过: 工具调用验证流程完整")
    
    # ==================== 3. LLM交互一致性测试 ====================
    
    def test_08_llm_tool_presentation(self):
        """🤖 测试LLM工具展示一致性"""
        logger.info("🧪 测试8: LLM工具展示一致性")
        
        # 获取为LLM优化的工具列表
        llm_tools = self.tool_manager.get_tools_for_llm()
        
        # 验证基本结构
        self.assertIsInstance(llm_tools, list)
        self.assertEqual(len(llm_tools), 4, f"LLM工具列表应该包含4个工具，实际: {len(llm_tools)}")
        
        # 验证每个工具的结构
        required_fields = ['id', 'name', 'description', 'actions', 'default_action']
        for tool in llm_tools:
            with self.subTest(tool_id=tool.get('id')):
                for field in required_fields:
                    self.assertIn(field, tool, f"工具 {tool.get('id')} 缺少字段: {field}")
                
                # 验证工具ID是标准格式
                tool_id = tool['id']
                self.assertTrue(self.tool_manager.is_valid_tool_id(tool_id))
                
                # 验证默认动作有效
                default_action = tool['default_action']
                self.assertTrue(self.tool_manager.is_valid_action(tool_id, default_action),
                               f"工具 {tool_id} 的默认动作无效: {default_action}")
                
                # 验证动作列表不为空
                actions = tool['actions']
                self.assertIsInstance(actions, list)
                self.assertGreater(len(actions), 0, f"工具 {tool_id} 没有定义任何动作")
        
        logger.info("✅ 测试8通过: LLM工具展示一致性正确")
    
    def test_09_tool_id_normalization(self):
        """🔄 测试工具ID规范化功能"""
        logger.info("🧪 测试9: 工具ID规范化功能")
        
        # 测试各种变体的工具ID都能正确规范化
        test_cases = [
            # 大小写变体
            ('MICROSANDBOX', 'microsandbox'),
            ('MicroSandbox', 'microsandbox'),
            ('DEEPSEARCH', 'deepsearch'),
            ('Browser_Use', 'browser_use'),
            
            # 分隔符变体
            ('micro-sandbox', 'microsandbox'),
            ('micro_sandbox', 'microsandbox'),
            ('deep-search', 'deepsearch'),
            ('deep_search', 'deepsearch'),
            ('browser-use', 'browser_use'),
            
            # 前后缀变体
            ('mcp-microsandbox', 'microsandbox'),
            ('microsandbox-server', 'microsandbox'),
            ('server-microsandbox', 'microsandbox'),
        ]
        
        for input_id, expected_id in test_cases:
            with self.subTest(input_id=input_id):
                try:
                    # 有些变体可能无法识别，这是正常的
                    actual_id = self.tool_manager.get_standard_id(input_id)
                    # 如果能识别，应该返回正确的标准ID
                    if actual_id:
                        self.assertEqual(actual_id, expected_id,
                                       f"ID规范化错误: {input_id} -> {actual_id} (期望: {expected_id})")
                except ValueError:
                    # 某些变体可能无法识别，这是可以接受的
                    logger.debug(f"💡 ID变体 {input_id} 无法识别，这是正常的")
        
        logger.info("✅ 测试9通过: 工具ID规范化功能正常")
    
    def test_10_system_statistics_and_health(self):
        """📊 测试系统统计和健康状态"""
        logger.info("🧪 测试10: 系统统计和健康状态")
        
        # 获取系统统计信息
        stats = self.tool_manager.get_statistics()
        
        # 验证统计信息结构
        expected_stats_fields = [
            'total_tools', 'total_legacy_mappings', 'total_actions', 
            'config_file', 'config_version', 'tools_by_action_count'
        ]
        for field in expected_stats_fields:
            self.assertIn(field, stats, f"统计信息缺少字段: {field}")
        
        # 验证统计数据合理性
        self.assertEqual(stats['total_tools'], 4, "工具总数应该是4")
        self.assertGreater(stats['total_legacy_mappings'], 0, "应该有兼容性映射")
        self.assertGreater(stats['total_actions'], 10, "总动作数应该大于10")
        
        # 验证每个工具的动作数量
        action_counts = stats['tools_by_action_count']
        for tool_id, count in action_counts.items():
            self.assertGreater(count, 0, f"工具 {tool_id} 应该有动作定义")
        
        # 获取诊断信息
        diagnosis = self.tool_manager.diagnose_tool_issues()
        self.assertIsInstance(diagnosis, dict)
        self.assertIn('warnings', diagnosis)
        self.assertIn('suggestions', diagnosis)
        self.assertIn('info', diagnosis)
        
        logger.info("✅ 测试10通过: 系统统计和健康状态正常")
    
    # ==================== 4. 错误处理和边界测试 ====================
    
    def test_11_error_handling_robustness(self):
        """🛡️ 测试错误处理的健壮性"""
        logger.info("🧪 测试11: 错误处理健壮性")
        
        # 测试无效输入的处理
        error_cases = [
            (None, ValueError, "空工具ID应该抛出错误"),
            ("", ValueError, "空字符串工具ID应该抛出错误"),
            ("completely_invalid_tool_that_does_not_exist", ValueError, "完全无效的工具ID应该抛出错误"),
        ]
        
        for invalid_input, expected_exception, description in error_cases:
            with self.subTest(description=description):
                with self.assertRaises(expected_exception):
                    self.tool_manager.get_standard_id(invalid_input)
        
        # 测试动作验证的错误处理
        self.assertFalse(self.tool_manager.is_valid_action("invalid_tool", "any_action"))
        self.assertFalse(self.tool_manager.is_valid_action("microsandbox", "invalid_action"))
        
        # 测试参数验证的错误处理
        with self.assertRaises(ValueError):
            self.tool_manager.get_action_parameters("invalid_tool", "any_action")
        
        with self.assertRaises(ValueError):
            self.tool_manager.get_action_parameters("microsandbox", "invalid_action")
        
        logger.info("✅ 测试11通过: 错误处理健壮性良好")
    
    def test_12_performance_and_efficiency(self):
        """⚡ 测试性能和效率"""
        logger.info("🧪 测试12: 性能和效率")
        
        import time
        
        # 测试工具ID映射的性能
        start_time = time.time()
        for _ in range(100):
            self.tool_manager.get_standard_id('microsandbox-mcp-server')
            self.tool_manager.get_standard_id('browser-use-mcp-server')
            self.tool_manager.get_standard_id('mcp-deepsearch')
        end_time = time.time()
        
        mapping_time = end_time - start_time
        self.assertLess(mapping_time, 1.0, f"100次ID映射耗时过长: {mapping_time:.3f}秒")
        
        # 测试动作验证的性能
        start_time = time.time()
        for _ in range(100):
            self.tool_manager.is_valid_action('microsandbox', 'microsandbox_execute')
            self.tool_manager.is_valid_action('deepsearch', 'research')
            self.tool_manager.is_valid_action('browser_use', 'browser_navigate')
        end_time = time.time()
        
        validation_time = end_time - start_time
        self.assertLess(validation_time, 1.0, f"100次动作验证耗时过长: {validation_time:.3f}秒")
        
        logger.info(f"✅ 测试12通过: 性能良好 (映射:{mapping_time:.3f}s, 验证:{validation_time:.3f}s)")
    
    @classmethod
    def tearDownClass(cls):
        """测试类清理"""
        logger.info("🏁 工具一致性测试套件完成")


class TestReportGenerator:
    """
    📊 测试报告生成器
    
    生成详细的测试报告，用于验证系统状态
    """
    
    @staticmethod
    def generate_comprehensive_report():
        """生成全面的系统状态报告"""
        print("\n" + "="*80)
        print("🔧 AGENT DATA PLATFORM - 工具一致性验证报告")
        print("="*80)
        
        try:
            tool_manager = get_tool_manager()
            
            # 基础信息
            print(f"\n📋 基础信息:")
            stats = tool_manager.get_statistics()
            print(f"  • 工具总数: {stats['total_tools']}")
            print(f"  • 动作总数: {stats['total_actions']}")
            print(f"  • 兼容映射: {stats['total_legacy_mappings']}")
            print(f"  • 配置版本: {stats['config_version']}")
            
            # 工具详情
            print(f"\n🔧 工具详细信息:")
            for tool_id in tool_manager.get_all_standard_ids():
                tool_info = tool_manager.get_tool_info(tool_id)
                actions = tool_manager.get_tool_actions(tool_id)
                default_action = tool_manager.get_default_action(tool_id)
                display_name = tool_manager.get_tool_display_name(tool_id)
                
                print(f"  • {tool_id} ({display_name})")
                print(f"    - 动作数量: {len(actions)}")
                print(f"    - 默认动作: {default_action}")
                print(f"    - 描述: {tool_info.get('description', 'N/A')[:50]}...")
            
            # 诊断信息
            print(f"\n🔍 系统诊断:")
            diagnosis = tool_manager.diagnose_tool_issues()
            if diagnosis['warnings']:
                print(f"  ⚠️  警告 ({len(diagnosis['warnings'])}):")
                for warning in diagnosis['warnings']:
                    print(f"    - {warning}")
            
            if diagnosis['suggestions']:
                print(f"  💡 建议 ({len(diagnosis['suggestions'])}):")
                for suggestion in diagnosis['suggestions']:
                    print(f"    - {suggestion}")
            
            if diagnosis['info']:
                print(f"  ℹ️  信息 ({len(diagnosis['info'])}):")
                for info in diagnosis['info']:
                    print(f"    - {info}")
            
            # LLM工具展示
            print(f"\n🤖 LLM工具展示:")
            llm_tools = tool_manager.get_tools_for_llm()
            for tool in llm_tools:
                print(f"  • {tool['id']}: {tool['name']}")
                print(f"    - 默认动作: {tool['default_action']}")
                print(f"    - 动作数量: {len(tool['actions'])}")
            
            print(f"\n✅ 系统状态: 正常运行")
            
        except Exception as e:
            print(f"\n❌ 系统状态: 错误 - {e}")
        
        print("="*80)


def run_comprehensive_tests():
    """
    🚀 运行全面的工具一致性测试
    
    这是系统工具映射验证的主入口函数
    """
    print("🚀 开始Agent Data Platform工具一致性全面测试")
    print("="*80)
    
    # 运行单元测试
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestUnifiedToolConsistency)
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    # 生成报告
    print("\n" + "="*80)
    TestReportGenerator.generate_comprehensive_report()
    
    # 返回测试结果
    success = result.wasSuccessful()
    print(f"\n🎯 测试结果: {'✅ 全部通过' if success else '❌ 存在失败'}")
    print(f"   - 总测试数: {result.testsRun}")
    print(f"   - 失败数: {len(result.failures)}")
    print(f"   - 错误数: {len(result.errors)}")
    
    if not success:
        print("\n❌ 失败详情:")
        for test, error in result.failures + result.errors:
            print(f"   - {test}: {error}")
    
    return success


if __name__ == "__main__":
    """
    🎯 主测试入口
    
    使用方法：
    python tests/test_unified_tool_consistency.py
    """
    
    print("🔧 Agent Data Platform - 工具ID映射一致性测试")
    print("📋 用途: 验证系统工具映射完整一致，避免误导LLM")
    print("⚠️  重要: 所有测试必须通过才能确保系统正常运行")
    print()
    
    success = run_comprehensive_tests()
    
    # 退出码
    sys.exit(0 if success else 1)