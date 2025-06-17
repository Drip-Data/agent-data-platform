import os
import logging
from typing import Any, Dict, List, Optional
import httpx
import tiktoken

from .interfaces import ILLMProvider

logger = logging.getLogger(__name__)

class OpenAIProvider(ILLMProvider):
    """
    OpenAI LLM 提供商的实现。
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_key = self.config.get('openai_api_key') or os.getenv('OPENAI_API_KEY')
        self.api_base = self.config.get('openai_api_base') or os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1')
        self.client = httpx.AsyncClient(timeout=60.0)
        self._supported_models = self.config.get('openai_supported_models', ["gpt-3.5-turbo", "gpt-4", "gpt-4o"])
        self._default_model = self.config.get('openai_default_model', "gpt-3.5-turbo")
        
        if not self.api_key:
            logger.warning("OPENAI_API_KEY 或配置中未设置。OpenAIProvider 可能无法正常工作。")

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
        根据给定的消息生成 OpenAI LLM 响应。
        """
        if model not in self._supported_models:
            logger.warning(f"模型 {model} 不受 OpenAIProvider 支持，将使用默认模型 {self._default_model}。")
            model = self._default_model

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
            **kwargs
        }
        
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = await self.client.post(
                f"{self.api_base}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            
            if stream:
                # 对于流式响应，返回 httpx.Response 对象，由调用者处理
                return response
            else:
                result = response.json()
                # 提取文本内容，如果存在 tool_calls，则返回 tool_calls
                if result["choices"] and result["choices"][0]["message"].get("tool_calls"):
                    return result["choices"][0]["message"]["tool_calls"]
                elif result["choices"] and result["choices"][0]["message"].get("content"):
                    return result["choices"][0]["message"]["content"]
                else:
                    return "" # 或者抛出错误，取决于期望行为
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI API HTTP 错误: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"OpenAI API 请求错误: {e}")
            raise
        except Exception as e:
            logger.error(f"调用 OpenAI API 失败: {e}")
            raise

    async def count_tokens(self, text: str, model: str) -> int:
        """
        计算给定文本在特定 OpenAI 模型中的令牌数。
        """
        try:
            encoding = tiktoken.encoding_for_model(model)
            return len(encoding.encode(text))
        except KeyError:
            logger.warning(f"未找到模型 {model} 的 tiktoken 编码，将使用 cl100k_base 编码。")
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception as e:
            logger.error(f"计算令牌数失败: {e}")
            return int(len(text) / 4) # 粗略估计，并转换为整数

    def get_supported_models(self) -> List[str]:
        """
        获取此提供商支持的 OpenAI 模型列表。
        """
        return self._supported_models

    def get_default_model(self) -> str:
        """
        获取此提供商的默认 OpenAI 模型。
        """
        return self._default_model