import os
import logging
import json
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
        
        # 🔧 修复消息格式转换 - 安全处理数据类型
        logger.debug(f"🔍 Gemini消息转换开始 - 输入消息数: {len(messages)}")
        contents = []
        for i, msg in enumerate(messages):
            try:
                # 确保msg是字典类型
                if not isinstance(msg, dict):
                    logger.error(f"消息 {i} 不是字典类型: {type(msg)}, 内容: {msg}")
                    continue
                
                # 安全获取role和content
                role = msg.get("role")
                content = msg.get("content")
                
                if not role or not content:
                    logger.warning(f"消息 {i} 缺少必要字段 - role: {role}, content: {content}")
                    continue
                
                # 确保content是字符串
                if not isinstance(content, str):
                    if isinstance(content, (dict, list)):
                        # 如果content是复杂对象，转换为JSON字符串
                        content = json.dumps(content, ensure_ascii=False)
                        logger.debug(f"将复杂content转换为字符串: {content[:100]}...")
                    else:
                        content = str(content)
                
                if role == "user":
                    contents.append({"parts": [{"text": content}]})
                elif role == "assistant":
                    # Gemini的assistant角色需要特殊处理，通常是模型输出
                    # 这里简化处理，如果需要更复杂的对话历史，可能需要调整
                    contents.append({"parts": [{"text": content}]})
                else:
                    logger.warning(f"未知的消息角色: {role}, 跳过该消息")
                    
            except Exception as e:
                logger.error(f"处理消息 {i} 时出错: {e}, 消息内容: {msg}")
                continue
        
        logger.debug(f"🔍 Gemini消息转换完成 - 转换成功: {len(contents)}/{len(messages)}")
        
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

        logger.debug(f"🔍 Gemini API调用开始 - 模型: {model}, payload大小: {len(json.dumps(payload))} 字符")
        
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
            
            # 🔧 增强响应格式检查 - 安全处理嵌套数据结构
            try:
                logger.debug(f"Gemini API原始响应结构: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}...")
                
                # 检查响应格式 - 安全字典访问
                if not isinstance(result, dict):
                    raise ValueError(f"响应不是字典类型: {type(result)}")
                
                if "candidates" not in result:
                    raise ValueError(f"响应缺少'candidates'字段: {list(result.keys())}")
                
                candidates = result["candidates"]
                if not isinstance(candidates, list) or not candidates:
                    raise ValueError(f"candidates字段无效: {type(candidates)}, 长度: {len(candidates) if isinstance(candidates, list) else 'N/A'}")
                    
                candidate = candidates[0]
                if not isinstance(candidate, dict):
                    raise ValueError(f"候选项不是字典类型: {type(candidate)}")
                
                if "content" not in candidate:
                    raise ValueError(f"候选项缺少'content'字段: {list(candidate.keys())}")
                    
                content = candidate["content"]
                if not isinstance(content, dict):
                    raise ValueError(f"content不是字典类型: {type(content)}")
                
                if "parts" not in content:
                    raise ValueError(f"content缺少'parts'字段: {list(content.keys())}")
                    
                parts = content["parts"]
                if not isinstance(parts, list) or not parts:
                    raise ValueError(f"parts字段无效: {type(parts)}, 长度: {len(parts) if isinstance(parts, list) else 'N/A'}")
                    
                part = parts[0]
                if not isinstance(part, dict):
                    raise ValueError(f"part不是字典类型: {type(part)}")
                
                if "text" not in part:
                    raise ValueError(f"part缺少'text'字段: {list(part.keys())}")
                    
                text_content = part["text"]
                if not isinstance(text_content, str):
                    logger.warning(f"text字段不是字符串类型: {type(text_content)}, 尝试转换")
                    text_content = str(text_content)
                
                await temp_client.aclose()
                logger.info(f"✅ Gemini响应解析成功，内容长度: {len(text_content)}")
                return text_content
                
            except Exception as parse_error:
                logger.error(f"Gemini响应解析失败: {parse_error}")
                logger.error(f"原始响应内容: {json.dumps(result, ensure_ascii=False, indent=2)}")
                raise ValueError(f"Gemini响应格式解析错误: {parse_error}")
            
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
                    
                    # 🔧 备用响应的安全格式检查
                    try:
                        if (isinstance(result, dict) and
                            "candidates" in result and isinstance(result["candidates"], list) and
                            len(result["candidates"]) > 0 and isinstance(result["candidates"][0], dict) and
                            "content" in result["candidates"][0] and isinstance(result["candidates"][0]["content"], dict) and
                            "parts" in result["candidates"][0]["content"] and isinstance(result["candidates"][0]["content"]["parts"], list) and
                            len(result["candidates"][0]["content"]["parts"]) > 0 and isinstance(result["candidates"][0]["content"]["parts"][0], dict) and
                            "text" in result["candidates"][0]["content"]["parts"][0]):
                            
                            backup_text = result["candidates"][0]["content"]["parts"][0]["text"]
                            if not isinstance(backup_text, str):
                                backup_text = str(backup_text)
                            
                            await backup_client.aclose()
                            logger.info("✅ 使用备用网络配置成功恢复")
                            return backup_text
                        else:
                            raise ValueError(f"备用响应格式无效: {list(result.keys()) if isinstance(result, dict) else type(result)}")
                    except Exception as backup_parse_error:
                        logger.error(f"备用响应解析失败: {backup_parse_error}")
                        raise ValueError(f"备用响应格式解析错误: {backup_parse_error}")
                        
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