import os
import logging
from typing import Any, Dict, List, Optional
import httpx
import tiktoken # vLLM也可能需要tiktoken来计算token

from .interfaces import ILLMProvider

logger = logging.getLogger(__name__)

class VLLMProvider(ILLMProvider):
    """
    vLLM 本地服务提供商的实现。
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.vllm_url = self.config.get("vllm_url", "http://localhost:8001") # 更改vLLM默认端口以避免冲突
        self.client = httpx.AsyncClient(timeout=60.0)
        self._supported_models = self.config.get('vllm_supported_models', ["default"]) # vLLM通常只有一个默认模型
        self._default_model = self.config.get('vllm_default_model', "default")
        
        logger.info(f"Initialized VLLMProvider with URL: {self.vllm_url}")

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.1, # vLLM的默认温度
        max_tokens: int = 1024, # vLLM的默认max_tokens
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None, # vLLM的工具调用可能不同
        tool_choice: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        根据给定的消息生成 vLLM 响应。
        """
        if model not in self._supported_models:
            logger.warning(f"模型 {model} 不受 VLLMProvider 支持，将使用默认模型 {self._default_model}。")
            model = self._default_model

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
            **kwargs
        }
        
        # vLLM的工具调用格式可能不同，这里暂时不处理tools和tool_choice
        # if tools:
        #     payload["tools"] = tools
        # if tool_choice:
        #     payload["tool_choice"] = tool_choice

        try:
            response = await self.client.post(
                f"{self.vllm_url}/v1/chat/completions",
                json=payload
            )
            response.raise_for_status()
            
            if stream:
                return response
            else:
                result = response.json()
                # vLLM通常只返回content
                if result["choices"] and result["choices"][0]["message"].get("content"):
                    return result["choices"][0]["message"]["content"]
                else:
                    return ""
        except httpx.HTTPStatusError as e:
            logger.error(f"vLLM API HTTP 错误: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"vLLM API 请求错误: {e}")
            raise
        except Exception as e:
            logger.error(f"调用 vLLM API 失败: {e}")
            raise

    async def count_tokens(self, text: str, model: str) -> int:
        """
        计算给定文本在特定 vLLM 模型中的令牌数。
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
        获取此提供商支持的 vLLM 模型列表。
        """
        return self._supported_models

    def get_default_model(self) -> str:
        """
        获取此提供商的默认 vLLM 模型。
        """
        return self._default_model