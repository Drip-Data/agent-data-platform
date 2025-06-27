"""
轨迹优化系统测试
Tests for trajectory optimization system
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from datetime import datetime

from core.trajectory.trajectory_optimizer import TrajectoryOptimizer, process_trajectory_file
from core.trajectory.text_cleaner import TrajectoryTextCleaner, TrajectoryMarkdownFormatter
from core.trajectory.metrics_collector import MetricsCollector, TrajectoryAggregator
from core.trajectory.integration_adapter import (
    TrajectoryOptimizationAdapter, 
    optimize_single_trajectory, 
    optimize_trajectory_file
)

class TestTrajectoryTextCleaner:
    """测试文本清理器"""
    
    def setup_method(self):
        self.cleaner = TrajectoryTextCleaner()
    
    def test_escape_sequence_removal(self):
        """测试转义符移除"""
        raw_text = "Hello\\nWorld\\t\\\"Test\\\"\\\\Path"
        cleaned = self.cleaner._remove_escape_sequences(raw_text)
        assert cleaned == "Hello\nWorld\t\"Test\"\\Path"
    
    def test_llm_output_cleaning(self):
        """测试LLM输出清理"""
        raw_output = "工具执行成功: {'answer': 'Hello\\nWorld\\tTest'}"
        cleaned = self.cleaner.clean_llm_output(raw_output)
        assert "Hello\nWorld\tTest" in cleaned
    
    def test_json_content_extraction(self):
        """测试JSON内容提取"""
        text_with_json = "Result: {'answer': 'This is the answer', 'status': 'success'}"
        result = self.cleaner._extract_json_content(text_with_json)
        assert result == "This is the answer"
    
    def test_thinking_process_parsing(self):
        """测试thinking过程解析"""
        thinking_text = """
        STEP 1 - Analysis: This is the analysis step
        STEP 2 - Decision: This is the decision step
        STEP 3 - Execution: This is the execution step
        """
        structured = self.cleaner.clean_thinking_process(thinking_text)
        assert len(structured) == 3
        assert "step_1_analysis" in structured
        assert "step_2_decision" in structured
        assert "step_3_execution" in structured

class TestMetricsCollector:
    """测试指标收集器"""
    
    def setup_method(self):
        self.collector = MetricsCollector()
    
    def test_token_metrics_calculation(self):
        """测试Token指标计算"""
        step_data = {
            'llm_interactions': [
                {
                    'input_tokens': 100,
                    'output_tokens': 50,
                    'model': 'gpt-4'
                }
            ]
        }
        
        metrics = self.collector._calculate_token_metrics(step_data, "test response")
        assert metrics.input_tokens == 100
        assert metrics.output_tokens == 50
        assert metrics.total_tokens == 150
        assert metrics.cost_estimate > 0
    
    def test_quality_assessment(self):
        """测试质量评估"""
        step_data = {
            'thinking': 'STEP 1: Analysis - I need to analyze this problem carefully because it requires logical reasoning',
            'tool_output': 'This is a comprehensive analysis of the problem with detailed explanations',
            'success': True
        }
        
        assessment = self.collector.assess_step_quality(step_data, step_data['tool_output'])
        assert assessment.overall_score > 0.5
        assert assessment.reasoning_quality.value in ['poor', 'fair', 'good', 'excellent']
    
    def test_efficiency_score_calculation(self):
        """测试效率评分计算"""
        # 高效执行（快速且成功）
        score_fast = self.collector._calculate_efficiency_score(5000, 0, True)
        assert score_fast > 0.8
        
        # 低效执行（慢且有重试）
        score_slow = self.collector._calculate_efficiency_score(60000, 3, True)
        assert score_slow < 0.5

class TestTrajectoryOptimizer:
    """测试轨迹优化器"""
    
    def setup_method(self):
        self.optimizer = TrajectoryOptimizer()
        
        # 创建测试轨迹数据
        self.test_trajectory = {
            'task_id': 'test_task_001',
            'task_name': 'Test Task',
            'task_description': 'This is a test task for trajectory optimization',
            'runtime_id': 'test_runtime',
            'success': True,
            'final_result': 'Task completed successfully',
            'steps': [
                {
                    'step_id': 1,
                    'action_type': 'tool_call',
                    'thinking': 'STEP 1 - Analysis: I need to process this request',
                    'tool_input': {
                        '_tool_id': 'search_tool',
                        '_action': 'search',
                        'query': 'test query'
                    },
                    'tool_output': '工具执行成功: {"answer": "Search results\\nFound 5 items"}',
                    'success': True,
                    'duration': 2.5
                },
                {
                    'step_id': 2,
                    'action_type': 'analysis',
                    'thinking': 'STEP 2 - Decision: Based on the search results, I will summarize',
                    'tool_input': {
                        '_tool_id': 'analysis_tool',
                        '_action': 'analyze',
                        'data': 'search results'
                    },
                    'tool_output': 'Analysis complete: Summary of findings',
                    'success': True,
                    'duration': 1.8
                }
            ]
        }
    
    def test_trajectory_optimization(self):
        """测试轨迹优化"""
        optimized = self.optimizer.optimize_trajectory(self.test_trajectory)
        
        # 验证基本结构
        assert optimized.task_id == 'test_task_001'
        assert optimized.task_name == 'Test Task'
        assert len(optimized.steps) == 2
        
        # 验证优化步骤
        step1 = optimized.steps[0]
        assert step1.step_id == 1
        assert step1.tool_id == 'search_tool'
        assert step1.action == 'search'
        assert step1.cleaned_output != step1.raw_output
        assert len(step1.structured_reasoning) > 0
        
        # 验证性能指标
        assert step1.performance_metrics.execution_time_ms > 0
        assert step1.performance_metrics.token_metrics.total_tokens > 0
        assert step1.quality_assessment.overall_score > 0
    
    def test_markdown_export(self):
        """测试Markdown导出"""
        optimized = self.optimizer.optimize_trajectory(self.test_trajectory)
        markdown = self.optimizer.export_as_markdown(optimized)
        
        # 验证Markdown结构
        assert "# 🎯 Task Execution Report" in markdown
        assert "## 📊 Execution Summary" in markdown
        assert "## 🔄 Execution Steps" in markdown
        assert "### ✅ Step 1:" in markdown
        assert "### ✅ Step 2:" in markdown
        assert "#### 🧠 Decision Process" in markdown
        assert "#### 📊 Performance" in markdown
    
    def test_json_export(self):
        """测试JSON导出"""
        optimized = self.optimizer.optimize_trajectory(self.test_trajectory)
        json_result = self.optimizer.export_as_json(optimized)
        
        # 验证JSON结构
        assert 'task_metadata' in json_result
        assert 'execution_summary' in json_result
        assert 'resource_usage' in json_result
        assert 'steps' in json_result
        
        assert len(json_result['steps']) == 2
        
        step1 = json_result['steps'][0]
        assert 'decision_context' in step1
        assert 'performance_metrics' in step1
        assert 'quality_assessment' in step1
        assert 'content' in step1

class TestTrajectoryAggregator:
    """测试轨迹聚合器"""
    
    def setup_method(self):
        self.aggregator = TrajectoryAggregator()
        
        self.test_steps = [
            {
                'step_id': 1,
                'success': True,
                'duration': 2.5,
                'llm_interactions': [{'input_tokens': 100, 'output_tokens': 50}]
            },
            {
                'step_id': 2,
                'success': True,
                'duration': 1.8,
                'llm_interactions': [{'input_tokens': 80, 'output_tokens': 40}]
            },
            {
                'step_id': 3,
                'success': False,
                'duration': 3.2,
                'llm_interactions': [{'input_tokens': 120, 'output_tokens': 30}]
            }
        ]
    
    def test_metrics_aggregation(self):
        """测试指标聚合"""
        metrics = self.aggregator.aggregate_trajectory_metrics(self.test_steps)
        
        assert metrics['total_steps'] == 3
        assert metrics['successful_steps'] == 2
        assert metrics['success_rate'] == 2/3
        assert metrics['total_duration_ms'] > 0
        assert metrics['total_tokens'] > 0
        assert metrics['average_quality_score'] >= 0

class TestIntegrationAdapter:
    """测试集成适配器"""
    
    def setup_method(self):
        self.adapter = TrajectoryOptimizationAdapter(enable_enhancement=False)
        
        self.test_trajectory = {
            'task_id': 'integration_test_001',
            'task_name': 'Integration Test',
            'task_description': 'Testing integration adapter',
            'runtime_id': 'test_runtime',
            'success': True,
            'final_result': 'Integration test completed',
            'steps': [
                {
                    'step_id': 1,
                    'action_type': 'tool_call',
                    'thinking': 'Testing integration',
                    'tool_input': {'_tool_id': 'test_tool', '_action': 'test'},
                    'tool_output': 'Test output',
                    'success': True,
                    'duration': 1.0
                }
            ]
        }
    
    def test_single_trajectory_processing(self):
        """测试单轨迹处理"""
        result = self.adapter.process_trajectory(self.test_trajectory, ['markdown', 'json'])
        
        assert result['success'] is True
        assert 'optimized_trajectory' in result
        assert 'exported_files' in result
        assert 'markdown' in result['exported_files']
        assert 'json' in result['exported_files']
        assert 'processing_metrics' in result
    
    def test_integration_status(self):
        """测试集成状态"""
        status = self.adapter.get_integration_status()
        
        assert status['optimizer_available'] is True
        assert 'enhancer_available' in status
        assert 'supported_formats' in status
        assert 'markdown' in status['supported_formats']
        assert 'json' in status['supported_formats']

class TestFileProcessing:
    """测试文件处理功能"""
    
    def test_trajectory_file_processing(self):
        """测试轨迹文件处理"""
        # 创建测试数据
        test_trajectories = [
            {
                'task_id': 'file_test_001',
                'task_name': 'File Test 1',
                'task_description': 'Testing file processing',
                'runtime_id': 'test_runtime',
                'success': True,
                'final_result': 'File test completed',
                'steps': [
                    {
                        'step_id': 1,
                        'action_type': 'tool_call',
                        'thinking': 'Processing file test',
                        'tool_input': {'_tool_id': 'file_tool', '_action': 'process'},
                        'tool_output': 'File processed successfully',
                        'success': True,
                        'duration': 2.0
                    }
                ]
            }
        ]
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_trajectories, f, ensure_ascii=False, indent=2)
            temp_input_file = f.name
        
        try:
            # 创建临时输出目录
            with tempfile.TemporaryDirectory() as temp_output_dir:
                # 处理文件
                result = process_trajectory_file(temp_input_file, temp_output_dir)
                
                # 验证结果
                assert 'File Test 1' in result or 'file_test_1' in result
                
                # 检查输出文件
                output_files = list(Path(temp_output_dir).glob('*.md'))
                assert len(output_files) > 0
                
                json_files = list(Path(temp_output_dir).glob('*_optimized.json'))
                assert len(json_files) > 0
        
        finally:
            # 清理临时文件
            os.unlink(temp_input_file)

class TestConvenienceFunctions:
    """测试便捷函数"""
    
    def test_optimize_single_trajectory_function(self):
        """测试单轨迹优化便捷函数"""
        test_trajectory = {
            'task_id': 'convenience_test_001',
            'task_name': 'Convenience Test',
            'task_description': 'Testing convenience function',
            'runtime_id': 'test_runtime',
            'success': True,
            'final_result': 'Convenience test completed',
            'steps': []
        }
        
        result = optimize_single_trajectory(test_trajectory, ['markdown'])
        
        assert result['success'] is True
        assert 'optimized_trajectory' in result
        assert 'markdown' in result['exported_files']
    
    def test_optimize_trajectory_file_function(self):
        """测试文件优化便捷函数"""
        # 创建测试数据
        test_trajectories = [
            {
                'task_id': 'convenience_file_test_001',
                'task_name': 'Convenience File Test',
                'task_description': 'Testing convenience file function',
                'runtime_id': 'test_runtime',
                'success': True,
                'final_result': 'Convenience file test completed',
                'steps': []
            }
        ]
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_trajectories, f, ensure_ascii=False, indent=2)
            temp_input_file = f.name
        
        try:
            # 创建临时输出目录
            with tempfile.TemporaryDirectory() as temp_output_dir:
                # 使用便捷函数处理文件
                result = optimize_trajectory_file(temp_input_file, temp_output_dir)
                
                # 验证结果
                assert result['success'] is True
                assert 'processed_files' in result
        
        finally:
            # 清理临时文件
            os.unlink(temp_input_file)

# 如果直接运行这个文件，执行测试
if __name__ == "__main__":
    pytest.main([__file__, "-v"])