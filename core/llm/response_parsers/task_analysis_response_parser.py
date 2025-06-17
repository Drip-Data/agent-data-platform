import json
import logging
from typing import Dict, Any, List

from core.llm.response_parsers.interfaces import IResponseParser

logger = logging.getLogger(__name__)

class TaskAnalysisResponseParser(IResponseParser):
    """
    用于解析LLM生成的任务需求分析响应的解析器。
    """

    def parse_response(self, response: str, **kwargs) -> Dict[str, Any]:
        """
        解析LLM的原始字符串响应，并将其转换为任务需求分析结果字典。
        
        Args:
            response (str): LLM的原始字符串响应。
            **kwargs: 额外的参数，目前未使用，但保留以符合接口。

        Returns:
            Dict[str, Any]: 包含任务需求分析结果的字典。
        """
        logger.info(f"🔍 解析LLM响应中的任务需求分析结果 (长度: {len(response)})")
        
        try:
            # 提取JSON内容（去除代码块标记）
            import re
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                json_content = json_match.group(1)
            else:
                # 如果没有代码块标记，尝试直接解析
                json_content = response.strip()
            
            # 尝试解析JSON
            parsed_response = json.loads(json_content)
            
            # 验证并提取关键字段，提供默认值以防缺失
            task_type = parsed_response.get("task_type", "unknown")
            required_capabilities = parsed_response.get("required_capabilities", [])
            tools_needed = parsed_response.get("tools_needed", [])
            key_features = parsed_response.get("key_features", [])
            reasoning = parsed_response.get("reasoning", "No reasoning provided.")
            confidence = parsed_response.get("confidence", 0.0)

            # 确保列表类型正确
            if not isinstance(required_capabilities, list):
                required_capabilities = []
            if not isinstance(tools_needed, list):
                tools_needed = []
            if not isinstance(key_features, list):
                key_features = []

            # 确保confidence在有效范围内
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                confidence = 0.0
                logger.warning(f"⚠️ 无效的confidence值: {parsed_response.get('confidence')}, 已重置为0.0")

            logger.info(f"✅ 成功解析任务需求分析结果: task_type={task_type}, confidence={confidence}")
            return {
                "task_type": task_type,
                "required_capabilities": required_capabilities,
                "tools_needed": tools_needed,
                "key_features": key_features,
                "reasoning": reasoning,
                "confidence": confidence
            }
        except json.JSONDecodeError as e:
            logger.warning(f"❌ JSON解析失败: {e}, 返回默认分析结果")
            return {
                "task_type": "unknown",
                "required_capabilities": [],
                "tools_needed": [],
                "key_features": [],
                "reasoning": f"JSON parsing error: {e}",
                "confidence": 0.0
            }
        except Exception as e:
            logger.error(f"❌ 解析任务需求分析响应过程中出错: {e}, 返回默认分析结果")
            return {
                "task_type": "unknown",
                "required_capabilities": [],
                "tools_needed": [],
                "key_features": [],
                "reasoning": f"Error during parsing: {e}",
                "confidence": 0.0
            }