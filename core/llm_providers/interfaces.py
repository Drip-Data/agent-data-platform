import abc
from typing import Any, Dict, List, Optional

class ILLMProvider(abc.ABC):
    """
    LLM 提供商的抽象基类接口。
    所有具体的 LLM 提供商（如 OpenAI、Anthropic 等）都应实现此接口。
    """

    @abc.abstractmethod
    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        根据给定的消息生成 LLM 响应。

        Args:
            messages: 消息列表，通常遵循 OpenAI 格式。
            model: 要使用的 LLM 模型名称。
            temperature: 采样温度。
            max_tokens: 生成的最大令牌数。
            stream: 是否以流式方式获取响应。
            tools: 可选的工具定义列表。
            tool_choice: 可选的工具选择策略。
            **kwargs: 其他特定于提供商的参数。

        Returns:
            LLM 响应对象。
        """
        pass

    @abc.abstractmethod
    async def count_tokens(self, text: str, model: str) -> int:
        """
        计算给定文本在特定模型中的令牌数。

        Args:
            text: 要计算令牌数的文本。
            model: 用于计算的 LLM 模型名称。

        Returns:
            文本中的令牌数。
        """
        pass

    @abc.abstractmethod
    def get_supported_models(self) -> List[str]:
        """
        获取此提供商支持的模型列表。

        Returns:
            支持的模型名称列表。
        """
        pass

    @abc.abstractmethod
    def get_default_model(self) -> str:
        """
        获取此提供商的默认模型。

        Returns:
            默认模型名称。
        """
        pass