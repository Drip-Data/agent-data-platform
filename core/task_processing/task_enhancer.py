import logging
import time
from typing import Dict, Any
from core.interfaces import TaskSpec
from core.toolscore.toolscore_client import ToolScoreClient

logger = logging.getLogger(__name__)

class TaskEnhancer:
    """
    任务增强器，负责调用 ToolScore 服务并根据推荐结果增强任务。
    """
    def __init__(self, toolscore_client: ToolScoreClient):
        self.toolscore_client = toolscore_client

    async def enhance_task_with_tools(self, task: TaskSpec) -> TaskSpec:
        """为任务增强工具选择"""
        # 如果已经有明确的工具指定，且不是auto，就保持不变
        if task.expected_tools and task.expected_tools != ["auto"]:
            logger.debug(f"任务 {task.task_id} 已有明确工具: {task.expected_tools}")
            return task
        
        # 调用智能工具推荐
        tool_recommendation = await self.toolscore_client.intelligent_recommend(task) # 调用 ToolScoreClient
        
        # 更新任务的工具配置
        task.expected_tools = tool_recommendation["recommended_tools"]
        
        # 添加推荐元数据
        if "tool_metadata" not in task.constraints:
            task.constraints["tool_metadata"] = {}
            
        task.constraints["tool_metadata"].update({
            "recommendation_confidence": tool_recommendation.get("confidence", 0.0),
            "recommended_at": time.time(),
            "recommendation_reason": tool_recommendation.get("reason", ""),
            "recommendation_strategy": tool_recommendation.get("strategy", "intelligent"),
            "original_tools": task.expected_tools if task.expected_tools != ["auto"] else []
        })
        
        logger.info(f"为任务 {task.task_id} 推荐工具: {task.expected_tools} (置信度: {tool_recommendation.get('confidence', 0.0)})")
        
        return task