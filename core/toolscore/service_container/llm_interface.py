"""
LLM友好接口
为LLM提供智能的服务发现、推荐和调用接口
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from datetime import datetime

from .models import ServiceStatus

if TYPE_CHECKING:
    from .mcp_service_container import MCPServiceContainer

logger = logging.getLogger(__name__)


class LLMServiceInterface:
    """LLM服务接口"""
    
    def __init__(self, container: 'MCPServiceContainer'):
        self.container = container
        
        # 任务关键词到服务能力的映射
        self.task_capability_mapping = {
            "搜索": ["search", "find", "query"],
            "浏览器": ["browser", "web", "automation"],
            "代码执行": ["execute", "run", "sandbox"],
            "文件操作": ["file", "filesystem", "read", "write"],
            "数据分析": ["analysis", "data", "statistics"],
            "图像处理": ["image", "vision", "ocr"],
            "自然语言": ["nlp", "text", "language"],
            "数据库": ["database", "sql", "query"],
            "网络请求": ["http", "api", "request"],
            "邮件": ["email", "mail", "smtp"]
        }
    
    def get_service_catalog_for_llm(self) -> Dict[str, Any]:
        """
        为LLM提供服务目录
        返回格式化的、易于LLM理解的服务清单
        """
        available_services = []
        
        for service_id, config in self.container.service_catalog.items():
            # 只包含运行中且健康的服务
            if config.status == ServiceStatus.RUNNING and config.health.is_healthy:
                service_info = {
                    "service_id": service_id,
                    "name": config.name,
                    "description": config.description,
                    "type": "内置服务" if config.service_type.value == "builtin" else "外部服务",
                    "capabilities": [
                        {
                            "name": cap.name,
                            "description": cap.description,
                            "usage": self._generate_usage_example(cap),
                            "parameters": {
                                "required": cap.required_params,
                                "optional": cap.optional_params
                            }
                        }
                        for cap in config.capabilities
                    ],
                    "tags": config.tags,
                    "performance": {
                        "response_time": f"{config.health.response_time_ms}ms" if config.health.response_time_ms else "未知",
                        "reliability": self._calculate_reliability_score(config)
                    }
                }
                available_services.append(service_info)
        
        # 生成服务统计
        total_capabilities = sum(len(service["capabilities"]) for service in available_services)
        service_types = {}
        for service in available_services:
            for cap in service["capabilities"]:
                for tag in service["tags"]:
                    service_types[tag] = service_types.get(tag, 0) + 1
        
        return {
            "summary": {
                "total_services": len(available_services),
                "total_capabilities": total_capabilities,
                "service_categories": list(service_types.keys()),
                "last_updated": datetime.now().isoformat()
            },
            "services": available_services,
            "usage_guide": {
                "how_to_use": "要使用服务，请指定service_id和capability_name，并提供必要参数",
                "example": {
                    "service_id": "search_tool",
                    "capability": "search_files",
                    "parameters": {"query": "function main", "path": "./src"}
                }
            }
        }
    
    def recommend_services_for_task(self, task_description: str) -> List[Dict[str, Any]]:
        """
        基于任务描述推荐合适的服务
        智能分析任务需求并匹配最合适的服务能力
        """
        task_lower = task_description.lower()
        recommendations = []
        
        for service_id, config in self.container.service_catalog.items():
            if config.status != ServiceStatus.RUNNING or not config.health.is_healthy:
                continue
            
            service_score = 0
            matching_capabilities = []
            
            # 分析每个服务能力与任务的匹配度
            for capability in config.capabilities:
                capability_score = self._calculate_capability_match_score(capability, task_lower)
                
                if capability_score > 0.3:  # 匹配度阈值
                    matching_capabilities.append({
                        "name": capability.name,
                        "description": capability.description,
                        "match_score": capability_score,
                        "usage_suggestion": self._generate_task_specific_usage(capability, task_description)
                    })
                    service_score += capability_score
            
            # 如果服务有匹配的能力，添加到推荐列表
            if matching_capabilities:
                recommendations.append({
                    "service_id": service_id,
                    "service_name": config.name,
                    "match_score": service_score / len(config.capabilities),  # 标准化分数
                    "match_reason": self._generate_match_reason(config, task_lower),
                    "recommended_capabilities": sorted(matching_capabilities, key=lambda x: x["match_score"], reverse=True),
                    "service_type": config.service_type.value,
                    "performance": {
                        "response_time": f"{config.health.response_time_ms}ms" if config.health.response_time_ms else "未知",
                        "reliability": self._calculate_reliability_score(config)
                    }
                })
        
        # 按匹配分数排序
        recommendations.sort(key=lambda x: x["match_score"], reverse=True)
        
        return recommendations[:5]  # 返回前5个推荐
    
    async def call_service_capability(self, service_id: str, capability_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        统一的服务能力调用接口
        """
        try:
            # 检查服务是否存在
            config = self.container.service_catalog.get(service_id)
            if not config:
                return {
                    "success": False,
                    "error": f"服务不存在: {service_id}",
                    "error_type": "SERVICE_NOT_FOUND"
                }
            
            # 检查服务状态
            if config.status != ServiceStatus.RUNNING:
                return {
                    "success": False,
                    "error": f"服务未运行: {config.name}",
                    "error_type": "SERVICE_NOT_RUNNING"
                }
            
            # 检查能力是否存在
            capability = None
            for cap in config.capabilities:
                if cap.name == capability_name:
                    capability = cap
                    break
            
            if not capability:
                return {
                    "success": False,
                    "error": f"服务能力不存在: {capability_name}",
                    "error_type": "CAPABILITY_NOT_FOUND",
                    "available_capabilities": [cap.name for cap in config.capabilities]
                }
            
            # 验证参数
            validation_result = self._validate_parameters(capability, parameters)
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "error": validation_result["error"],
                    "error_type": "INVALID_PARAMETERS"
                }
            
            # 这里需要集成实际的服务调用逻辑
            # 暂时返回模拟结果
            result = await self._execute_service_call(service_id, capability_name, parameters)
            
            return {
                "success": True,
                "result": result,
                "service_info": {
                    "service_id": service_id,
                    "service_name": config.name,
                    "capability_name": capability_name
                },
                "execution_time": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ 调用服务能力失败: {e}")
            return {
                "success": False,
                "error": f"调用异常: {str(e)}",
                "error_type": "EXECUTION_ERROR"
            }
    
    def get_service_capabilities_summary(self) -> Dict[str, Any]:
        """获取服务能力汇总"""
        capabilities_by_category = {}
        all_capabilities = []
        
        for config in self.container.service_catalog.values():
            if config.status == ServiceStatus.RUNNING and config.health.is_healthy:
                for capability in config.capabilities:
                    cap_info = {
                        "service_id": config.service_id,
                        "service_name": config.name,
                        "capability_name": capability.name,
                        "description": capability.description,
                        "tags": config.tags
                    }
                    all_capabilities.append(cap_info)
                    
                    # 按标签分类
                    for tag in config.tags:
                        if tag not in capabilities_by_category:
                            capabilities_by_category[tag] = []
                        capabilities_by_category[tag].append(cap_info)
        
        return {
            "total_capabilities": len(all_capabilities),
            "categories": capabilities_by_category,
            "all_capabilities": all_capabilities
        }
    
    def _calculate_capability_match_score(self, capability, task_lower: str) -> float:
        """计算能力与任务的匹配分数"""
        score = 0.0
        
        # 检查能力名称匹配
        if capability.name.lower() in task_lower:
            score += 0.8
        
        # 检查描述匹配
        description_words = capability.description.lower().split()
        task_words = task_lower.split()
        
        common_words = set(description_words) & set(task_words)
        if common_words:
            score += len(common_words) / len(task_words) * 0.5
        
        # 检查关键词匹配
        for task_type, keywords in self.task_capability_mapping.items():
            if task_type in task_lower:
                for keyword in keywords:
                    if keyword in capability.name.lower() or keyword in capability.description.lower():
                        score += 0.3
                        break
        
        return min(score, 1.0)  # 限制最大分数为1.0
    
    def _generate_match_reason(self, config, task_lower: str) -> str:
        """生成匹配原因说明"""
        reasons = []
        
        # 检查服务名称匹配
        if config.name.lower() in task_lower:
            reasons.append(f"服务名称匹配: {config.name}")
        
        # 检查标签匹配
        matching_tags = [tag for tag in config.tags if tag.lower() in task_lower]
        if matching_tags:
            reasons.append(f"功能标签匹配: {', '.join(matching_tags)}")
        
        # 检查描述匹配
        if any(word in config.description.lower() for word in task_lower.split()):
            reasons.append("服务描述与任务相关")
        
        return "; ".join(reasons) if reasons else "基于服务能力推荐"
    
    def _generate_usage_example(self, capability) -> str:
        """生成使用示例"""
        if capability.required_params:
            params = ", ".join(f"{param}=<value>" for param in capability.required_params)
            return f"{capability.name}({params})"
        else:
            return f"{capability.name}()"
    
    def _generate_task_specific_usage(self, capability, task_description: str) -> str:
        """生成针对特定任务的使用建议"""
        base_usage = self._generate_usage_example(capability)
        
        # 根据任务描述生成更具体的建议
        if "搜索" in task_description and "search" in capability.name:
            return f"使用 {base_usage} 搜索相关内容"
        elif "浏览器" in task_description and "browser" in capability.name:
            return f"使用 {base_usage} 进行浏览器自动化"
        elif "执行" in task_description and "execute" in capability.name:
            return f"使用 {base_usage} 安全执行代码"
        else:
            return f"建议使用 {base_usage}"
    
    def _calculate_reliability_score(self, config) -> str:
        """计算可靠性分数"""
        if config.health.check_count == 0:
            return "未知"
        
        # 基于连续失败次数计算可靠性
        failure_rate = config.health.consecutive_failures / max(config.health.check_count, 1)
        
        if failure_rate == 0:
            return "优秀"
        elif failure_rate < 0.1:
            return "良好" 
        elif failure_rate < 0.3:
            return "一般"
        else:
            return "较差"
    
    def _validate_parameters(self, capability, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """验证参数"""
        # 检查必需参数
        missing_params = []
        for required_param in capability.required_params:
            if required_param not in parameters:
                missing_params.append(required_param)
        
        if missing_params:
            return {
                "valid": False,
                "error": f"缺少必需参数: {', '.join(missing_params)}"
            }
        
        # 检查多余参数
        all_valid_params = set(capability.required_params + capability.optional_params)
        extra_params = set(parameters.keys()) - all_valid_params
        
        if extra_params:
            return {
                "valid": False,
                "error": f"未知参数: {', '.join(extra_params)}"
            }
        
        return {"valid": True}
    
    async def _execute_service_call(self, service_id: str, capability_name: str, parameters: Dict[str, Any]) -> Any:
        """执行实际的服务调用"""
        # 这里需要集成具体的服务调用逻辑
        # 可以通过WebSocket、HTTP或直接函数调用
        
        # 暂时返回模拟结果
        return {
            "status": "执行成功",
            "data": f"模拟执行 {service_id}.{capability_name}",
            "parameters_used": parameters
        }