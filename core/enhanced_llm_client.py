"""
增强LLM客户端 - 收集详细的令牌使用和成本信息
为轨迹记录系统提供更丰富的LLM交互元数据
"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from core.llm_client import LLMClient
from core.interfaces import LLMInteraction

logger = logging.getLogger(__name__)

@dataclass
class LLMResponse:
    """增强的LLM响应，包含详细元数据"""
    content: str
    provider: str
    model: str
    token_usage: Dict[str, Any]
    cost_info: Dict[str, Any]
    response_time: float
    metadata: Dict[str, Any]

class EnhancedLLMClient:
    """增强LLM客户端包装器"""
    
    def __init__(self, base_client: LLMClient):
        self.base_client = base_client
        self.interaction_history: List[LLMInteraction] = []
        
        # 成本计算配置（示例值，实际应从配置文件读取）
        self.cost_config = {
            'gemini': {
                'input_cost_per_1k': 0.00025,
                'output_cost_per_1k': 0.0005
            },
            'openai': {
                'gpt-4': {
                    'input_cost_per_1k': 0.03,
                    'output_cost_per_1k': 0.06
                },
                'gpt-3.5-turbo': {
                    'input_cost_per_1k': 0.0015,
                    'output_cost_per_1k': 0.002
                }
            },
            'deepseek': {
                'input_cost_per_1k': 0.00014,
                'output_cost_per_1k': 0.00028
            }
        }
    
    def estimate_token_count(self, text: str) -> int:
        """估算令牌数量（简化实现）"""
        # 简化的令牌估算：英文约4字符/令牌，中文约1.5字符/令牌
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        
        estimated_tokens = int(chinese_chars / 1.5 + other_chars / 4)
        return max(estimated_tokens, 1)  # 至少1个令牌
    
    def calculate_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> Dict[str, Any]:
        """计算API调用成本"""
        try:
            cost_config = self.cost_config.get(provider.lower(), {})
            
            if provider.lower() == 'openai':
                model_config = cost_config.get(model, cost_config.get('gpt-4', {}))
            else:
                model_config = cost_config
            
            input_cost_per_1k = model_config.get('input_cost_per_1k', 0)
            output_cost_per_1k = model_config.get('output_cost_per_1k', 0)
            
            input_cost = (input_tokens / 1000) * input_cost_per_1k
            output_cost = (output_tokens / 1000) * output_cost_per_1k
            total_cost = input_cost + output_cost
            
            return {
                'input_cost': round(input_cost, 6),
                'output_cost': round(output_cost, 6),
                'total_cost': round(total_cost, 6),
                'currency': 'USD',
                'model': model,
                'rate_type': 'estimated'
            }
        except Exception as e:
            logger.warning(f"成本计算失败: {e}")
            return {'error': str(e)}
    
    async def enhanced_call_api(self, messages: List[Dict[str, Any]], context: str = "unknown") -> LLMResponse:
        """增强的API调用，收集详细元数据"""
        start_time = time.time()
        
        # 估算输入令牌数
        input_text = " ".join([msg.get('content', '') for msg in messages])
        estimated_input_tokens = self.estimate_token_count(input_text)
        
        # 获取提供商和模型信息
        provider = self.base_client.provider.value if hasattr(self.base_client.provider, 'value') else str(self.base_client.provider)
        model = getattr(self.base_client.provider_instance, 'get_default_model', lambda: 'unknown')()
        
        try:
            # 调用基础客户端
            response_content = await self.base_client._call_api(messages)
            
            response_time = time.time() - start_time
            
            # 估算输出令牌数
            estimated_output_tokens = self.estimate_token_count(response_content)
            
            # 计算成本
            cost_info = self.calculate_cost(provider, model, estimated_input_tokens, estimated_output_tokens)
            
            # 构建详细的令牌使用信息
            token_usage = {
                'prompt_tokens': estimated_input_tokens,
                'completion_tokens': estimated_output_tokens,
                'total_tokens': estimated_input_tokens + estimated_output_tokens,
                'estimation_method': 'character_based'
            }
            
            # 创建LLM交互记录
            interaction = LLMInteraction(
                provider=provider,
                model=model,
                context=context,
                prompt=input_text[:1000] + "..." if len(input_text) > 1000 else input_text,
                prompt_length=len(input_text),
                response=response_content[:1000] + "..." if len(response_content) > 1000 else response_content,
                response_length=len(response_content),
                response_time=response_time,
                token_usage=token_usage,
                cost_info=cost_info,
                success=True
            )
            
            self.interaction_history.append(interaction)
            
            return LLMResponse(
                content=response_content,
                provider=provider,
                model=model,
                token_usage=token_usage,
                cost_info=cost_info,
                response_time=response_time,
                metadata={
                    'context': context,
                    'interaction_id': interaction.interaction_id,
                    'timestamp': start_time
                }
            )
            
        except Exception as e:
            response_time = time.time() - start_time
            
            # 记录失败的交互
            interaction = LLMInteraction(
                provider=provider,
                model=model,
                context=context,
                prompt=input_text[:1000] + "..." if len(input_text) > 1000 else input_text,
                prompt_length=len(input_text),
                response_time=response_time,
                success=False,
                error_message=str(e)
            )
            
            self.interaction_history.append(interaction)
            
            raise e
    
    def get_accumulated_metrics(self) -> Dict[str, Any]:
        """获取累积的LLM使用指标"""
        total_interactions = len(self.interaction_history)
        total_cost = sum(interaction.cost_info.get('total_cost', 0) for interaction in self.interaction_history)
        total_tokens = sum(interaction.token_usage.get('total_tokens', 0) for interaction in self.interaction_history)
        total_response_time = sum(interaction.response_time for interaction in self.interaction_history)
        
        successful_interactions = sum(1 for interaction in self.interaction_history if interaction.success)
        
        return {
            'total_interactions': total_interactions,
            'successful_interactions': successful_interactions,
            'success_rate': successful_interactions / max(total_interactions, 1),
            'total_cost': round(total_cost, 6),
            'total_tokens': total_tokens,
            'total_response_time': round(total_response_time, 3),
            'average_response_time': round(total_response_time / max(total_interactions, 1), 3)
        }
    
    def clear_history(self):
        """清除交互历史"""
        self.interaction_history.clear()
    
    # 代理所有其他方法到基础客户端
    def __getattr__(self, name):
        return getattr(self.base_client, name)