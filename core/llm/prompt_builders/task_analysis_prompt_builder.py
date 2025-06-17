import logging
from typing import Dict, Any, List
from core.llm.prompt_builders.interfaces import IPromptBuilder

logger = logging.getLogger(__name__)

class TaskAnalysisPromptBuilder(IPromptBuilder):
    """构建任务需求分析提示词"""
    def build_prompt(self, task_description: str) -> List[Dict[str, Any]]:
        """构建任务需求分析提示词"""
        prompt_content = f"""你是一个专业的任务分析助手。请仔细分析以下任务描述，总结完成这个任务需要什么样的功能和能力。

任务描述: {task_description}

请从以下维度分析这个任务：

1. **任务类型分类** (task_type):
   - reasoning: 需要复杂推理、多工具协同、分析对比
   - web: 主要涉及网页操作、信息搜索、网站导航  
   - code: 主要是编程、算法、计算、数据处理
   - image: 图像生成、图像处理、视觉相关
   - file: 文件操作、文档处理、格式转换
   - data: 数据分析、统计、可视化
   - communication: 通信、发送消息、API调用

2. **核心能力需求** (required_capabilities):
   分析任务需要哪些具体的技术能力，例如：
   - image_generation (图像生成)
   - web_scraping (网页抓取)
   - data_analysis (数据分析)
   - file_processing (文件处理)
   - code_execution (代码执行)
   - search (搜索功能)
   - browser_automation (浏览器自动化)
   - database_access (数据库访问)
   - api_calls (API调用)
   - text_processing (文本处理)

3. **具体工具类型** (tools_needed):
   基于能力需求，推测可能需要的工具类型，例如：
   - 图像生成工具 (如DALL-E, Stable Diffusion相关)
   - 浏览器操作工具 (如Selenium, Playwright相关)
   - 数据分析工具 (如pandas, numpy相关)
   - 文件处理工具 (如PDF, Excel处理相关)
   - API调用工具 (如HTTP客户端相关)

4. **关键特征识别** (key_features):
   识别任务描述中的关键特征，帮助匹配工具

请严格按照以下JSON格式返回分析结果，不要包含任何其他文字：

{{
  "task_type": "...",
  "required_capabilities": ["capability1", "capability2", "..."],
  "tools_needed": ["tool_type1", "tool_type2", "..."],
  "key_features": ["feature1", "feature2", "..."],
  "reasoning": "详细的分析推理过程，说明为什么需要这些能力和工具",
  "confidence": 0.9
}}

要求：
- 分析要准确且具体
- 不要猜测不存在的需求
- 重点关注任务的核心功能需求
- 确保JSON格式正确"""
        
        return [{"role": "user", "content": prompt_content}]