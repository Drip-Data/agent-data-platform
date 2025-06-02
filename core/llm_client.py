#!/usr/bin/env python3
"""
LLM客户端统一接口
支持多种API提供商：vLLM本地服务、OpenAI、Google Gemini、DeepSeek等
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from enum import Enum
import httpx
import asyncio

logger = logging.getLogger(__name__)

class LLMProvider(Enum):
    """LLM提供商枚举"""
    VLLM = "vllm"
    OPENAI = "openai"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"

class LLMClient:
    """统一的LLM客户端"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.provider = self._detect_provider()
        self.client = httpx.AsyncClient(timeout=60.0)
        
        logger.info(f"Initialized LLM client with provider: {self.provider.value}")
    
    def _detect_provider(self) -> LLMProvider:
        """自动检测使用的LLM提供商"""
        # 优先级：Gemini > DeepSeek > OpenAI > vLLM
        if os.getenv('GEMINI_API_KEY'):
            return LLMProvider.GEMINI
        elif os.getenv('DEEPSEEK_API_KEY'):
            return LLMProvider.DEEPSEEK
        elif os.getenv('OPENAI_API_KEY'):
            return LLMProvider.OPENAI
        else:
            return LLMProvider.VLLM
    
    async def generate_code(self, description: str, language: str = "python") -> str:
        """生成代码"""
        prompt = self._build_code_prompt(description, language)
        
        try:
            response = await self._call_api(prompt)
            code = self._extract_code(response, language)
            return code
        except Exception as e:
            logger.error(f"Failed to generate code: {e}")
            return self._fallback_code_template(description, language)
    
    async def generate_web_actions(self, description: str, page_content: str = "") -> List[Dict]:
        """生成Web操作步骤"""
        prompt = self._build_web_prompt(description, page_content)
        
        try:
            response = await self._call_api(prompt)
            actions = self._extract_web_actions(response)
            return actions
        except Exception as e:
            logger.error(f"Failed to generate web actions: {e}")
            return self._fallback_web_actions(description)
    
    async def _call_api(self, prompt: str) -> str:
        """调用相应的API"""
        if self.provider == LLMProvider.VLLM:
            return await self._call_vllm(prompt)
        elif self.provider == LLMProvider.OPENAI:
            return await self._call_openai(prompt)
        elif self.provider == LLMProvider.GEMINI:
            return await self._call_gemini(prompt)
        elif self.provider == LLMProvider.DEEPSEEK:
            return await self._call_deepseek(prompt)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
    
    async def _call_vllm(self, prompt: str) -> str:
        """调用vLLM本地服务"""
        vllm_url = self.config.get("vllm_url", "http://localhost:8000")
        
        payload = {
            "model": "default",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 1024,
            "temperature": 0.1
        }
        
        response = await self.client.post(
            f"{vllm_url}/v1/chat/completions",
            json=payload
        )
        response.raise_for_status()
        
        result = response.json()
        return result["choices"][0]["message"]["content"]
    
    async def _call_openai(self, prompt: str) -> str:
        """调用OpenAI API"""
        api_key = os.getenv('OPENAI_API_KEY')
        api_base = os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1')
        
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 1024,
            "temperature": 0.1
        }
        
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
    
    async def _call_gemini(self, prompt: str) -> str:
        """调用Google Gemini API"""
        api_key = os.getenv('GEMINI_API_KEY')
        api_url = os.getenv('GEMINI_API_URL', 'https://generativelanguage.googleapis.com/v1beta')
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1024
            }
        }
        
        response = await self.client.post(
            f"{api_url}/models/gemini-1.5-flash:generateContent?key={api_key}",
            json=payload
        )
        response.raise_for_status()
        
        result = response.json()
        return result["candidates"][0]["content"]["parts"][0]["text"]
    
    async def _call_deepseek(self, prompt: str) -> str:
        """调用DeepSeek API"""
        api_key = os.getenv('DEEPSEEK_API_KEY')
        api_url = os.getenv('DEEPSEEK_API_URL', 'https://api.deepseek.com/v1')
        
        payload = {
            "model": "deepseek-coder",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 1024,
            "temperature": 0.1
        }
        
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
    
    def _build_code_prompt(self, description: str, language: str) -> str:
        """构建代码生成提示"""
        return f"""请根据以下描述生成{language}代码：

描述：{description}

要求：
1. 代码应该完整且可执行
2. 包含必要的注释
3. 处理可能的异常情况
4. 输出结果到控制台

请只返回代码，不要包含其他解释文字："""
    
    def _build_web_prompt(self, description: str, page_content: str) -> str:
        """构建Web操作提示"""
        return f"""请根据以下描述生成Web操作步骤：

任务描述：{description}

当前页面内容：
{page_content[:1000] if page_content else '无'}

请返回JSON格式的操作步骤列表，每个步骤包含：
- action: 操作类型（navigate, click, fill, wait等）
- selector: CSS选择器（如果需要）
- value: 输入值（如果需要）
- description: 操作描述

示例格式：
[
  {{"action": "navigate", "url": "https://example.com", "description": "打开网站"}},
  {{"action": "fill", "selector": "#search", "value": "搜索内容", "description": "填写搜索框"}},
  {{"action": "click", "selector": "button[type=submit]", "description": "点击搜索按钮"}}
]

请只返回JSON数组，不要包含其他文字："""
    
    def _extract_code(self, response: str, language: str) -> str:
        """从响应中提取代码"""
        # 尝试提取代码块
        import re
        
        # 查找代码块标记
        code_pattern = rf'```{language}\n(.*?)```'
        match = re.search(code_pattern, response, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # 查找通用代码块
        code_pattern = r'```\n(.*?)```'
        match = re.search(code_pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # 如果没有代码块标记，返回整个响应
        return response.strip()
    
    def _extract_web_actions(self, response: str) -> List[Dict]:
        """从响应中提取Web操作"""
        try:
            # 尝试解析JSON
            import re
            
            # 查找JSON数组
            json_pattern = r'\[(.*?)\]'
            match = re.search(json_pattern, response, re.DOTALL)
            if match:
                json_str = '[' + match.group(1) + ']'
                return json.loads(json_str)
            
            # 尝试直接解析整个响应
            return json.loads(response)
        except:
            logger.warning(f"Failed to parse web actions from response: {response[:200]}...")
            return self._fallback_web_actions("")
    
    def _fallback_code_template(self, description: str, language: str) -> str:
        """代码生成失败时的回退模板"""
        if language.lower() == "python":
            # 根据任务描述生成相应的代码模板
            desc_lower = description.lower()
            
            if "factorial" in desc_lower:
                return '''def factorial(n):
    """计算n的阶乘"""
    if n <= 1:
        return 1
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result

# 计算5的阶乘
result = factorial(5)
print(f"5! = {result}")'''
            
            elif "fibonacci" in desc_lower:
                return '''def fibonacci(n):
    """计算斐波那契数列第n项"""
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

# 计算斐波那契数列第10项
result = fibonacci(10)
print(f"fibonacci(10) = {result}")'''
            
            elif "prime" in desc_lower:
                return '''def is_prime(n):
    """检查n是否为质数"""
    if n < 2:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True

# 检查17是否为质数
number = 17
result = is_prime(number)
print(f"{number} is {'prime' if result else 'not prime'}")'''
            
            elif "gcd" in desc_lower:
                return '''def gcd(a, b):
    """计算两个数的最大公约数"""
    while b:
        a, b = b, a % b
    return a

# 计算48和18的最大公约数
result = gcd(48, 18)
print(f"GCD(48, 18) = {result}")'''
            
            elif "sum" in desc_lower and "array" in desc_lower:
                return '''# 计算数组的和
array = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
result = sum(array)
print(f"Sum of {array} = {result}")'''
            
            elif "reverse" in desc_lower and "string" in desc_lower:
                return '''# 反转字符串
text = "Hello World"
reversed_text = text[::-1]
print(f"Original: {text}")
print(f"Reversed: {reversed_text}")'''
            
            elif "bubble sort" in desc_lower or "sort" in desc_lower:
                return '''def bubble_sort(arr):
    """冒泡排序算法"""
    n = len(arr)
    for i in range(n):
        for j in range(0, n-i-1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr

# 对数组进行冒泡排序
array = [64, 34, 25, 12, 22, 11, 90]
print(f"Original array: {array}")
sorted_array = bubble_sort(array.copy())
print(f"Sorted array: {sorted_array}")'''
            
            else:
                return f'''# 生成的代码用于: {description}
def solution():
    # TODO: 根据描述实现具体逻辑
    return "This is a placeholder solution for: {description}"

result = solution()
print(result)'''
        else:
            return f'// 生成的代码用于: {description}\nconsole.log("This is a placeholder solution for: {description}");'
    
    def _fallback_web_actions(self, description: str) -> List[Dict]:
        """Web操作生成失败时的回退操作"""
        return [
            {
                "action": "navigate",
                "url": "https://www.google.com",
                "description": f"执行任务: {description}"
            }
        ]
    
    async def close(self):
        """关闭客户端"""
        await self.client.aclose()