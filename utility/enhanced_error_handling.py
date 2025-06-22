#!/usr/bin/env python3
"""
增强的错误处理和循环终止机制
用于避免推理运行时陷入无限循环
"""

import logging
import time
from typing import Dict, List, Set, Optional
from dataclasses import dataclass
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

@dataclass
class LoopDetectionState:
    """循环检测状态"""
    repeated_actions: Dict[str, int]  # 重复动作计数
    repeated_errors: Dict[str, int]   # 重复错误计数
    recent_tool_calls: deque          # 最近的工具调用
    consecutive_failures: int         # 连续失败次数
    start_time: float                 # 开始时间
    last_progress_time: float         # 最后进度时间

class EnhancedErrorHandler:
    """增强的错误处理器"""
    
    def __init__(self):
        self.max_consecutive_failures = 3
        self.max_repeated_actions = 5
        self.max_execution_time = 300  # 5分钟
        self.progress_timeout = 60     # 1分钟无进展超时
        self.loop_detection_window = 10  # 检测窗口大小
        
    def create_detection_state(self) -> LoopDetectionState:
        """创建循环检测状态"""
        current_time = time.time()
        return LoopDetectionState(
            repeated_actions=defaultdict(int),
            repeated_errors=defaultdict(int),
            recent_tool_calls=deque(maxlen=self.loop_detection_window),
            consecutive_failures=0,
            start_time=current_time,
            last_progress_time=current_time
        )
    
    def should_terminate_execution(
        self, 
        state: LoopDetectionState,
        current_action: str,
        current_tool_id: str,
        step_success: bool,
        error_message: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        检查是否应该终止执行
        返回 (should_terminate, reason)
        """
        current_time = time.time()
        
        # 1. 检查总执行时间
        if current_time - state.start_time > self.max_execution_time:
            return True, f"执行超时 ({self.max_execution_time}秒)"
        
        # 2. 检查无进展超时
        if not step_success:
            time_since_progress = current_time - state.last_progress_time
            if time_since_progress > self.progress_timeout:
                return True, f"无进展超时 ({self.progress_timeout}秒无成功操作)"
        else:
            state.last_progress_time = current_time
        
        # 3. 更新状态
        action_key = f"{current_action}:{current_tool_id}"
        state.repeated_actions[action_key] += 1
        state.recent_tool_calls.append((current_action, current_tool_id, step_success))
        
        if not step_success:
            state.consecutive_failures += 1
            if error_message:
                state.repeated_errors[error_message] += 1
        else:
            state.consecutive_failures = 0
        
        # 4. 检查连续失败
        if state.consecutive_failures >= self.max_consecutive_failures:
            return True, f"连续失败 {state.consecutive_failures} 次"
        
        # 5. 检查重复动作
        if state.repeated_actions[action_key] > self.max_repeated_actions:
            return True, f"重复执行相同动作 {state.repeated_actions[action_key]} 次: {action_key}"
        
        # 6. 检查错误循环
        for error_msg, count in state.repeated_errors.items():
            if count >= 3:
                return True, f"重复相同错误 {count} 次: {error_msg[:100]}"
        
        # 7. 检查工具调用模式循环
        if len(state.recent_tool_calls) >= self.loop_detection_window:
            # 检查是否在重复相同的模式
            recent_actions = [f"{action}:{tool}" for action, tool, _ in state.recent_tool_calls]
            
            # 简单的模式检测：检查是否有重复的序列
            pattern_length = 3
            if len(recent_actions) >= pattern_length * 2:
                pattern = recent_actions[-pattern_length:]
                previous_pattern = recent_actions[-pattern_length*2:-pattern_length]
                if pattern == previous_pattern:
                    return True, f"检测到工具调用循环模式: {' -> '.join(pattern)}"
        
        return False, ""
    
    def get_termination_suggestion(
        self, 
        state: LoopDetectionState,
        termination_reason: str
    ) -> str:
        """获取终止建议"""
        suggestions = []
        
        # 分析最频繁的失败原因
        if state.repeated_errors:
            top_error = max(state.repeated_errors.items(), key=lambda x: x[1])
            suggestions.append(f"主要错误: {top_error[0][:100]} (出现{top_error[1]}次)")
        
        # 分析最频繁的动作
        if state.repeated_actions:
            top_action = max(state.repeated_actions.items(), key=lambda x: x[1])
            suggestions.append(f"最频繁动作: {top_action[0]} (执行{top_action[1]}次)")
        
        # 成功率统计
        total_calls = len(state.recent_tool_calls)
        successful_calls = sum(1 for _, _, success in state.recent_tool_calls if success)
        if total_calls > 0:
            success_rate = successful_calls / total_calls * 100
            suggestions.append(f"成功率: {success_rate:.1f}% ({successful_calls}/{total_calls})")
        
        return f"任务终止原因: {termination_reason}\n建议:\n" + "\n".join(f"- {s}" for s in suggestions)

def create_enhanced_error_handler() -> EnhancedErrorHandler:
    """创建增强错误处理器的工厂函数"""
    return EnhancedErrorHandler()

# 使用示例
if __name__ == "__main__":
    # 测试错误处理器
    handler = EnhancedErrorHandler()
    state = handler.create_detection_state()
    
    # 模拟一些重复动作
    for i in range(6):
        should_terminate, reason = handler.should_terminate_execution(
            state, "analyze_content", "content_analyzer", False, "Tool not found"
        )
        print(f"Step {i+1}: Terminate={should_terminate}, Reason={reason}")
        if should_terminate:
            suggestion = handler.get_termination_suggestion(state, reason)
            print(f"建议:\n{suggestion}")
            break