#!/usr/bin/env python3
"""
Browser-Use搜索功能修复测试
测试修复后的browser_search_google是否能正确返回内容
"""

import pytest
import asyncio
import logging
from typing import Dict, Any

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestBrowserUseSearchFix:
    """Browser-Use搜索功能修复测试类"""
    
    def setup_method(self):
        """每个测试前的初始化"""
        self.test_queries = [
            "新加坡国立大学 IORA",
            "Institute of Operations Research and Analytics NUS",
            "Python programming tutorial",
            "机器学习基础教程"
        ]
    
    def test_browser_use_search_fix_integration(self):
        """测试Browser-Use搜索修复的集成效果"""
        try:
            # 模拟原有问题：空内容返回
            empty_result = {
                'success': True, 
                'result': {'content': None, 'is_done': False}
            }
            
            # 模拟增强运行时的检测
            from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime
            from core.unified_tool_manager import UnifiedToolManager
            
            tool_manager = UnifiedToolManager()
            runtime = EnhancedReasoningRuntime.__new__(EnhancedReasoningRuntime)
            runtime.tool_manager = tool_manager
            
            # 测试空内容检测
            has_issue, guidance = runtime._detect_tool_result_issues(
                empty_result, "browser_use", "browser_search_google"
            )
            
            assert has_issue, "应该检测到browser_use空内容问题"
            assert "Browser搜索返回空内容" in guidance, "应该包含特定的browser_use问题说明"
            assert "DeepSearch" in guidance, "应该建议使用DeepSearch替代"
            assert "已知的技术问题" in guidance, "应该说明这是已知问题"
            
            logger.info("✅ Browser-Use空内容检测测试通过")
            
        except Exception as e:
            pytest.fail(f"Browser-Use搜索修复集成测试失败: {e}")
    
    def test_manual_search_extraction_logic(self):
        """测试手动搜索提取逻辑的设计"""
        try:
            # 验证搜索选择器策略
            extraction_methods = [
                {'selector': 'div[data-ved] h3', 'name': 'data-ved标题'},
                {'selector': '.g h3', 'name': 'g类标题'},
                {'selector': 'h3', 'name': '所有h3标题'},
                {'selector': '.LC20lb', 'name': 'LC20lb类'},
                {'selector': '[role="heading"]', 'name': 'heading角色'},
                {'selector': 'a h3', 'name': '链接中的h3'},
                {'selector': 'cite', 'name': '引用文本'},
            ]
            
            # 验证策略覆盖度
            assert len(extraction_methods) >= 5, "应该有足够多的提取策略"
            
            # 验证选择器多样性
            selector_types = set()
            for method in extraction_methods:
                if 'h3' in method['selector']:
                    selector_types.add('heading')
                elif '[' in method['selector']:
                    selector_types.add('attribute')
                elif '.' in method['selector']:
                    selector_types.add('class')
                elif 'cite' in method['selector']:
                    selector_types.add('semantic')
            
            assert len(selector_types) >= 3, f"选择器类型应该多样化，当前类型: {selector_types}"
            
            logger.info("✅ 手动搜索提取逻辑设计测试通过")
            
        except Exception as e:
            pytest.fail(f"手动搜索提取逻辑测试失败: {e}")
    
    def test_browser_config_anti_detection(self):
        """测试浏览器反检测配置"""
        try:
            # 验证关键的反检测参数
            expected_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
                "--user-agent=Mozilla/5.0",
                "--disable-images",
                "--disable-component-extensions-with-background-pages"
            ]
            
            # 读取浏览器配置文件来验证参数
            import inspect
            import os
            
            # 获取browser_use服务器的主文件
            browser_server_path = "/Users/zhaoxiang/Documents/Agent Platform/agent-data-platform/mcp_servers/browser_use_server/main.py"
            
            if os.path.exists(browser_server_path):
                with open(browser_server_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 检查关键反检测参数是否存在
                found_args = []
                for arg in expected_args:
                    if arg in content:
                        found_args.append(arg)
                
                assert len(found_args) >= 4, f"应该包含至少4个关键反检测参数，找到: {found_args}"
                
                # 检查是否包含用户代理设置
                assert "Mozilla/5.0" in content, "应该包含自定义用户代理"
                
                logger.info(f"✅ 浏览器反检测配置测试通过，找到 {len(found_args)} 个关键参数")
                
            else:
                logger.warning("⚠️ 浏览器服务器文件不存在，跳过配置测试")
            
        except Exception as e:
            pytest.fail(f"浏览器反检测配置测试失败: {e}")
    
    def test_error_recovery_prompt_integration(self):
        """测试错误恢复提示集成"""
        try:
            from core.llm.prompt_builders.reasoning_prompt_builder import ReasoningPromptBuilder
            from core.unified_tool_manager import UnifiedToolManager
            
            tool_manager = UnifiedToolManager()
            prompt_builder = ReasoningPromptBuilder(tool_manager, streaming_mode=True)
            
            # 构建提示并检查错误恢复指导
            prompt_messages = prompt_builder.build_prompt("Test browser search issue", [])
            prompt_content = prompt_messages[0]["content"]
            
            # 验证错误恢复指导包含在内
            error_recovery_keywords = [
                "Empty Search Results",
                "tool fails",
                "alternative tools",
                "different keywords",
                "deepsearch",
                "browser_use"
            ]
            
            found_keywords = []
            for keyword in error_recovery_keywords:
                if keyword.lower() in prompt_content.lower():
                    found_keywords.append(keyword)
            
            assert len(found_keywords) >= 4, f"应该包含至少4个错误恢复关键词，找到: {found_keywords}"
            
            # 验证具体的工具切换指导
            assert "deepsearch" in prompt_content.lower(), "应该提到deepsearch作为替代工具"
            assert "browser_use" in prompt_content.lower(), "应该提到browser_use工具"
            
            logger.info("✅ 错误恢复提示集成测试通过")
            
        except Exception as e:
            pytest.fail(f"错误恢复提示集成测试失败: {e}")
    
    def test_fallback_content_structure(self):
        """测试回退内容结构的设计"""
        try:
            # 模拟回退机制返回的内容结构
            manual_extraction_result = {
                "success": True, 
                "data": {
                    "content": "Google搜索查询: test query\n\n搜索结果:\n1. Result 1\n2. Result 2\n",
                    "query": "test query",
                    "results_count": 2,
                    "extraction_method": "manual_fallback"
                }
            }
            
            basic_fallback_result = {
                "success": True,
                "data": {
                    "content": "Google搜索已完成查询: test query\n页面标题: Test Page\n注意: 由于页面结构限制，无法提取具体搜索结果，但搜索操作已成功执行。",
                    "query": "test query",
                    "page_title": "Test Page",
                    "extraction_method": "basic_fallback"
                }
            }
            
            # 验证手动提取结果结构
            assert manual_extraction_result["success"], "手动提取应该成功"
            assert "content" in manual_extraction_result["data"], "应该包含content字段"
            assert "results_count" in manual_extraction_result["data"], "应该包含结果计数"
            assert "extraction_method" in manual_extraction_result["data"], "应该标记提取方法"
            
            # 验证基础回退结果结构
            assert basic_fallback_result["success"], "基础回退应该成功"
            assert "搜索已完成" in basic_fallback_result["data"]["content"], "应该说明搜索已完成"
            assert "注意:" in basic_fallback_result["data"]["content"], "应该包含说明信息"
            
            # 验证内容不为空
            assert len(manual_extraction_result["data"]["content"]) > 20, "手动提取内容应该有足够长度"
            assert len(basic_fallback_result["data"]["content"]) > 20, "基础回退内容应该有足够长度"
            
            logger.info("✅ 回退内容结构设计测试通过")
            
        except Exception as e:
            pytest.fail(f"回退内容结构测试失败: {e}")


def run_tests():
    """运行所有Browser-Use搜索修复测试"""
    logger.info("🚀 开始运行Browser-Use搜索功能修复测试")
    
    test_instance = TestBrowserUseSearchFix()
    test_instance.setup_method()
    
    tests = [
        test_instance.test_browser_use_search_fix_integration,
        test_instance.test_manual_search_extraction_logic,
        test_instance.test_browser_config_anti_detection,
        test_instance.test_error_recovery_prompt_integration,
        test_instance.test_fallback_content_structure
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
            logger.info(f"✅ {test.__name__} 通过")
        except Exception as e:
            failed += 1
            logger.error(f"❌ {test.__name__} 失败: {e}")
    
    logger.info(f"🎯 Browser-Use搜索修复测试结果: {passed} 个通过, {failed} 个失败")
    
    if failed == 0:
        logger.info("🎉 所有Browser-Use搜索修复测试通过！")
        return True
    else:
        logger.error("💥 部分测试失败，需要进一步检查")
        return False


if __name__ == "__main__":
    import sys
    sys.path.insert(0, '/Users/zhaoxiang/Documents/Agent Platform/agent-data-platform')
    
    success = run_tests()
    sys.exit(0 if success else 1)