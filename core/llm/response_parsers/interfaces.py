from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class IResponseParser(ABC):
    """
    LLM响应解析器接口。
    定义了从LLM原始响应中提取和结构化信息的通用方法。
    """

    @abstractmethod
    def parse_response(self, response: str, **kwargs) -> Dict[str, Any]:
        """
        解析LLM的原始字符串响应，并将其转换为结构化的字典。
        
        Args:
            response (str): LLM的原始字符串响应。
            **kwargs: 额外的参数，例如语言、任务描述等，可能用于特定解析逻辑。

        Returns:
            Dict[str, Any]: 包含解析后信息的字典。
        """
        pass