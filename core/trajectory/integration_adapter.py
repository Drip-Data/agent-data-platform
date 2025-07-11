"""
轨迹优化系统集成适配器
Integration adapter for trajectory optimization system
"""

import logging
import time
from typing import Dict, Any, List, Optional
from pathlib import Path
import json

from .trajectory_optimizer import TrajectoryOptimizer
from ..trajectory_enhancer import TrajectoryEnhancer
from ..interfaces import TrajectoryResult, ExecutionStep

logger = logging.getLogger(__name__)

class TrajectoryOptimizationAdapter:
    """轨迹优化系统集成适配器
    
    负责整合新的轨迹优化组件与现有系统的接口
    """
    
    def __init__(self, enable_enhancement: bool = True):
        self.trajectory_optimizer = TrajectoryOptimizer()
        self.trajectory_enhancer = TrajectoryEnhancer() if enable_enhancement else None
        self.enable_enhancement = enable_enhancement
        
        logger.info("轨迹优化集成适配器初始化完成")
    
    def process_trajectory(self, trajectory_data: Dict[str, Any], 
                          output_formats: List[str] = None) -> Dict[str, Any]:
        """处理单个轨迹
        
        Args:
            trajectory_data: 原始轨迹数据
            output_formats: 输出格式列表 ['markdown', 'json']
            
        Returns:
            处理结果包含优化后的轨迹和导出文件路径
        """
        if output_formats is None:
            output_formats = ['markdown', 'json']
        
        start_time = time.time()
        
        try:
            # 1. 使用新优化器优化轨迹
            optimized_trajectory = self.trajectory_optimizer.optimize_trajectory(trajectory_data)
            
            # 2. 如果启用增强，使用原有增强器
            if self.enable_enhancement and self.trajectory_enhancer:
                # 转换为TrajectoryResult格式以兼容现有增强器
                trajectory_result = self._convert_to_trajectory_result(trajectory_data)
                enhanced_result = self.trajectory_enhancer.enhance_trajectory(trajectory_result)
                
                # 将增强数据合并到优化轨迹中
                self._merge_enhancement_data(optimized_trajectory, enhanced_result)
            
            # 3. 导出到指定格式
            exported_files = {}
            
            if 'markdown' in output_formats:
                markdown_content = self.trajectory_optimizer.export_as_markdown(optimized_trajectory)
                exported_files['markdown'] = {
                    'content': markdown_content,
                    'size': len(markdown_content.encode('utf-8'))
                }
            
            if 'json' in output_formats:
                json_content = self.trajectory_optimizer.export_as_json(optimized_trajectory)
                exported_files['json'] = {
                    'content': json_content,
                    'size': len(json.dumps(json_content, ensure_ascii=False).encode('utf-8'))
                }
            
            processing_time = time.time() - start_time
            
            return {
                'success': True,
                'optimized_trajectory': optimized_trajectory,
                'exported_files': exported_files,
                'processing_metrics': {
                    'processing_time_ms': int(processing_time * 1000),
                    'original_steps': len(trajectory_data.get('steps', [])),
                    'optimized_steps': len(optimized_trajectory.steps),
                    'enhancement_enabled': self.enable_enhancement
                }
            }
            
        except Exception as e:
            logger.error(f"轨迹处理失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'processing_time_ms': int((time.time() - start_time) * 1000)
            }
    
    def batch_process_trajectories(self, trajectories_file: str,
                                 output_dir: str) -> Dict[str, Any]:
        """批量处理轨迹文件
        
        Args:
            trajectories_file: 轨迹集合文件路径
            output_dir: 输出目录
            
        Returns:
            批量处理结果
        """
        start_time = time.time()
        
        try:
            # 使用现有的批处理函数
            from .trajectory_optimizer import process_trajectory_file
            
            processed_files = process_trajectory_file(trajectories_file, output_dir)
            
            processing_time = time.time() - start_time
            
            return {
                'success': True,
                'processed_files': processed_files,
                'total_processing_time_ms': int(processing_time * 1000),
                'enhancement_enabled': self.enable_enhancement
            }
            
        except Exception as e:
            logger.error(f"批量处理失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'processing_time_ms': int((time.time() - start_time) * 1000)
            }
    
    def _convert_to_trajectory_result(self, trajectory_data: Dict[str, Any]) -> TrajectoryResult:
        """转换轨迹数据为TrajectoryResult格式以兼容现有增强器"""
        try:
            # 转换步骤数据
            steps = []
            for i, step_data in enumerate(trajectory_data.get('steps', [])):
                # 从step_data中提取必要信息
                step = ExecutionStep(
                    step_id=step_data.get('step_id', i + 1),
                    action_type=step_data.get('action_type', 'TOOL_CALL'),
                    action_params=step_data.get('tool_input', {}),
                    observation=step_data.get('tool_output', ''),
                    success=step_data.get('success', True),
                    thinking=step_data.get('thinking', ''),
                    execution_code=step_data.get('execution_code', ''),
                    duration=step_data.get('duration', 0.0),
                    timestamp=step_data.get('timestamp', time.time())
                )
                steps.append(step)
            
            # 创建TrajectoryResult
            trajectory_result = TrajectoryResult(
                task_name=trajectory_data.get('task_name', ''),
                task_id=trajectory_data.get('task_id', ''),
                task_description=trajectory_data.get('task_description', ''),
                runtime_id=trajectory_data.get('runtime_id', ''),
                success=trajectory_data.get('success', True),
                steps=steps,
                final_result=trajectory_data.get('final_result', ''),
                total_duration=trajectory_data.get('total_duration', 0.0),
                metadata=trajectory_data.get('metadata', {}),
                created_at=trajectory_data.get('created_at', time.time())
            )
            
            return trajectory_result
            
        except Exception as e:
            logger.error(f"转换轨迹数据失败: {e}")
            raise
    
    def _merge_enhancement_data(self, optimized_trajectory, enhanced_result: TrajectoryResult):
        """将增强数据合并到优化轨迹中"""
        try:
            # 将增强器添加的元数据合并到优化轨迹
            if hasattr(enhanced_result, 'llm_metrics'):
                optimized_trajectory.metadata.setdefault('enhancement', {})
                optimized_trajectory.metadata['enhancement']['llm_metrics'] = enhanced_result.llm_metrics
            
            if hasattr(enhanced_result, 'execution_environment'):
                optimized_trajectory.metadata.setdefault('enhancement', {})
                optimized_trajectory.metadata['enhancement']['execution_environment'] = enhanced_result.execution_environment
            
            if hasattr(enhanced_result, 'error_handling'):
                optimized_trajectory.metadata.setdefault('enhancement', {})
                optimized_trajectory.metadata['enhancement']['error_handling'] = enhanced_result.error_handling
            
            # 合并步骤级别的增强数据
            for i, enhanced_step in enumerate(enhanced_result.steps):
                if i < len(optimized_trajectory.steps):
                    optimized_step = optimized_trajectory.steps[i]
                    
                    # 合并资源使用信息
                    if hasattr(enhanced_step, 'resource_usage') and enhanced_step.resource_usage:
                        optimized_step.performance_metrics.execution_time_ms = enhanced_step.resource_usage.get('execution_time_ms', 0)
                    
                    # 合并LLM交互记录
                    if hasattr(enhanced_step, 'llm_interactions') and enhanced_step.llm_interactions:
                        # 这里可以将LLM交互信息添加到性能指标中
                        for interaction in enhanced_step.llm_interactions:
                            if hasattr(interaction, 'token_usage') and interaction.token_usage:
                                optimized_step.performance_metrics.token_metrics.input_tokens += interaction.token_usage.get('prompt_tokens', 0)
                                optimized_step.performance_metrics.token_metrics.output_tokens += interaction.token_usage.get('completion_tokens', 0)
                                optimized_step.performance_metrics.token_metrics.total_tokens = (
                                    optimized_step.performance_metrics.token_metrics.input_tokens + 
                                    optimized_step.performance_metrics.token_metrics.output_tokens
                                )
            
            logger.debug("增强数据合并完成")
            
        except Exception as e:
            logger.warning(f"合并增强数据失败: {e}")
    
    def get_integration_status(self) -> Dict[str, Any]:
        """获取集成状态"""
        return {
            'optimizer_available': self.trajectory_optimizer is not None,
            'enhancer_available': self.trajectory_enhancer is not None,
            'enhancement_enabled': self.enable_enhancement,
            'supported_formats': ['markdown', 'json'],
            'integration_version': '1.0.0'
        }

# 兼容性函数，提供简单的接口
def optimize_single_trajectory(trajectory_data: Dict[str, Any], 
                             output_formats: List[str] = None,
                             enable_enhancement: bool = True) -> Dict[str, Any]:
    """优化单个轨迹的便捷函数"""
    adapter = TrajectoryOptimizationAdapter(enable_enhancement=enable_enhancement)
    return adapter.process_trajectory(trajectory_data, output_formats)

def optimize_trajectory_file(input_file: str, output_dir: str,
                           enable_enhancement: bool = True) -> Dict[str, Any]:
    """优化轨迹文件的便捷函数"""
    adapter = TrajectoryOptimizationAdapter(enable_enhancement=enable_enhancement)
    return adapter.batch_process_trajectories(input_file, output_dir)