"""
LLM请求预校验中间件
在LLM调用前进行结构化校验，避免无效请求消耗资源
"""

import json
import logging
from typing import Dict, Any, Optional, Tuple
from core.toolscore.structured_tools import tool_registry, LLMRequest, ToolValidationError

logger = logging.getLogger(__name__)


class LLMValidationMiddleware:
    """LLM请求预校验中间件"""
    
    def __init__(self):
        self.validation_stats = {
            "total_requests": 0,
            "valid_requests": 0,
            "invalid_requests": 0,
            "auto_corrected": 0,
            "validation_errors": []
        }
    
    def validate_before_llm_call(self, request_data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        在LLM调用前进行预校验
        
        Returns:
            Tuple[bool, Dict[str, Any], Optional[str]]: 
            (是否有效, 处理后的请求数据, 错误信息)
        """
        self.validation_stats["total_requests"] += 1
        
        try:
            # 1. 基础格式检查
            if not self._check_basic_format(request_data):
                error_msg = "请求格式不完整，缺少必需字段"
                self._record_error(error_msg, request_data)
                return False, request_data, error_msg
            
            # 2. 使用结构化工具注册表进行预校验
            validated_request = tool_registry.validate_request(LLMRequest(**request_data))
            
            self.validation_stats["valid_requests"] += 1
            logger.debug(f"✅ 预校验通过: {request_data.get('tool_id')}.{request_data.get('action')}")
            
            return True, validated_request["validated_request"].dict(), None
            
        except ToolValidationError as e:
            # 3. 尝试自动纠正
            try:
                corrected_request = tool_registry.auto_correct_request(request_data)
                self.validation_stats["auto_corrected"] += 1
                logger.info(f"🔧 自动纠正成功: {request_data.get('action')} -> {corrected_request.get('action')}")
                
                return True, corrected_request, None
                
            except ToolValidationError as correction_error:
                # 如果纠正也失败了，说明确实无法修复
                error_msg = f"校验失败且无法自动纠正: {str(e)}"
                self._record_error(error_msg, request_data, str(e))
                return False, request_data, error_msg
            except Exception as correction_error:
                # 其他意外错误
                error_msg = f"自动纠正过程出错: {str(correction_error)}"
                self._record_error(error_msg, request_data, str(e))
                return False, request_data, error_msg
        
        except Exception as e:
            error_msg = f"预校验过程发生错误: {str(e)}"
            self._record_error(error_msg, request_data, str(e))
            return False, request_data, error_msg
    
    def _check_basic_format(self, request_data: Dict[str, Any]) -> bool:
        """检查基础请求格式"""
        required_fields = ["thinking", "action", "tool_id"]
        return all(field in request_data for field in required_fields)
    
    def _record_error(self, error_msg: str, request_data: Dict[str, Any], original_error: str = None):
        """记录校验错误"""
        self.validation_stats["invalid_requests"] += 1
        
        error_record = {
            "error_message": error_msg,
            "original_error": original_error,
            "request_data": request_data,
            "tool_id": request_data.get("tool_id"),
            "action": request_data.get("action")
        }
        
        self.validation_stats["validation_errors"].append(error_record)
        logger.warning(f"❌ 预校验失败: {error_msg}")
    
    def get_validation_stats(self) -> Dict[str, Any]:
        """获取校验统计信息"""
        total = self.validation_stats["total_requests"]
        if total == 0:
            return self.validation_stats
        
        return {
            **self.validation_stats,
            "success_rate": self.validation_stats["valid_requests"] / total,
            "auto_correction_rate": self.validation_stats["auto_corrected"] / total,
            "failure_rate": self.validation_stats["invalid_requests"] / total
        }
    
    def reset_stats(self):
        """重置统计信息"""
        self.validation_stats = {
            "total_requests": 0,
            "valid_requests": 0,
            "invalid_requests": 0,
            "auto_corrected": 0,
            "validation_errors": []
        }


class ResponseValidationResult:
    """响应校验结果"""
    def __init__(self, is_valid: bool, data: Dict[str, Any], error: str = None, corrected: bool = False):
        self.is_valid = is_valid
        self.data = data
        self.error = error
        self.corrected = corrected


def validate_llm_response(response_text: str) -> ResponseValidationResult:
    """
    校验LLM响应并尝试自动纠正
    集成到现有的response parser中
    """
    try:
        # 这里可以集成到现有的ReasoningResponseParser中
        # 作为额外的预校验步骤
        
        # 简单的JSON格式检查
        try:
            if response_text.strip().startswith('{'):
                data = json.loads(response_text)
            else:
                # 提取JSON部分
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(0))
                else:
                    return ResponseValidationResult(
                        False, {}, "无法从响应中提取JSON格式数据"
                    )
        except json.JSONDecodeError as e:
            return ResponseValidationResult(
                False, {}, f"JSON解析失败: {str(e)}"
            )
        
        # 使用中间件进行校验
        middleware = LLMValidationMiddleware()
        is_valid, validated_data, error = middleware.validate_before_llm_call(data)
        
        return ResponseValidationResult(
            is_valid, validated_data, error, 
            corrected=(data != validated_data)
        )
        
    except Exception as e:
        return ResponseValidationResult(
            False, {}, f"响应校验过程出错: {str(e)}"
        )


# 全局校验中间件实例
validation_middleware = LLMValidationMiddleware()


def prevalidate_tool_request(func):
    """
    装饰器：为工具调用添加预校验
    
    使用示例:
    @prevalidate_tool_request
    def call_tool(self, request_data):
        # 如果到达这里，说明已经通过预校验
        pass
    """
    def wrapper(*args, **kwargs):
        # 假设第一个参数是request_data
        if args and isinstance(args[0], dict):
            request_data = args[0]
            is_valid, validated_data, error = validation_middleware.validate_before_llm_call(request_data)
            
            if not is_valid:
                raise ToolValidationError(f"预校验失败: {error}")
            
            # 用校验后的数据替换原始数据
            args = (validated_data,) + args[1:]
        
        return func(*args, **kwargs)
    
    return wrapper