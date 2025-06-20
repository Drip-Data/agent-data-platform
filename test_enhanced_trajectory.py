#!/usr/bin/env python3
"""
测试增强轨迹记录系统
验证新增的LLM元数据、成本追踪、事件因果关系等功能
"""

import asyncio
import json
import sys
import os
from typing import Dict, Any

# 添加项目根目录到Python路径
sys.path.insert(0, '/Users/zhaoxiang/Documents/Datapresso/agent-data-platform')

from core.interfaces import ExecutionStep, TrajectoryResult, LLMInteraction, ActionType, ErrorType
from core.trajectory_enhancer import TrajectoryEnhancer
from core.enhanced_llm_client import EnhancedLLMClient, LLMResponse

def create_test_llm_interaction() -> LLMInteraction:
    """创建测试LLM交互记录"""
    return LLMInteraction(
        provider="gemini",
        model="gemini-1.5-pro",
        context="test_context",
        prompt="这是一个测试提示",
        prompt_length=8,
        response="这是一个测试响应",
        response_length=8,
        response_time=1.5,
        token_usage={
            'prompt_tokens': 10,
            'completion_tokens': 15,
            'total_tokens': 25
        },
        cost_info={
            'total_cost': 0.000125,
            'currency': 'USD'
        },
        success=True
    )

def create_test_execution_step() -> ExecutionStep:
    """创建测试执行步骤"""
    step = ExecutionStep(
        step_id=1,
        action_type=ActionType.TOOL_CALL,
        action_params={"test_param": "test_value"},
        observation="测试观察结果",
        success=True,
        event_source="agent",
        triggering_event="user_request",
        resource_usage={
            "cpu_usage_percent": 25.5,
            "memory_usage_mb": 128.0,
            "execution_time_ms": 1500
        }
    )
    
    # 添加LLM交互记录
    step.llm_interactions.append(create_test_llm_interaction())
    
    # 添加子事件
    step.sub_events.append({
        "event_id": "sub_1",
        "timestamp": 1640995200.0,
        "event_type": "tool_call_initiated",
        "description": "开始工具调用"
    })
    
    return step

def create_test_trajectory() -> TrajectoryResult:
    """创建测试轨迹"""
    steps = [create_test_execution_step()]
    
    trajectory = TrajectoryResult(
        task_name="test_task",
        task_id="test_123",
        task_description="这是一个测试任务",
        runtime_id="test_runtime",
        success=True,
        steps=steps,
        final_result="测试任务成功完成",
        total_duration=5.0,
        available_tools=[{"name": "test_tool", "version": "1.0"}],
        used_tools={"test_tool": True}
    )
    
    return trajectory

def test_trajectory_enhancer():
    """测试轨迹增强器"""
    print("🔍 测试轨迹增强器...")
    
    enhancer = TrajectoryEnhancer()
    test_trajectory = create_test_trajectory()
    
    # 增强轨迹
    enhanced = enhancer.enhance_trajectory(test_trajectory)
    
    # 验证增强结果
    print(f"✅ LLM指标: {enhanced.llm_metrics}")
    print(f"✅ 执行环境: {enhanced.execution_environment}")
    print(f"✅ 错误处理: {enhanced.error_handling}")
    
    return enhanced

def test_step_to_dict():
    """测试步骤的to_dict方法"""
    print("🔍 测试ExecutionStep.to_dict()...")
    
    step = create_test_execution_step()
    step_dict = step.to_dict()
    
    # 验证新增字段
    required_fields = [
        'event_source', 'caused_by_step', 'triggering_event',
        'resource_usage', 'sub_events', 'llm_interactions'
    ]
    
    for field in required_fields:
        if field in step_dict:
            print(f"✅ 字段 '{field}' 存在: {step_dict[field]}")
        else:
            print(f"❌ 字段 '{field}' 缺失")
    
    return step_dict

def test_trajectory_to_dict():
    """测试轨迹的to_dict方法"""
    print("🔍 测试TrajectoryResult.to_dict()...")
    
    enhancer = TrajectoryEnhancer()
    trajectory = create_test_trajectory()
    enhanced_trajectory = enhancer.enhance_trajectory(trajectory)
    
    trajectory_dict = enhanced_trajectory.to_dict()
    
    # 验证新增字段
    required_fields = [
        'llm_metrics', 'execution_environment', 'error_handling'
    ]
    
    for field in required_fields:
        if field in trajectory_dict:
            print(f"✅ 字段 '{field}' 存在")
        else:
            print(f"❌ 字段 '{field}' 缺失")
    
    return trajectory_dict

def test_llm_interaction_to_dict():
    """测试LLM交互的to_dict方法"""
    print("🔍 测试LLMInteraction.to_dict()...")
    
    interaction = create_test_llm_interaction()
    interaction_dict = interaction.to_dict()
    
    # 验证新增字段
    required_fields = ['token_usage', 'cost_info']
    
    for field in required_fields:
        if field in interaction_dict:
            print(f"✅ 字段 '{field}' 存在: {interaction_dict[field]}")
        else:
            print(f"❌ 字段 '{field}' 缺失")
    
    return interaction_dict

def save_test_trajectory():
    """保存测试轨迹到文件"""
    print("🔍 保存测试轨迹...")
    
    enhancer = TrajectoryEnhancer()
    trajectory = create_test_trajectory()
    enhanced_trajectory = enhancer.enhance_trajectory(trajectory)
    
    # 保存到测试文件
    test_file = "/Users/zhaoxiang/Documents/Datapresso/agent-data-platform/output/test_enhanced_trajectory.json"
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(test_file), exist_ok=True)
    
    with open(test_file, 'w', encoding='utf-8') as f:
        json.dump(enhanced_trajectory.to_dict(), f, ensure_ascii=False, indent=2)
    
    print(f"✅ 测试轨迹已保存到: {test_file}")
    return test_file

def main():
    """主测试函数"""
    print("🚀 开始测试增强轨迹记录系统\n")
    
    try:
        # 测试各个组件
        test_llm_interaction_to_dict()
        print()
        
        test_step_to_dict()
        print()
        
        test_trajectory_to_dict()
        print()
        
        test_trajectory_enhancer()
        print()
        
        saved_file = save_test_trajectory()
        print()
        
        print("🎉 所有测试完成！")
        print(f"📄 查看生成的轨迹文件: {saved_file}")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()