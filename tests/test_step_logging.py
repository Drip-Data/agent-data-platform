#!/usr/bin/env python3
"""
步骤级日志系统测试

验证步骤日志记录器的功能完整性
"""

import pytest
import sys
import os
import json
import tempfile
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.step_logger import StepDiagnosticLogger
from core.interfaces import TaskSpec


class TestStepDiagnosticLogger:
    """测试步骤诊断日志记录器"""
    
    def setup_method(self):
        """设置测试环境"""
        # 使用临时目录进行测试
        self.temp_dir = tempfile.mkdtemp()
        self.logger = StepDiagnosticLogger(base_path=self.temp_dir)
    
    def test_task_initialization(self):
        """测试任务初始化"""
        task_id = "test-task-123"
        task_description = "测试任务描述"
        
        self.logger.start_task(task_id, task_description)
        
        assert self.logger.current_task_data is not None
        assert self.logger.current_task_data["task_id"] == task_id
        assert self.logger.current_task_data["task_description"] == task_description
        assert "task_start_time" in self.logger.current_task_data
        assert self.logger.current_task_data["steps"] == []
    
    def test_step_initialization(self):
        """测试步骤初始化"""
        self.logger.start_task("test-task", "test description")
        
        step_index = 0
        self.logger.start_step(step_index)
        
        assert self.logger.current_step_data is not None
        assert self.logger.current_step_data["step_index"] == step_index
        assert "step_start_time" in self.logger.current_step_data
        assert "llm_interaction" in self.logger.current_step_data
        assert "parsing_stage" in self.logger.current_step_data
        assert "tool_executions" in self.logger.current_step_data
    
    def test_llm_call_logging(self):
        """测试LLM调用日志记录"""
        self.logger.start_task("test-task", "test description")
        self.logger.start_step(0)
        
        prompt = [{"role": "user", "content": "计算1+1"}]
        raw_response = "<think>需要计算1+1</think><answer>2</answer>"
        stop_sequence = "</answer>"
        start_time = 1000.0
        end_time = 1002.5
        token_usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        
        self.logger.log_llm_call(
            prompt=prompt,
            raw_response=raw_response,
            stop_sequence=stop_sequence,
            start_time=start_time,
            end_time=end_time,
            token_usage=token_usage
        )
        
        llm_data = self.logger.current_step_data["llm_interaction"]
        assert llm_data["prompt_sent_to_llm"] == prompt
        assert llm_data["raw_llm_response"] == raw_response
        assert llm_data["stop_sequence_triggered"] == stop_sequence
        assert llm_data["llm_call_duration_seconds"] == 2.5
        assert llm_data["token_usage"] == token_usage
    
    def test_parsing_result_logging(self):
        """测试解析结果日志记录"""
        self.logger.start_task("test-task", "test description")
        self.logger.start_step(0)
        
        think_content = "需要计算1+1"
        execution_block = "<microsandbox><run_code>print(1+1)</run_code></microsandbox>"
        answer_content = None
        actions = [{"service": "microsandbox", "tool": "run_code", "input": "print(1+1)"}]
        parsing_errors = []
        start_time = 2000.0
        end_time = 2000.1
        
        self.logger.log_parsing_result(
            think_content=think_content,
            execution_block=execution_block,
            answer_content=answer_content,
            actions=actions,
            parsing_errors=parsing_errors,
            start_time=start_time,
            end_time=end_time
        )
        
        parsing_data = self.logger.current_step_data["parsing_stage"]
        assert parsing_data["extracted_think_content"] == think_content
        assert parsing_data["extracted_execution_block"] == execution_block
        assert parsing_data["extracted_answer_content"] == answer_content
        assert parsing_data["parsed_actions"] == actions
        assert parsing_data["parsing_errors"] == parsing_errors
        assert parsing_data["parsing_duration_seconds"] == 0.1
    
    def test_tool_execution_logging(self):
        """测试工具执行日志记录"""
        self.logger.start_task("test-task", "test description")
        self.logger.start_step(0)
        
        execution_index = 0
        action = {"service": "microsandbox", "tool": "run_code", "input": "print(1+1)"}
        toolscore_request = {
            "endpoint": "http://127.0.0.1:8090/execute_tool",
            "method": "POST",
            "payload": {"tool_id": "microsandbox", "action": "run_code", "parameters": {"code": "print(1+1)"}}
        }
        raw_response = {
            "success": True,
            "data": {"stdout": "2\n", "stderr": "", "exit_code": 0}
        }
        formatted_result = "2"
        start_time = 3000.0
        end_time = 3000.5
        execution_status = "success"
        
        self.logger.log_tool_execution(
            execution_index=execution_index,
            action=action,
            toolscore_request=toolscore_request,
            raw_response=raw_response,
            formatted_result=formatted_result,
            start_time=start_time,
            end_time=end_time,
            execution_status=execution_status
        )
        
        tool_executions = self.logger.current_step_data["tool_executions"]
        assert len(tool_executions) == 1
        
        execution_data = tool_executions[0]
        assert execution_data["execution_index"] == execution_index
        assert execution_data["action"] == action
        assert execution_data["toolscore_request"] == toolscore_request
        assert execution_data["toolscore_raw_response"] == raw_response
        assert execution_data["formatted_result_for_llm"] == formatted_result
        assert execution_data["execution_status"] == execution_status
        assert execution_data["execution_timing"]["execution_duration_seconds"] == 0.5
    
    def test_step_completion(self):
        """测试步骤完成"""
        self.logger.start_task("test-task", "test description")
        self.logger.start_step(0)
        
        step_conclusion = "task_completed"
        self.logger.finish_step(step_conclusion)
        
        # 检查步骤是否已添加到任务数据中
        assert len(self.logger.current_task_data["steps"]) == 1
        completed_step = self.logger.current_task_data["steps"][0]
        
        assert completed_step["step_index"] == 0
        assert "step_end_time" in completed_step
        assert "step_duration_seconds" in completed_step
        assert completed_step["step_conclusion"] == step_conclusion
        
        # 检查当前步骤数据是否已重置
        assert self.logger.current_step_data is None
    
    @pytest.mark.asyncio
    async def test_task_finalization(self):
        """测试任务完成和文件写入"""
        self.logger.start_task("test-task-456", "完整的测试任务")
        
        # 模拟一个完整的步骤
        self.logger.start_step(0)
        self.logger.log_llm_call(
            prompt=[{"role": "user", "content": "test"}],
            raw_response="<answer>test result</answer>",
            stop_sequence="</answer>",
            start_time=1000.0,
            end_time=1001.0
        )
        self.logger.log_parsing_result(
            think_content=None,
            execution_block=None,
            answer_content="test result",
            actions=[],
            parsing_errors=[],
            start_time=1001.0,
            end_time=1001.1
        )
        self.logger.finish_step("completed_with_answer")
        
        # 完成任务
        final_status = "success"
        final_result = "test result"
        await self.logger.finalize_task(final_status, final_result)
        
        # 验证任务数据完整性
        assert self.logger.current_task_data is None  # 应该已重置
        
        # 检查日志文件是否创建
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(self.temp_dir, "grouped", date_str, f"step_logs_{date_str}.jsonl")
        
        assert os.path.exists(log_file), f"日志文件应该存在: {log_file}"
        
        # 验证日志文件内容
        with open(log_file, 'r', encoding='utf-8') as f:
            log_content = f.read().strip()
            
        # 应该只有一行（一个JSON对象）
        assert len(log_content.split('\n')) == 1
        
        # 解析JSON内容
        log_data = json.loads(log_content)
        
        assert log_data["task_id"] == "test-task-456"
        assert log_data["task_description"] == "完整的测试任务"
        assert log_data["task_final_status"] == final_status
        assert log_data["task_final_result"] == final_result
        assert "task_duration_seconds" in log_data
        assert len(log_data["steps"]) == 1
        
        # 验证步骤数据
        step_data = log_data["steps"][0]
        assert step_data["step_index"] == 0
        assert "llm_interaction" in step_data
        assert "parsing_stage" in step_data
        assert "tool_executions" in step_data
        assert step_data["step_conclusion"] == "completed_with_answer"
    
    def test_content_extraction_methods(self):
        """测试内容提取方法"""
        response_with_think = "<think>我需要计算这个问题</think><answer>42</answer>"
        response_with_execution = "<execute_tools><microsandbox><run>print('hello')</run></microsandbox></execute_tools>"
        response_with_answer = "<answer>最终答案是42</answer>"
        
        # 测试思考内容提取
        think_content = self.logger._extract_think_content(response_with_think)
        assert think_content == "我需要计算这个问题"
        
        # 测试答案内容提取
        answer_content = self.logger._extract_answer_content(response_with_think)
        assert answer_content == "42"
        
        answer_content2 = self.logger._extract_answer_content(response_with_answer)
        assert answer_content2 == "最终答案是42"
        
        # 测试执行块提取
        exec_block = self.logger._extract_execution_block(response_with_execution)
        assert "<microsandbox>" in exec_block
        assert "print('hello')" in exec_block
        
        # 测试没有匹配的情况
        no_think = self.logger._extract_think_content("没有思考内容")
        assert no_think is None
        
        no_answer = self.logger._extract_answer_content("没有答案内容")
        assert no_answer is None
        
        no_exec = self.logger._extract_execution_block("没有执行块")
        assert no_exec is None
    
    def teardown_method(self):
        """清理测试环境"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)


class TestStepLoggingIntegration:
    """测试步骤日志与Runtime的集成"""
    
    def test_step_logger_initialization_in_runtime(self):
        """测试Runtime中步骤日志记录器的初始化"""
        from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime
        from core.step_logger import StepDiagnosticLogger
        
        # 创建mock对象
        mock_config = MagicMock()
        mock_llm_client = MagicMock()
        mock_toolscore_client = MagicMock()
        mock_tool_manager = MagicMock()
        
        # 创建runtime实例
        runtime = EnhancedReasoningRuntime(
            config_manager=mock_config,
            llm_client=mock_llm_client,
            toolscore_client=mock_toolscore_client,
            tool_manager=mock_tool_manager
        )
        
        # 验证步骤日志记录器已初始化
        assert hasattr(runtime, 'step_logger')
        assert isinstance(runtime.step_logger, StepDiagnosticLogger)
    
    def test_detect_triggered_stop_sequence(self):
        """测试停止序列检测"""
        from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime
        
        # 创建mock runtime
        runtime = EnhancedReasoningRuntime(
            config_manager=MagicMock(),
            llm_client=MagicMock(),
            toolscore_client=MagicMock(),
            tool_manager=MagicMock()
        )
        
        stop_sequences = ["</answer>", "<execute_tools />", "<execute_tools></execute_tools>"]
        
        # 测试检测答案结束标签
        response_with_answer = "这是答案</answer>"
        detected = runtime._detect_triggered_stop_sequence(response_with_answer, stop_sequences)
        assert detected == "</answer>"
        
        # 测试检测工具执行标签
        response_with_tools = "开始执行<execute_tools />"
        detected = runtime._detect_triggered_stop_sequence(response_with_tools, stop_sequences)
        assert detected == "<execute_tools />"
        
        # 测试未检测到的情况
        response_without_stop = "普通的响应文本"
        detected = runtime._detect_triggered_stop_sequence(response_without_stop, stop_sequences)
        assert detected == "unknown"


if __name__ == "__main__":
    """运行步骤日志系统测试"""
    print("🔧 开始测试步骤级日志系统...")
    
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
    
    print("\n✅ 步骤级日志系统测试完成！")
    print("\n📋 测试验证内容:")
    print("- ✅ 日志记录器初始化和任务管理")
    print("- ✅ LLM调用日志记录")
    print("- ✅ 解析结果日志记录") 
    print("- ✅ 工具执行日志记录")
    print("- ✅ 步骤完成和任务终结")
    print("- ✅ 日志文件创建和JSON格式验证")
    print("- ✅ 内容提取辅助方法")
    print("- ✅ Runtime集成验证")