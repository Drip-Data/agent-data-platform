import os
import logging
from typing import Any, Dict, List, Optional
import httpx
import tiktoken # DeepSeek也可能需要tiktoken来计算token

from .interfaces import ILLMProvider

logger = logging.getLogger(__name__)

class DeepSeekProvider(ILLMProvider):
    """
    DeepSeek LLM 提供商的实现。
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_key = self.config.get('deepseek_api_key') or os.getenv('DEEPSEEK_API_KEY')
        self.api_url = self.config.get('deepseek_api_url') or os.getenv('DEEPSEEK_API_URL', 'https://api.deepseek.com/v1')
        self.client = httpx.AsyncClient(timeout=60.0)
        self._supported_models = self.config.get('deepseek_supported_models', ["deepseek-coder", "deepseek-chat"])
        self._default_model = self.config.get('deepseek_default_model', "deepseek-coder")
        
        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY 环境变量或配置中未设置。DeepSeekProvider 可能无法正常工作。")

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.1, # DeepSeek的默认温度
        max_tokens: int = 1024, # DeepSeek的默认max_tokens
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None, # DeepSeek的工具调用可能不同
        tool_choice: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        根据给定的消息生成 DeepSeek LLM 响应。
        """
        # 处理stop_sequences参数 - DeepSeek API兼容OpenAI，使用'stop'参数
        if 'stop_sequences' in kwargs:
            stop_sequences = kwargs.pop('stop_sequences')
            kwargs['stop'] = stop_sequences
            logger.debug(f"🔧 转换stop_sequences为DeepSeek的stop参数: {stop_sequences}")
        if model not in self._supported_models:
            logger.warning(f"模型 {model} 不受 DeepSeekProvider 支持，将使用默认模型 {self._default_model}。")
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
                f"{self.api_url}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            
            if stream:
                return response
            else:
                result = response.json()
                if result["choices"] and result["choices"][0]["message"].get("tool_calls"):
                    return result["choices"][0]["message"]["tool_calls"]
                elif result["choices"] and result["choices"][0]["message"].get("content"):
                    return result["choices"][0]["message"]["content"]
                else:
                    return ""
        except httpx.HTTPStatusError as e:
            logger.error(f"DeepSeek API HTTP 错误: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"DeepSeek API 请求错误: {e}")
            raise
        except Exception as e:
            logger.error(f"调用 DeepSeek API 失败: {e}")
            raise

    async def count_tokens(self, text: str, model: str) -> int:
        """
        计算给定文本在特定 DeepSeek 模型中的令牌数。
        """
        try:
            encoding = tiktoken.encoding_for_model(model)
            return len(encoding.encode(text))
        except KeyError:
            logger.warning(f"未找到模型 {model} 的 tiktoken 编码，将使用 cl100k_base 编码进行粗略估计。")
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception as e:
            logger.error(f"计算令牌数失败: {e}")
            return int(len(text) / 4) # 粗略估计，并转换为整数

    def get_supported_models(self) -> List[str]:
        """
        获取此提供商支持的 DeepSeek 模型列表。
        """
        return self._supported_models

    def get_default_model(self) -> str:
        """
        获取此提供商的默认 DeepSeek 模型。
        """
        return self._default_model