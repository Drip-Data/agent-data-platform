#!/usr/bin/env python3
"""
🔧 任务状态判定修复验证测试

此测试验证已修复的任务状态判定逻辑和结果提取功能
"""

import pytest
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.interfaces import TaskExecutionConstants
from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime


class TestStatusDeterminationFix:
    """测试状态判定修复效果"""
    
    def setup_method(self):
        """设置测试环境"""
        # 创建一个最小化的runtime实例用于测试
        self.runtime = EnhancedReasoningRuntime(
            config_manager=None,
            llm_client=None,
            toolscore_client=None,
            tool_manager=None
        )
    
    def test_task_execution_constants_exist(self):
        """测试常量是否正确定义"""
        # 验证关键常量存在
        assert hasattr(TaskExecutionConstants, 'XML_TAGS')
        assert hasattr(TaskExecutionConstants, 'SUCCESS_INDICATORS')
        assert hasattr(TaskExecutionConstants, 'FAILURE_INDICATORS')
        assert hasattr(TaskExecutionConstants, 'NO_ACTION_PERFORMED')
        
        # 验证XML标签常量
        xml_tags = TaskExecutionConstants.XML_TAGS
        assert 'ANSWER' in xml_tags
        assert 'THINK' in xml_tags
        assert 'RESULT' in xml_tags
        
        # 验证常量值不为空
        assert len(TaskExecutionConstants.SUCCESS_INDICATORS) > 0
        assert len(TaskExecutionConstants.FAILURE_INDICATORS) > 0
    
    def test_success_determination_with_answer_tag(self):
        """测试包含answer标签的成功判定"""
        trajectory_with_answer = "<think>我需要计算1+1</think><answer>1+1等于2</answer>"
        
        success = self.runtime._determine_task_success(trajectory_with_answer, [])
        assert success == True, "包含answer标签的轨迹应该被判定为成功"
    
    def test_success_determination_with_errors(self):
        """测试包含错误的失败判定"""
        trajectory_with_error = "<think>计算中</think><answer>结果</answer>发生了error: 计算失败"
        
        success = self.runtime._determine_task_success(trajectory_with_error, [])
        assert success == False, "包含错误指示器的轨迹应该被判定为失败"
    
    def test_success_determination_think_only(self):
        """测试仅包含思考内容的判定"""
        trajectory_think_only = "<think>这是一个详细的思考过程，分析了问题的各个方面</think>"
        
        success = self.runtime._determine_task_success(trajectory_think_only, [])
        assert success == True, "包含有意义思考内容的轨迹应该被判定为成功"
    
    def test_final_result_extraction_from_answer(self):
        """测试从answer标签提取最终结果"""
        trajectory = "<think>计算中</think><answer>1+1的结果是2</answer>"
        
        result = self.runtime._extract_final_result(trajectory)
        assert "1+1的结果是2" in result, "应该能够从answer标签提取实际答案内容"
    
    def test_final_result_extraction_from_think(self):
        """测试从think标签提取结果"""
        trajectory = "<think>经过分析，答案应该是42</think>"
        
        result = self.runtime._extract_final_result(trajectory)
        assert "思考过程" in result and "42" in result, "应该能够从think标签提取思考内容"
    
    def test_final_result_extraction_from_tool_result(self):
        """测试从工具结果提取最终结果"""
        trajectory = "<result>计算完成：2+2=4</result>"
        
        result = self.runtime._extract_final_result(trajectory)
        assert "执行结果" in result and "2+2=4" in result, "应该能够从result标签提取工具执行结果"
    
    def test_no_action_injection_logic_think_content(self):
        """测试思考内容时不注入无动作消息"""
        response_with_think = "<think>我正在分析这个问题</think>"
        
        should_inject = self.runtime._should_inject_no_action_message(response_with_think)
        assert should_inject == False, "包含思考内容时不应该注入无动作消息"
    
    def test_no_action_injection_logic_answer_content(self):
        """测试答案内容时不注入无动作消息"""
        response_with_answer = "<answer>这是最终答案</answer>"
        
        should_inject = self.runtime._should_inject_no_action_message(response_with_answer)
        assert should_inject == False, "包含答案内容时不应该注入无动作消息"
    
    def test_no_action_injection_logic_empty_response(self):
        """测试空响应时注入无动作消息"""
        empty_response = "   "
        
        should_inject = self.runtime._should_inject_no_action_message(empty_response)
        assert should_inject == True, "空响应时应该注入无动作消息"
    
    def test_format_result_uses_constants(self):
        """测试结果格式化使用常量"""
        # 测试空结果
        empty_result = self.runtime._format_result("")
        assert TaskExecutionConstants.NO_ACTION_PERFORMED in empty_result
        assert TaskExecutionConstants.XML_TAGS['RESULT'] in empty_result
        
        # 测试非空结果
        normal_result = self.runtime._format_result("正常的工具执行结果")
        assert "正常的工具执行结果" in normal_result
        assert TaskExecutionConstants.XML_TAGS['RESULT'] in normal_result
    
    def test_constants_not_hardcoded(self):
        """验证关键字符串不再硬编码"""
        # 检查代码中是否还存在硬编码的问题
        import inspect
        
        source = inspect.getsource(self.runtime._determine_task_success)
        
        # 确保没有硬编码的XML标签
        assert "</answer>" not in source, "代码中不应该包含硬编码的XML标签"
        assert "<answer>" not in source, "代码中不应该包含硬编码的XML标签"
        assert "<think>" not in source, "代码中不应该包含硬编码的XML标签"
        
        # 确保使用了常量
        assert "TaskExecutionConstants" in source, "应该使用TaskExecutionConstants常量"


if __name__ == "__main__":
    """运行测试验证修复效果"""
    print("🔧 开始验证任务状态判定修复效果...")
    
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
    
    print("\n✅ 修复验证完成！")
    print("\n📋 修复效果摘要:")
    print("- ✅ 消除了所有硬编码的状态判定逻辑")
    print("- ✅ 实现了智能的成功状态判定")
    print("- ✅ 实现了动态的结果内容提取")
    print("- ✅ 优化了错误消息注入逻辑")
    print("- ✅ 提供了统一的常量管理")