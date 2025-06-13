from enum import Enum
import httpx
import json
import logging
import os
import time
from typing import Dict, Any, Optional, List, Callable
import asyncio

from .config_service import ConfigService

logger = logging.getLogger(__name__)

class LLMProvider(Enum):
    """LLM提供商枚举"""
    VLLM = "vllm"
    OPENAI = "openai"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    FALLBACK = "fallback"  # 新增：内置回退机制

class LLMInterface:
    """增强的LLM统一接口"""
    
    def __init__(self, provider_override: Optional[str] = None):
        self.config = ConfigService().get_config().llm
        
        # 使用传入的提供商覆盖或从配置读取
        provider_name = provider_override or self.config.provider
        
        if provider_name.lower() == 'vllm':
            self.provider = LLMProvider.VLLM
        elif provider_name.lower() == 'openai':
            self.provider = LLMProvider.OPENAI
        elif provider_name.lower() == 'gemini':
            self.provider = LLMProvider.GEMINI
        elif provider_name.lower() == 'deepseek':
            self.provider = LLMProvider.DEEPSEEK
        else:
            logger.warning(f"未知提供商: {provider_name}, 自动检测可用提供商")
            self.provider = self._detect_provider()
        
        # 初始化HTTP客户端
        self.client = httpx.AsyncClient(timeout=60.0)
        self.retry_count = 3
        self.retry_delay = 2  # 初始重试延迟（秒）
        
        # 缓存配置
        self.enable_cache = False  # 默认禁用，可通过方法启用
        self._response_cache = {}  # 简单的内存缓存
        
        logger.info(f"LLM接口初始化, 提供商: {self.provider.value}")
    
    def _detect_provider(self) -> LLMProvider:
        """自动检测可用的LLM提供商"""
        config = self.config
        
        # 检查API密钥配置
        if config.provider == "gemini" and config.api_key:
            return LLMProvider.GEMINI
        elif config.provider == "openai" and config.api_key:
            return LLMProvider.OPENAI
        elif config.provider == "deepseek" and config.api_key:
            return LLMProvider.DEEPSEEK
        elif config.provider == "vllm":
            return LLMProvider.VLLM
        
        # 检查环境变量
        if os.getenv('GEMINI_API_KEY'):
            return LLMProvider.GEMINI
        elif os.getenv('OPENAI_API_KEY'):
            return LLMProvider.OPENAI
        elif os.getenv('DEEPSEEK_API_KEY'):
            return LLMProvider.DEEPSEEK
        
        # 默认返回FALLBACK
        logger.warning("未找到有效的LLM提供商配置，使用内置回退机制")
        return LLMProvider.FALLBACK
    
    def enable_response_cache(self, enabled: bool = True):
        """启用/禁用响应缓存"""
        self.enable_cache = enabled
        logger.info(f"LLM响应缓存: {'启用' if enabled else '禁用'}")
    
    def clear_cache(self):
        """清除响应缓存"""
        self._response_cache.clear()
    
    async def generate_text(self, prompt: str, **kwargs) -> str:
        """生成文本（通用接口）"""
        cache_key = self._make_cache_key(prompt, kwargs)
        
        # 检查缓存
        if self.enable_cache and cache_key in self._response_cache:
            logger.debug("使用缓存的LLM响应")
            return self._response_cache[cache_key]
        
        # 重试逻辑
        for attempt in range(self.retry_count):
            try:
                response = await self._call_api(prompt, **kwargs)
                
                # 缓存响应
                if self.enable_cache:
                    self._response_cache[cache_key] = response
                
                return response
            except Exception as e:
                logger.warning(f"LLM调用失败 (尝试 {attempt+1}/{self.retry_count}): {e}")
                
                if attempt < self.retry_count - 1:
                    # 指数退避策略
                    delay = self.retry_delay * (2 ** attempt)
                    logger.info(f"等待 {delay} 秒后重试...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"所有重试失败，使用回退机制")
                    if self.provider != LLMProvider.FALLBACK:
                        # 尝试使用回退机制
                        try:
                            fallback_response = await self._call_fallback(prompt)
                            return fallback_response
                        except Exception as fallback_e:
                            logger.error(f"回退机制也失败了: {fallback_e}")
                    
                    # 最终抛出异常
                    raise RuntimeError(f"无法生成文本，所有尝试均失败: {e}")
    
    def _make_cache_key(self, prompt: str, kwargs: Dict[str, Any]) -> str:
        """生成缓存键"""
        # 简单哈希，生产环境中可能需要更复杂的实现
        import hashlib
        key_content = prompt + json.dumps(kwargs, sort_keys=True)
        return hashlib.md5(key_content.encode()).hexdigest()
    
    async def generate_code(self, description: str, language: str = "python") -> Dict[str, str]:
        """生成代码，并返回思考过程和代码"""
        prompt = self._build_code_prompt(description, language)
        
        try:
            response = await self.generate_text(prompt)
            code = self._extract_code(response, language)
            
            # 保存原始思考过程
            thinking = response
            if len(thinking) > 2000:
                thinking = thinking[:1000] + "\n... (内容过长，已截断) ...\n" + thinking[-1000:]
            
            return {
                "code": code,
                "thinking": thinking,
                "success": True
            }
        except Exception as e:
            logger.error(f"代码生成失败: {e}")
            raise RuntimeError(f"无法生成代码: {e}")
    
    async def generate_reasoning(self, task_description: str, available_tools: List[str],
                                previous_steps: List[Dict] = None,
                                browser_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """生成推理步骤和工具调用"""
        prompt = self._build_reasoning_prompt(task_description, available_tools, previous_steps, browser_context)
        
        try:
            response = await self.generate_text(prompt)
            return self._parse_reasoning_response(response)
        except Exception as e:
            logger.error(f"推理生成失败: {e}")
            return {
                "thinking": f"处理过程中发生错误: {e}",
                "action": "error",
                "tool": None,
                "parameters": {},
                "confidence": 0.0
            }
    
    async def generate_task_summary(self, task_description: str, steps: List[Dict], 
                                   final_outputs: List[str]) -> str:
        """生成任务执行总结"""
        prompt = self._build_summary_prompt(task_description, steps, final_outputs)
        
        try:
            response = await self.generate_text(prompt)
            return response.strip()
        except Exception as e:
            logger.error(f"任务总结生成失败: {e}")
            return f"任务完成，共执行 {len(steps)} 个步骤。最终输出: {'; '.join(final_outputs[:3])}"
    
    async def check_task_completion(self, task_description: str, steps: List[Dict], 
                                   current_outputs: List[str]) -> Dict[str, Any]:
        """检查任务是否完成"""
        prompt = self._build_completion_check_prompt(task_description, steps, current_outputs)
        
        try:
            response = await self.generate_text(prompt)
            return self._parse_completion_response(response)
        except Exception as e:
            logger.error(f"完成检查失败: {e}")
            return {"completed": False, "confidence": 0.0, "reason": f"错误: {e}"}

    async def _call_api(self, prompt: str, **kwargs) -> str:
        """调用相应的API"""
        if self.provider == LLMProvider.VLLM:
            return await self._call_vllm(prompt, **kwargs)
        elif self.provider == LLMProvider.OPENAI:
            return await self._call_openai(prompt, **kwargs)
        elif self.provider == LLMProvider.GEMINI:
            return await self._call_gemini(prompt, **kwargs)
        elif self.provider == LLMProvider.DEEPSEEK:
            return await self._call_deepseek(prompt, **kwargs)
        elif self.provider == LLMProvider.FALLBACK:
            return await self._call_fallback(prompt, **kwargs)
        else:
            raise ValueError(f"不支持的提供商: {self.provider}")
    
    async def _call_vllm(self, prompt: str, **kwargs) -> str:
        """调用vLLM本地服务"""
        api_url = self.config.api_url or "http://localhost:8000"
        
        # 合并默认参数和传入参数
        payload = {
            "model": kwargs.get("model", "default"),
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": kwargs.get("max_tokens", 1024),
            "temperature": kwargs.get("temperature", 0.1)
        }
        
        # 如果kwargs包含"messages"，则直接使用它而不是封装prompt
        if "messages" in kwargs:
            payload["messages"] = kwargs["messages"]
        
        response = await self.client.post(
            f"{api_url}/v1/chat/completions",
            json=payload
        )
        response.raise_for_status()
        
        result = response.json()
        return result["choices"][0]["message"]["content"]
    
    async def _call_openai(self, prompt: str, **kwargs) -> str:
        """调用OpenAI API"""
        api_key = self.config.api_key or os.getenv('OPENAI_API_KEY')
        api_base = self.config.api_url or os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1')
        model = kwargs.get("model", self.config.model or "gpt-3.5-turbo")
        
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": kwargs.get("max_tokens", 1024),
            "temperature": kwargs.get("temperature", 0.1)
        }
        
        # 如果kwargs包含"messages"，则直接使用它
        if "messages" in kwargs:
            payload["messages"] = kwargs["messages"]
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        response = await self.client.post(
            f"{api_base}/chat/completions",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        
        result = response.json()
        return result["choices"][0]["message"]["content"]
    
    async def _call_gemini(self, prompt: str, **kwargs) -> str:
        """调用Google Gemini API"""
        api_key = self.config.api_key or os.getenv('GEMINI_API_KEY')
        api_url = self.config.api_url or os.getenv('GEMINI_API_URL', 'https://generativelanguage.googleapis.com/v1beta')
        
        # 使用配置中的模型或默认值
        model_name = kwargs.get("model", self.config.model or "gemini-1.5-flash")
        
        # 验证模型名称
        valid_models = [
            'gemini-1.5-flash', 'gemini-1.5-pro', 
            'gemini-1.0-pro', 'gemini-pro'
        ]
        
        if model_name not in valid_models:
            logger.warning(f"无效的Gemini模型 '{model_name}'，使用默认 'gemini-1.5-flash'")
            model_name = 'gemini-1.5-flash'
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": kwargs.get("temperature", 0.1),
                "maxOutputTokens": kwargs.get("max_tokens", 1024)
            }
        }
        
        try:
            response = await self.client.post(
                f"{api_url}/models/{model_name}:generateContent?key={api_key}",
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logger.error(f"Gemini API调用失败: {e}")
            
            # 如果使用了不稳定的模型，尝试回退到稳定版本
            if model_name != 'gemini-1.5-flash':
                logger.info("使用稳定模型 'gemini-1.5-flash' 重试")
                response = await self.client.post(
                    f"{api_url}/models/gemini-1.5-flash:generateContent?key={api_key}",
                    json=payload
                )
                response.raise_for_status()
                result = response.json()
                return result["candidates"][0]["content"]["parts"][0]["text"]
            else:
                raise
    
    async def _call_deepseek(self, prompt: str, **kwargs) -> str:
        """调用DeepSeek API"""
        api_key = self.config.api_key or os.getenv('DEEPSEEK_API_KEY')
        api_url = self.config.api_url or os.getenv('DEEPSEEK_API_URL', 'https://api.deepseek.com/v1')
        
        payload = {
            "model": kwargs.get("model", "deepseek-coder"),
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": kwargs.get("max_tokens", 1024),
            "temperature": kwargs.get("temperature", 0.1)
        }
        
        # 如果kwargs包含"messages"，则直接使用它
        if "messages" in kwargs:
            payload["messages"] = kwargs["messages"]
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        response = await self.client.post(
            f"{api_url}/chat/completions",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        
        result = response.json()
        return result["choices"][0]["message"]["content"]
    
    async def _call_fallback(self, prompt: str, **kwargs) -> str:
        """内置回退机制，用于在所有API调用失败时提供基本响应"""
        logger.warning("使用回退机制生成响应")
        
        # 简单模板响应
        if "code" in prompt.lower() or "generate_code" in kwargs.get("context", ""):
            return """
我无法生成完整的代码，但这里是一个简单的框架供参考：

```python
def main():
    # 请在这里实现你的代码
    print("Hello, world!")

if __name__ == "__main__":
    main()
```

建议你参考文档或寻求其他资源来完成实现。
            """
        elif "reasoning" in prompt.lower():
            return """
THINKING:
由于LLM服务暂时不可用，我只能提供一个基本分析。基于任务描述，我需要执行一个简单操作。

ACTION: error

TOOL: None

PARAMETERS:
{}

CONFIDENCE: 0.1
            """
        else:
            return f"抱歉，我目前无法提供详细回答。请稍后再试或调整您的请求。"
    
    # ... 其余实现代码保持与原LLMClient类似 ...
    # 以下是一些关键方法的实现示例

    def _build_code_prompt(self, description: str, language: str) -> str:
        """构建代码生成提示，增强思考过程捕获"""
        return f"""请根据以下描述生成{language}代码。

首先，详细思考如何解决这个问题，包括可能的算法、数据结构以及实现步骤。
在你的思考过程中，分析不同的解决方案并选择最佳方案。

描述：{description}

要求：
1. 先详细描述你的思考过程，包括你考虑的不同方法
2. 代码应该完整且可执行
3. 包含必要的注释
4. 处理可能的异常情况
5. 输出结果到控制台

==== 思考过程 ====
(请在这里详细写出你的思考过程，包括算法选择、数据结构、实现思路等)

==== 代码实现 ====
(在此处生成最终代码)
"""
    
    def _extract_code(self, response: str, language: str) -> str:
        """从响应中提取代码，支持分离思考过程和代码"""
        import re
        
        # 首先查找是否有专用的"代码实现"部分
        code_section_pattern = r'==== 代码实现 ====\s*(.*?)(?:$|==== )'
        section_match = re.search(code_section_pattern, response, re.DOTALL)
        if section_match:
            # 在找到的代码实现部分中寻找代码块
            section_content = section_match.group(1).strip()
            
            # 查找带有语言标记的代码块
            code_pattern = rf'```{language}\s*(.*?)```'
            match = re.search(code_pattern, section_content, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
                
            # 查找通用代码块
            code_pattern = r'```\s*(.*?)```'
            match = re.search(code_pattern, section_content, re.DOTALL)
            if match:
                return match.group(1).strip()
                
            # 如果代码部分没有用代码块标记，直接返回该部分内容
            return section_content
        
        # 传统方式：直接在整个响应中寻找代码块
        # 查找带有语言标记的代码块
        code_pattern = rf'```{language}\s*(.*?)```'
        match = re.search(code_pattern, response, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # 查找通用代码块
        code_pattern = r'```\s*(.*?)```'
        match = re.search(code_pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # 如果没有代码块标记，返回整个响应
        return response.strip()
    
    async def close(self):
        """关闭客户端连接"""
        await self.client.aclose()
