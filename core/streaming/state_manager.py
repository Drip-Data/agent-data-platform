"""
Streaming State Manager - 流式执行状态管理器
管理Sequential执行过程中的状态、结果缓存和步骤间依赖
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class ExecutionStep:
    """执行步骤数据结构"""
    step_id: str
    step_type: str  # 'think', 'microsandbox', 'deepsearch', 'browser', 'search', 'answer'
    content: str
    position: tuple  # (start_pos, end_pos) in XML
    needs_execution: bool = False
    status: str = 'pending'  # 'pending', 'executing', 'completed', 'failed'
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class ExecutionContext:
    """执行上下文"""
    task_description: str
    initial_response: str
    current_response: str
    max_steps: int = 10
    timeout_per_step: int = 300  # 5 minutes per step
    total_timeout: int = 1800    # 30 minutes total
    session_id: str = ""  # 会话ID

class StreamingStateManager:
    """流式执行状态管理器"""
    
    def __init__(self, context: ExecutionContext):
        """
        初始化状态管理器
        
        Args:
            context: 执行上下文
        """
        self.context = context
        self.steps: List[ExecutionStep] = []
        self.step_results: Dict[str, Dict[str, Any]] = {}
        self.execution_sequence: List[str] = []
        self.shared_context: Dict[str, Any] = {}
        self.current_step: int = 0
        self.execution_start_time = datetime.now()
        self.is_completed = False
        self.error_count = 0
        
        logger.info(f"🔄 初始化StreamingStateManager - 任务: {context.task_description[:100]}...")
    
    def add_step(self, step: ExecutionStep) -> None:
        """添加执行步骤"""
        self.steps.append(step)
        logger.debug(f"➕ 添加步骤 {step.step_id}: {step.step_type} - {step.content[:50]}...")
    
    def add_step_result(self, step_id: str, result: Dict[str, Any]) -> None:
        """
        添加步骤执行结果
        
        Args:
            step_id: 步骤ID
            result: 执行结果
        """
        self.step_results[step_id] = result
        self.execution_sequence.append(step_id)
        
        # 更新步骤状态
        for step in self.steps:
            if step.step_id == step_id:
                step.result = result
                step.status = 'completed' if result.get('success', True) else 'failed'
                if not result.get('success', True):
                    step.error = result.get('error', 'Unknown error')
                    self.error_count += 1
                break
        
        logger.info(f"✅ 步骤 {step_id} 结果已保存 - 成功: {result.get('success', True)}")
    
    def get_step_result(self, step_id: str) -> Optional[Dict[str, Any]]:
        """获取步骤结果"""
        return self.step_results.get(step_id)
    
    def get_context_for_step(self, step_id: str) -> Dict[str, Any]:
        """
        获取特定步骤的上下文信息
        
        Args:
            step_id: 步骤ID
            
        Returns:
            包含历史结果和共享上下文的字典
        """
        context = {
            'task_description': self.context.task_description,
            'current_step_id': step_id,
            'previous_results': {},
            'shared_context': self.shared_context.copy(),
            'execution_stats': self.get_execution_stats()
        }
        
        # 获取当前步骤之前的所有结果
        current_step_index = None
        for i, step in enumerate(self.steps):
            if step.step_id == step_id:
                current_step_index = i
                break
        
        if current_step_index is not None:
            for i in range(current_step_index):
                step = self.steps[i]
                if step.result:
                    context['previous_results'][step.step_id] = {
                        'type': step.step_type,
                        'content': step.content[:100],  # 限制长度
                        'result': step.result,
                        'success': step.status == 'completed'
                    }
        
        return context
    
    def update_response(self, new_response: str) -> None:
        """更新当前响应"""
        self.context.current_response = new_response
        logger.debug(f"🔄 响应已更新 - 新长度: {len(new_response)} 字符")
    
    def update_shared_context(self, key: str, value: Any) -> None:
        """更新共享上下文"""
        self.shared_context[key] = value
        logger.debug(f"🔄 共享上下文更新: {key}")
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """获取执行统计信息"""
        total_steps = len(self.steps)
        completed_steps = len([s for s in self.steps if s.status == 'completed'])
        failed_steps = len([s for s in self.steps if s.status == 'failed'])
        pending_steps = len([s for s in self.steps if s.status == 'pending'])
        executing_steps = len([s for s in self.steps if s.status == 'executing'])
        
        execution_time = (datetime.now() - self.execution_start_time).total_seconds()
        
        return {
            'total_steps': total_steps,
            'completed_steps': completed_steps,
            'failed_steps': failed_steps,
            'pending_steps': pending_steps,
            'executing_steps': executing_steps,
            'error_count': self.error_count,
            'execution_time': execution_time,
            'success_rate': completed_steps / total_steps if total_steps > 0 else 0,
            'is_completed': self.is_completed
        }
    
    def mark_step_executing(self, step_id: str) -> None:
        """标记步骤开始执行"""
        for step in self.steps:
            if step.step_id == step_id:
                step.status = 'executing'
                step.timestamp = datetime.now()
                break
        logger.info(f"🔄 步骤 {step_id} 开始执行")
    
    def mark_completed(self) -> None:
        """标记整个执行完成"""
        self.is_completed = True
        execution_time = (datetime.now() - self.execution_start_time).total_seconds()
        logger.info(f"🎉 Sequential执行完成 - 总耗时: {execution_time:.2f}秒")
    
    def get_next_executable_step(self) -> Optional[ExecutionStep]:
        """获取下一个可执行的步骤"""
        for step in self.steps:
            if step.needs_execution and step.status == 'pending':
                return step
        return None
    
    def has_pending_executions(self) -> bool:
        """检查是否有待执行的步骤"""
        return any(s.needs_execution and s.status == 'pending' for s in self.steps)
    
    def get_step_by_id(self, step_id: str) -> Optional[ExecutionStep]:
        """根据ID获取步骤"""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None
    
    def should_stop_execution(self) -> tuple[bool, str]:
        """
        检查是否应该停止执行
        
        Returns:
            (should_stop, reason)
        """
        # 检查超时
        execution_time = (datetime.now() - self.execution_start_time).total_seconds()
        if execution_time > self.context.total_timeout:
            return True, f"总执行时间超时 ({execution_time:.2f}s > {self.context.total_timeout}s)"
        
        # 检查已执行步骤数量限制
        executed_steps = len([s for s in self.steps if s.status in ['completed', 'failed']])
        if executed_steps > self.context.max_steps:
            return True, f"执行步骤数量超过限制 ({executed_steps} > {self.context.max_steps})"
        
        # 检查错误率
        if self.error_count >= 3:
            return True, f"错误次数过多 ({self.error_count} >= 3)"
        
        # 检查是否已完成
        if self.is_completed:
            return True, "执行已完成"
        
        return False, ""
    
    def get_state_summary(self) -> Dict[str, Any]:
        """获取状态摘要"""
        stats = self.get_execution_stats()
        should_stop, stop_reason = self.should_stop_execution()
        
        return {
            'context': {
                'task_description': self.context.task_description,
                'max_steps': self.context.max_steps,
                'timeout_per_step': self.context.timeout_per_step,
                'total_timeout': self.context.total_timeout
            },
            'execution_stats': stats,
            'should_stop': should_stop,
            'stop_reason': stop_reason,
            'current_step': self.current_step,
            'has_pending_executions': self.has_pending_executions(),
            'shared_context_keys': list(self.shared_context.keys())
        }