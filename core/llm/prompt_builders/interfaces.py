from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class IPromptBuilder(ABC):
    """抽象提示构建器接口"""
    @abstractmethod
    def build_prompt(self, *args, **kwargs) -> List[Dict[str, Any]]:
        """构建并返回LLM消息列表"""
        pass