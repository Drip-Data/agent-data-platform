from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import time
import uuid

@dataclass
class LLMInteraction:
    """LLM交互记录 - 用于审计和分析"""
    interaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    provider: str = ""  # LLM提供商 (gemini, openai, etc.)
    model: str = ""     # 使用的模型名称
    context: str = ""   # 交互上下文 (工具选择、任务分析等)
    
    # 输入信息
    prompt: str = ""
    prompt_length: int = 0
    prompt_type: str = ""  # tool_selection, task_analysis, reasoning等
    input_metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 输出信息
    response: str = ""
    response_length: int = 0
    response_time: float = 0.0  # 响应时间（秒）
    
    # 解析结果
    parsed_data: Dict[str, Any] = field(default_factory=dict)
    parsing_success: bool = True
    parsing_errors: List[str] = field(default_factory=list)
    
    # 成功/失败状态
    success: bool = True
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式便于存储"""
        return {
            'interaction_id': self.interaction_id,
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(self.timestamp)),
            'provider': self.provider,
            'model': self.model,
            'context': self.context,
            'prompt_info': {
                'type': self.prompt_type,
                'length': self.prompt_length,
                'content_preview': self.prompt[:200] + '...' if len(self.prompt) > 200 else self.prompt,
                'metadata': self.input_metadata
            },
            'response_info': {
                'length': self.response_length,
                'time': self.response_time,
                'content_preview': self.response[:200] + '...' if len(self.response) > 200 else self.response,
                'parsing_success': self.parsing_success,
                'parsing_errors': self.parsing_errors,
                'parsed_data': self.parsed_data
            },
            'status': {
                'success': self.success,
                'error_type': self.error_type,
                'error_message': self.error_message
            }
        }
    
    @classmethod
    def create_tool_selection_interaction(cls, prompt: str, task_description: str, 
                                        available_tools_count: int) -> 'LLMInteraction':
        """创建工具选择交互记录"""
        return cls(
            context="tool_selection",
            prompt=prompt,
            prompt_length=len(prompt),
            prompt_type="tool_selection",
            input_metadata={
                "task_description": task_description[:100] + "..." if len(task_description) > 100 else task_description,
                "available_tools_count": available_tools_count
            }
        )