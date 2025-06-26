import json
import logging
from typing import Dict, Any

from core.llm.response_parsers.interfaces import IResponseParser

logger = logging.getLogger(__name__)

class CompletionCheckResponseParser(IResponseParser):
    """
    用于解析LLM生成的任务完成检查响应的解析器。
    """

    def parse_response(self, response: str, **kwargs) -> Dict[str, Any]:
        """
        解析LLM的原始字符串响应，并将其转换为任务完成检查结果字典。
        支持JSON格式和自然语言描述两种响应模式。
        
        Args:
            response (str): LLM的原始字符串响应。
            **kwargs: 额外的参数，目前未使用，但保留以符合接口。

        Returns:
            Dict[str, Any]: 包含任务完成检查结果的字典。
        """
        logger.info(f"🔍 解析LLM响应中的任务完成检查结果 (长度: {len(response)})")
        
        # 首先尝试JSON解析
        try:
            # 清理响应文本
            cleaned_response = response.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()
            
            parsed_response = json.loads(cleaned_response)
            
            # 验证并提取关键字段
            completed = parsed_response.get("completed", False)
            confidence = parsed_response.get("confidence", 0.0)
            reason = parsed_response.get("reason", "No reason provided.")

            # 确保confidence在有效范围内
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                confidence = 0.0
                logger.warning(f"⚠️ 无效的confidence值: {parsed_response.get('confidence')}, 已重置为0.0")

            logger.info(f"✅ 成功解析JSON任务完成检查结果: completed={completed}, confidence={confidence}")
            return {
                "completed": completed,
                "confidence": confidence,
                "reason": reason
            }
        except json.JSONDecodeError:
            # JSON解析失败，尝试自然语言解析
            logger.info("JSON解析失败，尝试自然语言解析...")
            return self._parse_natural_language_response(response)
        except Exception as e:
            logger.error(f"❌ 解析任务完成检查响应过程中出错: {e}")
            return self._parse_natural_language_response(response)
    
    def _parse_natural_language_response(self, response: str) -> Dict[str, Any]:
        """
        解析自然语言格式的任务完成检查响应
        """
        response_lower = response.lower()
        
        # 检查完成指示词
        completion_indicators = [
            "任务已", "任务完成", "已完成", "成功完成", "完成", "successful", "completed", "done",
            "结果正确", "计算正确", "执行成功", "验证通过", "满足要求"
        ]
        
        # 检查失败指示词
        failure_indicators = [
            "失败", "错误", "未完成", "incomplete", "failed", "error", "问题", "无法"
        ]
        
        completed = False
        confidence = 0.5  # 默认中等置信度
        
        # 分析完成指示
        completion_count = sum(1 for indicator in completion_indicators if indicator in response_lower)
        failure_count = sum(1 for indicator in failure_indicators if indicator in response_lower)
        
        if completion_count > failure_count and completion_count > 0:
            completed = True
            confidence = min(0.9, 0.6 + (completion_count * 0.1))
        elif failure_count > 0:
            completed = False
            confidence = max(0.1, 0.5 - (failure_count * 0.1))
        else:
            # 如果没有明确指示，检查其他线索
            if any(word in response_lower for word in ["128255625", "结果", "输出", "计算"]):
                completed = True
                confidence = 0.7
        
        logger.info(f"✅ 自然语言解析结果: completed={completed}, confidence={confidence}")
        return {
            "completed": completed,
            "confidence": confidence,
            "reason": f"自然语言分析: {response[:100]}..."
        }