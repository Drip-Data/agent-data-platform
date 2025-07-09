#!/usr/bin/env python3
"""
Browser Use服务工具模块
集中管理所有工具函数，避免重复导入和作用域问题
"""

import re
import json
import logging
from typing import Dict, Any, Optional, Union

logger = logging.getLogger(__name__)


class JSONExtractor:
    """JSON内容提取工具类 - 解决re模块作用域问题"""
    
    @staticmethod
    def extract_from_markdown(content: str) -> Optional[Dict[str, Any]]:
        """从Markdown代码块中提取JSON内容"""
        try:
            # 查找被markdown代码块包围的JSON
            json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', content, re.DOTALL)
            if json_match:
                json_content = json_match.group(1).strip()
                return json.loads(json_content)
            return None
        except (json.JSONDecodeError, AttributeError) as e:
            logger.debug(f"Failed to extract JSON from markdown: {e}")
            return None
    
    @staticmethod
    def extract_json_pattern(content: str) -> Optional[Dict[str, Any]]:
        """从文本中提取JSON模式内容"""
        try:
            # 查找类似JSON的内容
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_content = json_match.group(0)
                return json.loads(json_content)
            return None
        except (json.JSONDecodeError, AttributeError) as e:
            logger.debug(f"Failed to extract JSON pattern: {e}")
            return None
    
    @staticmethod
    def parse_structured_content(content: str) -> Dict[str, Any]:
        """解析结构化内容，尝试多种方法"""
        # 1. 尝试直接解析
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            pass
        
        # 2. 尝试从markdown提取
        markdown_result = JSONExtractor.extract_from_markdown(content)
        if markdown_result:
            return markdown_result
        
        # 3. 尝试JSON模式提取
        pattern_result = JSONExtractor.extract_json_pattern(content)
        if pattern_result:
            return pattern_result
        
        # 4. 失败时返回包装的响应
        return {"response": content}


class ResponseValidator:
    """响应验证工具类"""
    
    @staticmethod
    def ensure_json_serializable(data: Any) -> Any:
        """确保数据是JSON可序列化的"""
        if isinstance(data, dict):
            return {key: ResponseValidator.ensure_json_serializable(value) 
                   for key, value in data.items()}
        elif isinstance(data, list):
            return [ResponseValidator.ensure_json_serializable(item) for item in data]
        elif isinstance(data, (str, int, float, bool, type(None))):
            return data
        else:
            # 对于不可序列化的对象，转换为字符串
            return str(data)
    
    @staticmethod
    def validate_structured_response(response: Dict[str, Any]) -> bool:
        """验证结构化响应的有效性"""
        required_fields = ['success', 'data']
        return all(field in response for field in required_fields)


class ConfigHelper:
    """配置助手工具类"""
    
    @staticmethod
    def get_model_from_config() -> str:
        """从配置文件中获取实际使用的模型名称"""
        try:
            from core.config_manager import ConfigManager
            config_manager = ConfigManager()
            llm_config = config_manager.get_llm_config()
            
            # 获取默认提供商
            default_provider = llm_config.get('default_provider', 'gemini')
            
            # 获取提供商配置
            provider_config = llm_config.get('llm_providers', {}).get(default_provider, {})
            
            # 返回实际模型名称
            return provider_config.get('model', 'gemini-2.5-flash')
        except Exception as e:
            logger.error(f"Failed to get model from config: {e}")
            return 'gemini-2.5-flash'  # 回退到默认值