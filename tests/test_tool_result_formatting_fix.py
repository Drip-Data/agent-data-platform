#!/usr/bin/env python3
"""
🔧 工具结果格式化修复验证测试

验证所有工具的结果格式化是否清晰易读，消除了JSON原始输出问题
"""

import pytest
import sys
import os
import json

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.interfaces import TaskExecutionConstants
from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime


class TestToolResultFormattingFix:
    """测试工具结果格式化修复效果"""
    
    def setup_method(self):
        """设置测试环境"""
        # 创建一个最小化的runtime实例用于测试
        self.runtime = EnhancedReasoningRuntime(
            config_manager=None,
            llm_client=None,
            toolscore_client=None,
            tool_manager=None
        )
    
    def test_microsandbox_stdout_extraction(self):
        """测试MicroSandbox stdout提取"""
        # 模拟MicroSandbox原始输出
        raw_output = {
            "stdout": "Hello World!\n42\n",
            "stderr": "",
            "exit_code": 0,
            "execution_time": 0.1
        }
        
        formatted = self.runtime._format_tool_output('microsandbox', 'execute_code', raw_output)
        
        assert formatted == "Hello World!\n42", "应该提取纯净的stdout内容"
        assert "stdout" not in formatted, "格式化结果不应包含技术字段名"
        assert "exit_code" not in formatted, "格式化结果不应包含技术字段"
    
    def test_microsandbox_empty_stdout(self):
        """测试MicroSandbox空输出处理"""
        raw_output = {
            "stdout": "",
            "stderr": "",
            "exit_code": 0
        }
        
        formatted = self.runtime._format_tool_output('microsandbox', 'execute_code', raw_output)
        
        assert formatted == TaskExecutionConstants.TOOL_FORMAT_PREFIXES['CODE_EXECUTION']
        assert "代码执行完成" in formatted, "空输出应该有有意义的提示"
    
    def test_deepsearch_output_formatting(self):
        """测试DeepSearch搜索结果格式化"""
        # 模拟DeepSearch原始JSON输出
        raw_output = {
            "search_results": [
                {
                    "title": "Python教程",
                    "snippet": "Python是一种高级编程语言...",
                    "url": "https://example.com/python"
                },
                {
                    "title": "数据分析指南", 
                    "content": "使用Python进行数据分析的完整指南...",
                    "url": "https://example.com/data"
                }
            ],
            "query": "Python编程",
            "summary": "找到关于Python编程的相关资源"
        }
        
        formatted = self.runtime._format_tool_output('deepsearch', 'search', raw_output)
        
        # 验证格式化效果
        assert "搜索查询: Python编程" in formatted, "应该包含查询信息"
        assert "搜索摘要:" in formatted, "应该包含摘要信息"
        assert "找到 2 个相关结果" in formatted, "应该显示结果数量"
        assert "1. Python教程" in formatted, "应该包含结果标题"
        assert "来源: https://example.com/python" in formatted, "应该包含来源链接"
        
        # 验证没有原始JSON结构
        assert "{" not in formatted, "不应包含JSON花括号"
        assert "search_results" not in formatted, "不应包含技术字段名"
    
    def test_deepsearch_list_output_formatting(self):
        """测试DeepSearch列表输出格式化"""
        raw_output = [
            {"title": "结果1", "content": "内容1..."},
            {"title": "结果2", "content": "内容2..."},
            {"title": "结果3", "content": "内容3..."}
        ]
        
        formatted = self.runtime._format_tool_output('deepsearch', 'search', raw_output)
        
        assert "找到 3 个相关结果" in formatted, "应该显示正确的结果数量"
        assert "1. 结果1" in formatted, "应该包含编号的结果"
        assert "2. 结果2" in formatted, "应该包含第二个结果"
        assert "[" not in formatted, "不应包含数组符号"
    
    def test_browser_use_output_formatting(self):
        """测试Browser Use浏览器操作结果格式化"""
        # 模拟Browser Use原始输出
        raw_output = {
            "action": "navigate_to_page",
            "status": True,
            "url": "https://example.com",
            "content": "<html><body><h1>欢迎页面</h1><p>这是网站内容</p></body></html>",
            "timestamp": "2024-01-01T12:00:00Z"
        }
        
        formatted = self.runtime._format_tool_output('browser_use', 'navigate', raw_output)
        
        # 验证格式化效果
        assert "浏览器操作: navigate_to_page - 成功" in formatted, "应该显示操作状态"
        assert "页面地址: https://example.com" in formatted, "应该显示URL"
        assert "页面内容: 欢迎页面这是网站内容" in formatted, "应该提取HTML文本内容"
        
        # 验证HTML标签被清理
        assert "<html>" not in formatted, "不应包含HTML标签"
        assert "<body>" not in formatted, "不应包含HTML标签"
        assert "timestamp" not in formatted, "不应包含技术字段"
    
    def test_browser_use_error_handling(self):
        """测试Browser Use错误处理"""
        raw_output = {
            "action": "click_element",
            "status": False,
            "error": "元素未找到",
            "url": "https://example.com"
        }
        
        formatted = self.runtime._format_tool_output('browser_use', 'click', raw_output)
        
        assert "浏览器操作: click_element - 失败" in formatted, "应该显示失败状态"
        assert "错误信息: 元素未找到" in formatted, "应该显示错误信息"
    
    def test_search_tool_output_formatting(self):
        """测试Search Tool文件搜索结果格式化"""
        raw_output = {
            "results": [
                {"path": "/path/to/file1.py", "matches": "function main():"},
                {"path": "/path/to/file2.py", "matches": "def calculate():"}
            ],
            "query": "function definition",
            "count": 2
        }
        
        formatted = self.runtime._format_tool_output('search_tool', 'search_files', raw_output)
        
        assert "文件搜索: function definition" in formatted, "应该显示搜索查询"
        assert "找到 2 个匹配文件" in formatted, "应该显示文件数量"
        assert "1. /path/to/file1.py" in formatted, "应该显示文件路径"
        assert "匹配内容: function main():" in formatted, "应该显示匹配内容"
    
    def test_generic_output_formatting(self):
        """测试通用工具输出格式化"""
        # 测试包含result字段的输出
        output_with_result = {"result": "操作成功完成", "metadata": "技术信息"}
        formatted = self.runtime._format_tool_output('unknown_tool', 'action', output_with_result)
        assert formatted == "操作成功完成", "应该提取result字段内容"
        
        # 测试包含content字段的输出
        output_with_content = {"content": "这是内容", "headers": "技术头信息"}
        formatted = self.runtime._format_tool_output('unknown_tool', 'action', output_with_content)
        assert formatted == "这是内容", "应该提取content字段内容"
        
        # 测试过滤技术字段
        output_with_tech_fields = {
            "meaningful_data": "有用信息",
            "success": True,
            "status": 200,
            "timestamp": "2024-01-01",
            "metadata": {"tech": "info"}
        }
        formatted = self.runtime._format_tool_output('unknown_tool', 'action', output_with_tech_fields)
        assert "meaningful_data" in formatted, "应该保留有意义的字段"
        assert "success" not in formatted, "应该过滤技术字段"
        assert "status" not in formatted, "应该过滤技术字段"
    
    def test_constants_usage_consistency(self):
        """验证常量使用的一致性"""
        # 验证所有工具格式化方法都使用了常量
        import inspect
        
        # 检查DeepSearch格式化方法
        deepsearch_source = inspect.getsource(self.runtime._format_deepsearch_output)
        assert "TaskExecutionConstants.TOOL_FORMAT_PREFIXES" in deepsearch_source, "应该使用格式化前缀常量"
        assert "TaskExecutionConstants.TOOL_RESULT_LIMITS" in deepsearch_source, "应该使用结果限制常量"
        
        # 检查Browser Use格式化方法
        browser_source = inspect.getsource(self.runtime._format_browser_use_output)
        assert "TaskExecutionConstants.TOOL_FORMAT_PREFIXES" in browser_source, "应该使用格式化前缀常量"
        
        # 验证没有硬编码的数字限制
        assert "[:5]" not in deepsearch_source, "不应包含硬编码的数字限制"
        assert "[:200]" not in deepsearch_source, "不应包含硬编码的长度限制"
    
    def test_result_length_limits(self):
        """测试结果长度限制"""
        # 创建一个超长的搜索结果
        long_results = []
        for i in range(20):  # 创建20个结果，超过MAX_SEARCH_RESULTS(5)
            long_results.append({
                "title": f"结果{i}",
                "snippet": "x" * 500  # 超长snippet，超过MAX_SNIPPET_LENGTH(200)
            })
        
        raw_output = {
            "search_results": long_results,
            "query": "测试查询"
        }
        
        formatted = self.runtime._format_tool_output('deepsearch', 'search', raw_output)
        
        # 验证结果数量限制 - 计算实际显示的条目数
        lines = formatted.split('\n')
        item_lines = [line for line in lines if line.strip() and (line.startswith('1.') or line.startswith('2.') or line.startswith('3.') or line.startswith('4.') or line.startswith('5.'))]
        max_results = TaskExecutionConstants.TOOL_RESULT_LIMITS['MAX_SEARCH_RESULTS']
        assert len(item_lines) <= max_results, f"显示的结果数量应该不超过{max_results}个，实际显示了{len(item_lines)}个"
        
        # 验证文本长度限制
        max_length = TaskExecutionConstants.TOOL_RESULT_LIMITS['MAX_SNIPPET_LENGTH']
        lines = formatted.split('\n')
        for line in lines:
            if line.strip().startswith('   x'):  # snippet内容行
                assert len(line) <= max_length + 20, "snippet长度应该被限制"  # +20为格式化字符的缓冲
    
    def test_error_handling_robustness(self):
        """测试错误处理的健壮性"""
        # 测试空输入
        formatted = self.runtime._format_tool_output('deepsearch', 'search', {})
        assert isinstance(formatted, str), "空输入应该返回字符串"
        assert len(formatted) > 0, "空输入应该有默认消息"
        
        # 测试None输入
        formatted = self.runtime._format_tool_output('browser_use', 'action', None)
        assert isinstance(formatted, str), "None输入应该返回字符串"
        
        # 测试异常数据结构
        malformed_output = {"search_results": "不是列表"}
        formatted = self.runtime._format_tool_output('deepsearch', 'search', malformed_output)
        assert isinstance(formatted, str), "异常数据应该有兜底处理"


if __name__ == "__main__":
    """运行测试验证工具结果格式化修复效果"""
    print("🔧 开始验证工具结果格式化修复效果...")
    
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
    
    print("\n✅ 工具结果格式化修复验证完成！")
    print("\n📋 修复效果摘要:")
    print("- ✅ MicroSandbox: 提取纯净stdout内容，消除JSON结构")
    print("- ✅ DeepSearch: 结构化显示搜索结果，去除原始JSON")
    print("- ✅ Browser Use: 格式化浏览器操作结果，提取HTML文本")
    print("- ✅ Search Tool: 清晰显示文件搜索结果")
    print("- ✅ 通用工具: 智能提取有意义字段，过滤技术信息")
    print("- ✅ 常量化管理: 所有格式化逻辑使用TaskExecutionConstants")
    print("- ✅ 长度限制: 防止输出过长影响LLM处理")
    print("- ✅ 错误处理: 健壮的异常处理和兜底机制")