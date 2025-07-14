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
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout=120.0, connect=30.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            trust_env=False
        )
        
        # 验证并使用有效的Gemini模型名称
        # 优先从配置文件中读取模型，然后是gemini_default_model，最后是默认值
        self._default_model = (
            self.config.get('model') or 
            self.config.get('gemini_default_model') or 
            'gemini-2.5-flash-preview-05-20'
        )
        
        # 🔧 动态读取支持的模型列表，避免硬编码
        # 如果配置中指定了supported_models，使用配置的列表
        # 否则创建包含当前配置模型的基础列表
        config_supported_models = self.config.get('gemini_supported_models')
        if config_supported_models:
            self._supported_models = config_supported_models
        else:
            # 基础支持模型列表 + 当前配置的模型（避免警告）
            base_models = [
                'gemini-2.5-pro', 'gemini-2.5-flash', 
                'gemini-2.5-flash-lite-preview-06-17',
                'gemini-2.5-flash-preview-05-20',
                'gemini-2.0-flash', 'gemini-2.0-pro', 
                'gemini-1.0-pro', 'gemini-pro', 'gemini-1.5-flash'
            ]
            # 确保当前配置的模型在支持列表中
            if self._default_model and self._default_model not in base_models:
                base_models.append(self._default_model)
            self._supported_models = base_models
        
        if not self.api_key:
            logger.warning("GEMINI_API_KEY 环境变量或配置中未设置。GeminiProvider 可能无法正常工作。")

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.1, # Gemini的默认温度
        max_tokens: int = 32768, # Increased default for complex tasks
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None, # Gemini的工具调用可能不同
        tool_choice: Optional[str] = None,
        timeout: int = 120,
        **kwargs
    ) -> Any:
        """
        根据给定的消息生成 Google Gemini LLM 响应。
        注意：Gemini API不支持stop_sequences参数，会被自动忽略。
        """
        # 提取 stop_sequences
        stop_sequences = kwargs.pop('stop_sequences', [])
        if stop_sequences:
            logger.debug(f"🔧 Applying stop_sequences for Gemini: {stop_sequences}")

        # 🔧 智能模型验证：优先使用配置的模型，避免不必要的警告
        if model not in self._supported_models:
            # 如果请求的模型是配置中指定的模型，直接接受
            if model == self._default_model:
                logger.debug(f"使用配置指定的模型: {model}")
            else:
                logger.warning(f"模型 {model} 不受支持，使用默认模型 {self._default_model}")
                model = self._default_model
        
        # 🔧 修复消息格式转换 - 支持角色交替和内容合并
        logger.debug(f"🔍 Gemini消息转换开始 - 输入消息数: {len(messages)}")
        
        contents = []
        current_role = None
        merged_content = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if not role:
                logger.warning(f"消息缺少 'role' 字段, 跳过: {msg}")
                continue

            # 将 'assistant' 映射到 'model'
            if role == "assistant":
                role = "model"
            
            # 确保角色是 'user' 或 'model'
            if role not in ["user", "model"]:
                logger.warning(f"未知的消息角色: {role}, 跳过该消息")
                continue

            if current_role is None:
                current_role = role

            if role == current_role:
                # 如果角色相同，合并内容
                merged_content.append(str(content))
            else:
                # 如果角色切换，添加前一个角色的合并内容
                if merged_content:
                    contents.append({
                        "role": current_role,
                        "parts": [{"text": "\n\n".join(merged_content)}]
                    })
                # 开始新的角色内容
                current_role = role
                merged_content = [str(content)]

        # 添加最后一部分合并的内容
        if merged_content:
            contents.append({
                "role": current_role,
                "parts": [{"text": "\n\n".join(merged_content)}]
            })

        logger.debug(f"🔍 Gemini消息转换完成 - 转换后消息数: {len(contents)}")
        
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "candidateCount": 1,
                "stopSequences": stop_sequences,
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
            response = await self.client.post(
                f"{self.api_url}/models/{model}:generateContent?key={self.api_key}",
                json=payload,
                timeout=timeout
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
                
                # 🔧 新增：提取usage metadata（token信息）
                usage_metadata = result.get('usageMetadata', {})
                usage_info = None
                if usage_metadata:
                    usage_info = {
                        'prompt_tokens': usage_metadata.get('promptTokenCount', 0),
                        'completion_tokens': usage_metadata.get('candidatesTokenCount', 0),
                        'total_tokens': usage_metadata.get('totalTokenCount', 0),
                        'data_source': 'real_api',
                        'model': model
                    }
                    logger.info(f"✅ 获取到真实token使用数据: prompt={usage_info['prompt_tokens']}, completion={usage_info['completion_tokens']}")
                else:
                    logger.warning("⚠️ Gemini API响应中没有usageMetadata字段")
                
                logger.info(f"✅ Gemini响应解析成功，内容长度: {len(text_content)}")
                
                # 返回新格式：包含content和usage信息
                return {
                    'content': text_content,
                    'usage': usage_info,
                    'metadata': {
                        'model': model,
                        'provider': 'gemini',
                        'api_response': result  # 保留原始响应用于调试
                    }
                }
                
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
                        timeout=httpx.Timeout(timeout=180.0, connect=60.0),
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
                            
                            # 备用响应也提取token信息
                            backup_usage_metadata = result.get('usageMetadata', {})
                            backup_usage_info = None
                            if backup_usage_metadata:
                                backup_usage_info = {
                                    'prompt_tokens': backup_usage_metadata.get('promptTokenCount', 0),
                                    'completion_tokens': backup_usage_metadata.get('candidatesTokenCount', 0),
                                    'total_tokens': backup_usage_metadata.get('totalTokenCount', 0),
                                    'data_source': 'real_api_backup',
                                    'model': stable_model
                                }
                            
                            await backup_client.aclose()
                            logger.info("✅ 使用备用网络配置成功恢复")
                            return {
                                'content': backup_text,
                                'usage': backup_usage_info,
                                'metadata': {
                                    'model': stable_model,
                                    'provider': 'gemini',
                                    'backup_recovery': True
                                }
                            }
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
        except httpx.RemoteProtocolError as e:
            logger.error(f"Gemini API 连接协议错误: {e}")
            # 🔧 专门处理 RemoteProtocolError - 服务器连接中断
            return await self._handle_remote_protocol_error(e, payload, model, timeout)
        except httpx.RequestError as e:
            logger.error(f"Gemini API 请求错误: {e}")
            # 🔧 对其他请求错误也尝试重试机制
            if any(keyword in str(e).lower() for keyword in ['timeout', 'connection', 'network', 'disconnect']):
                logger.info("检测到网络相关错误，尝试重试...")
                return await self._handle_network_error_retry(e, payload, model, timeout)
            raise
        except Exception as e:
            logger.error(f"调用 Gemini API 失败: {e}")
            raise

    async def count_tokens(self, text: str, model: str) -> int:
        """
        使用Gemini SDK的真实API计算给定文本在特定模型中的准确token数量
        """
        try:
            # 🔧 智能模型验证：优先使用配置的模型
            if model not in self._supported_models:
                # 如果请求的模型是配置中指定的模型，直接接受
                if model == self._default_model:
                    logger.debug(f"Token计数使用配置指定的模型: {model}")
                else:
                    logger.warning(f"模型 {model} 不受支持，使用默认模型 {self._default_model}")
                    model = self._default_model
            
            # 构造请求payload
            payload = {
                "contents": [{"parts": [{"text": text}]}]
            }
            
            # 调用Gemini count_tokens API
            response = await self.client.post(
                f"{self.api_url}/models/{model}:countTokens?key={self.api_key}",
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            
            # 解析响应
            if isinstance(result, dict) and "totalTokens" in result:
                token_count = result["totalTokens"]
                logger.debug(f"✅ Gemini API token计数: {token_count} tokens for {len(text)} characters")
                return int(token_count)
            else:
                logger.warning(f"Gemini token计数API响应格式异常: {result}")
                # 回退到改进的估算方法
                return self._accurate_token_estimation_fallback(text)
                
        except httpx.RemoteProtocolError as e:
            logger.warning(f"Gemini token计数API 连接协议错误: {e}, 使用估算方法")
            return self._accurate_token_estimation_fallback(text)
        except httpx.HTTPStatusError as e:
            logger.warning(f"Gemini token计数API HTTP错误: {e.response.status_code} - {e.response.text}")
            return self._accurate_token_estimation_fallback(text)
        except httpx.RequestError as e:
            logger.warning(f"Gemini token计数API 请求错误: {e}, 使用估算方法")
            return self._accurate_token_estimation_fallback(text)
        except Exception as e:
            logger.warning(f"Gemini token计数API调用失败: {e}, 使用估算方法")
            return self._accurate_token_estimation_fallback(text)
    
    def _accurate_token_estimation_fallback(self, text: str) -> int:
        """
        当API调用失败时使用的高精度估算方法
        基于Gemini tokenizer特性的改进估算
        """
        if not text:
            return 0
        
        # 中文字符统计
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        japanese_chars = sum(1 for c in text if '\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff')
        korean_chars = sum(1 for c in text if '\uac00' <= c <= '\ud7af')
        
        # 其他字符
        other_chars = len(text) - chinese_chars - japanese_chars - korean_chars
        
        # 基于Gemini tokenizer的改进估算
        # 中文: ~1.5 chars/token, 日文: ~2 chars/token, 韩文: ~2 chars/token, 英文: ~4 chars/token
        estimated_tokens = int(
            chinese_chars / 1.5 + 
            japanese_chars / 2.0 + 
            korean_chars / 2.0 + 
            other_chars / 4.0
        )
        
        # 考虑特殊标记和格式
        special_tokens = text.count('<') + text.count('>') + text.count('{') + text.count('}')
        estimated_tokens += int(special_tokens * 0.5)  # 特殊标记通常占用额外token
        
        return max(estimated_tokens, 1)

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
    
    async def _handle_remote_protocol_error(self, error: Exception, payload: dict, model: str, timeout: int) -> str:
        """
        🔧 专门处理 RemoteProtocolError - 服务器连接中断
        
        这种错误通常由以下原因引起：
        1. 网络连接不稳定
        2. 服务器负载过高主动断开连接
        3. 请求过大导致服务器提前关闭
        4. API速率限制触发
        """
        import asyncio
        
        logger.warning(f"🚨 RemoteProtocolError detected: {error}")
        logger.info("🔄 启动多层重试策略...")
        
        # 策略1: 立即重试一次（可能是临时网络抖动）
        try:
            logger.info("📡 策略1: 立即重试（网络抖动恢复）")
            await asyncio.sleep(1)  # 短暂延迟
            
            response = await self.client.post(
                f"{self.api_url}/models/{model}:generateContent?key={self.api_key}",
                json=payload,
                timeout=timeout
            )
            response.raise_for_status()
            result = response.json()
            
            return self._parse_gemini_response(result)
            
        except Exception as retry1_error:
            logger.warning(f"策略1失败: {retry1_error}")
        
        # 策略2: 使用新的客户端连接和更长超时
        try:
            logger.info("🔄 策略2: 新连接+延长超时（服务器负载问题）")
            await asyncio.sleep(3)  # 等待服务器负载降低
            
            # 创建新的客户端，避免连接复用问题
            fresh_client = httpx.AsyncClient(
                timeout=httpx.Timeout(timeout=timeout*2, connect=60.0),  # 延长超时
                limits=httpx.Limits(max_connections=3, max_keepalive_connections=1),  # 减少并发
                trust_env=False,
                http2=False  # 禁用HTTP/2，使用HTTP/1.1避免协议问题
            )
            
            try:
                response = await fresh_client.post(
                    f"{self.api_url}/models/{model}:generateContent?key={self.api_key}",
                    json=payload,
                    timeout=timeout*2
                )
                response.raise_for_status()
                result = response.json()
                
                return self._parse_gemini_response(result)
                
            finally:
                await fresh_client.aclose()
                
        except Exception as retry2_error:
            logger.warning(f"策略2失败: {retry2_error}")
        
        # 策略3: 使用稳定模型和简化请求
        try:
            logger.info("⚡ 策略3: 稳定模型+简化请求（兼容性问题）")
            await asyncio.sleep(5)  # 更长等待
            
            # 使用最稳定的模型
            fallback_model = 'gemini-1.5-flash'
            simplified_payload = {
                "contents": payload.get("contents", []),
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": min(payload.get("generationConfig", {}).get("maxOutputTokens", 8192), 8192)
                }
            }
            
            fallback_client = httpx.AsyncClient(
                timeout=httpx.Timeout(timeout=180.0, connect=90.0),
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),  # 单连接无复用
                trust_env=False,
                http2=False
            )
            
            try:
                response = await fallback_client.post(
                    f"{self.api_url}/models/{fallback_model}:generateContent?key={self.api_key}",
                    json=simplified_payload,
                    timeout=180
                )
                response.raise_for_status()
                result = response.json()
                
                logger.info("✅ 策略3成功：使用稳定模型恢复")
                return self._parse_gemini_response(result)
                
            finally:
                await fallback_client.aclose()
                
        except Exception as retry3_error:
            logger.error(f"策略3也失败: {retry3_error}")
        
        # 所有策略都失败，抛出详细错误
        error_msg = f"RemoteProtocolError 多重重试失败。原始错误: {error}"
        logger.error(f"❌ {error_msg}")
        raise ConnectionError(error_msg)
    
    async def _handle_network_error_retry(self, error: Exception, payload: dict, model: str, timeout: int) -> str:
        """
        🔧 处理一般网络错误的重试机制
        """
        import asyncio
        
        logger.warning(f"🌐 网络错误检测: {error}")
        
        # 指数退避重试
        for attempt in range(3):
            wait_time = 2 ** attempt  # 2, 4, 8 秒
            logger.info(f"🔄 网络重试 {attempt + 1}/3，等待 {wait_time} 秒...")
            await asyncio.sleep(wait_time)
            
            try:
                response = await self.client.post(
                    f"{self.api_url}/models/{model}:generateContent?key={self.api_key}",
                    json=payload,
                    timeout=timeout + attempt * 30  # 递增超时
                )
                response.raise_for_status()
                result = response.json()
                
                logger.info(f"✅ 网络重试第 {attempt + 1} 次成功")
                return self._parse_gemini_response(result)
                
            except Exception as retry_error:
                logger.warning(f"重试 {attempt + 1} 失败: {retry_error}")
                if attempt == 2:  # 最后一次重试
                    raise error  # 抛出原始错误
        
        raise error
    
    def _parse_gemini_response(self, result: dict) -> str:
        """
        🔧 解析Gemini响应的通用方法
        """
        try:
            if (isinstance(result, dict) and
                "candidates" in result and isinstance(result["candidates"], list) and
                len(result["candidates"]) > 0 and isinstance(result["candidates"][0], dict) and
                "content" in result["candidates"][0] and isinstance(result["candidates"][0]["content"], dict) and
                "parts" in result["candidates"][0]["content"] and isinstance(result["candidates"][0]["content"]["parts"], list) and
                len(result["candidates"][0]["content"]["parts"]) > 0 and isinstance(result["candidates"][0]["content"]["parts"][0], dict) and
                "text" in result["candidates"][0]["content"]["parts"][0]):
                
                text_content = result["candidates"][0]["content"]["parts"][0]["text"]
                if not isinstance(text_content, str):
                    text_content = str(text_content)
                
                return text_content
            else:
                raise ValueError(f"Invalid response structure: {list(result.keys()) if isinstance(result, dict) else type(result)}")
                
        except Exception as parse_error:
            logger.error(f"Response parsing failed: {parse_error}")
            logger.error(f"Raw response: {json.dumps(result, ensure_ascii=False, indent=2)}")
            raise ValueError(f"Gemini response parsing error: {parse_error}")