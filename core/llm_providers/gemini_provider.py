import os
import logging
from typing import Any, Dict, List, Optional
import httpx
import tiktoken # Gemini也可能需要tiktoken来计算token

from .interfaces import ILLMProvider

logger = logging.getLogger(__name__)

class GeminiProvider(ILLMProvider):
    """
    Google Gemini LLM 提供商的实现。
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_key = self.config.get('gemini_api_key') or os.getenv('GEMINI_API_KEY')
        self.api_url = self.config.get('gemini_api_url') or os.getenv('GEMINI_API_URL', 'https://generativelanguage.googleapis.com/v1beta')
        self.client = httpx.AsyncClient(timeout=60.0)
        
        # 验证并使用有效的Gemini模型名称
        # 优先从配置文件中读取模型，然后是gemini_default_model，最后是默认值
        self._default_model = (
            self.config.get('model') or 
            self.config.get('gemini_default_model') or 
            'gemini-2.5-flash-preview-05-20'
        )
        self._supported_models = self.config.get('gemini_supported_models', [
            'gemini-2.5-flash-lite-preview-06-17',
            'gemini-2.5-flash-preview-05-20',
            'gemini-2.0-flash', 'gemini-2.0-pro', 
            'gemini-1.0-pro', 'gemini-pro', 'gemini-1.5-flash' # 添加稳定模型
        ])
        
        if not self.api_key:
            logger.warning("GEMINI_API_KEY 环境变量或配置中未设置。GeminiProvider 可能无法正常工作。")

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.1, # Gemini的默认温度
        max_tokens: int = 4096, # Gemini的默认max_tokens
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None, # Gemini的工具调用可能不同
        tool_choice: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        根据给定的消息生成 Google Gemini LLM 响应。
        """
        if model not in self._supported_models:
            logger.warning(f"模型 {model} 不受 GeminiProvider 支持，将使用默认模型 {self._default_model}。")
            model = self._default_model
        
        # 将消息列表转换为Gemini的contents格式
        contents = []
        for msg in messages:
            if msg["role"] == "user":
                contents.append({"parts": [{"text": msg["content"]}]})
            elif msg["role"] == "assistant":
                # Gemini的assistant角色需要特殊处理，通常是模型输出
                # 这里简化处理，如果需要更复杂的对话历史，可能需要调整
                contents.append({"parts": [{"text": msg["content"]}]})
        
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "candidateCount": 1,
                "stopSequences": [],
                "topP": 0.9,
                "topK": 40
            },
            **kwargs
        }
        
        # Gemini的工具调用格式与OpenAI不同，这里暂时不处理tools和tool_choice
        # if tools:
        #     payload["tools"] = tools
        # if tool_choice:
        #     payload["tool_choice"] = tool_choice

        try:
            # 🔧 添加DNS解析重试机制 (从llm_client.py中迁移过来)
            from httpx import Timeout
            import asyncio # 尽管这里不直接使用asyncio.sleep，但为了保持原逻辑的完整性
            
            # 创建一个临时客户端，配置更长的超时和重试
            temp_client = httpx.AsyncClient(
                timeout=Timeout(timeout=120.0, connect=30.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                trust_env=False  # 不使用环境代理设置
            )
            
            response = await temp_client.post(
                f"{self.api_url}/models/{model}:generateContent?key={self.api_key}",
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            
            # 检查响应格式 (从llm_client.py中迁移过来)
            if "candidates" not in result:
                raise ValueError(f"Invalid Gemini response format: missing 'candidates' field")
            
            if not result["candidates"]:
                raise ValueError(f"Empty candidates in Gemini response")
                
            candidate = result["candidates"][0]
            if "content" not in candidate:
                raise ValueError(f"Invalid candidate format: missing 'content' field")
                
            content = candidate["content"]
            if "parts" not in content:
                raise ValueError(f"Invalid content format: missing 'parts' field")
                
            if not content["parts"]:
                raise ValueError(f"Empty parts in content")
                
            part = content["parts"][0]
            if "text" not in part:
                raise ValueError(f"Invalid part format: missing 'text' field")
                
            await temp_client.aclose()
            return part["text"]
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Gemini API HTTP 错误: {e.response.status_code} - {e.response.text}")
            # 🔧 强化的重试机制：使用稳定模型+直接IP (从llm_client.py中迁移过来)
            if "name resolution" in str(e).lower() or "connection" in str(e).lower():
                logger.info("尝试使用备用网络配置重试...")
                try:
                    # 使用备用DNS配置
                    backup_client = httpx.AsyncClient(
                        timeout=Timeout(timeout=180.0, connect=60.0),
                        limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
                        trust_env=False
                    )
                    
                    # 使用稳定模型重试
                    stable_model = 'gemini-1.5-flash'
                    response = await backup_client.post(
                        f"{self.api_url}/models/{stable_model}:generateContent?key={self.api_key}",
                        json=payload
                    )
                    response.raise_for_status()
                    result = response.json()
                    
                    # 同样的格式检查
                    if ("candidates" in result and result["candidates"] and 
                        "content" in result["candidates"][0] and
                        "parts" in result["candidates"][0]["content"] and
                        result["candidates"][0]["content"]["parts"] and
                        "text" in result["candidates"][0]["content"]["parts"][0]):
                        await backup_client.aclose()
                        logger.info("✅ 使用备用网络配置成功恢复")
                        return result["candidates"][0]["content"]["parts"][0]["text"]
                    else:
                        raise ValueError(f"Invalid backup response format")
                        
                except Exception as backup_e:
                    logger.error(f"备用网络配置也失败: {backup_e}")
                    raise e
            else:
                raise e
        except httpx.RequestError as e:
            logger.error(f"Gemini API 请求错误: {e}")
            raise
        except Exception as e:
            logger.error(f"调用 Gemini API 失败: {e}")
            raise

    async def count_tokens(self, text: str, model: str) -> int:
        """
        计算给定文本在特定 Gemini 模型中的令牌数。
        Gemini没有直接的tiktoken，这里使用粗略估计或未来集成Google的token计数API。
        """
        # 暂时使用粗略估计，或者如果tiktoken支持Gemini模型，则使用tiktoken
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
        获取此提供商支持的 Gemini 模型列表。
        """
        return self._supported_models

    def get_default_model(self) -> str:
        """
        获取此提供商的默认 Gemini 模型。
        """
        return self._default_model