#!/usr/bin/env python3
"""
智能工具发现系统演示
展示如何通过Agent自主推理进行场景识别和工具选择
完全去掉预定义规则，让AI自主分析决策
"""

import asyncio
import logging
import sys
import os
from typing import Dict, Any

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.toolscore.intelligent_discovery_service import IntelligentDiscoveryService
from core.toolscore.tool_registry import ToolRegistry, ToolkitRegistry
from core.llm_client import LLMClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockLLMClient:
    """模拟LLM客户端，用于演示"""
    
    def __init__(self):
        self.call_count = 0
    
    async def generate(self, prompt: str) -> str:
        """模拟LLM响应"""
        self.call_count += 1
        
        print(f"\n🤖 LLM调用 #{self.call_count}")
        print("=" * 80)
        print("📝 PROMPT:")
        print(prompt)
        print("\n" + "=" * 80)
        
        # 根据prompt类型返回不同的模拟响应
        if "任务分析专家" in prompt:
            return self._generate_analysis_response(prompt)
        elif "工具包选择专家" in prompt:
            return self._generate_toolkit_selection_response(prompt)
        elif "工具筛选专家" in prompt:
            return self._generate_tool_filtering_response(prompt)
        else:
            return "模拟LLM响应"
    
    def _generate_analysis_response(self, prompt: str) -> str:
        """生成分析响应"""
        if "分析这个网站的用户评论" in prompt:
            return """
CORE_INTENT:
用户希望从某个网站获取用户评论数据，并对这些评论进行分析，可能包括情感分析、内容归类、统计分析等，目的是了解用户对产品或服务的反馈情况。

TASK_CHARACTERISTICS:
这是一个复合型任务，包含数据获取和数据分析两个主要阶段。首先需要通过网页抓取技术获取评论数据，然后使用数据处理和分析工具对评论内容进行深度分析。任务复杂度中等，需要多步骤协作。

TECHNICAL_REQUIREMENTS:
需要网页交互能力（浏览器自动化、数据抓取）以及数据分析能力（文本处理、统计分析、可能的机器学习）。还可能需要数据清洗、格式转换、结果可视化等功能。

SCENARIO_CLASSIFICATION:
复合型网页数据挖掘与分析场景 - 结合了WEB_DATA_EXTRACTION和TEXT_ANALYTICS的特征

ANALYSIS_CONFIDENCE: 0.9

STRATEGIC_APPROACH:
建议采用分阶段执行策略：1）使用浏览器工具导航到目标网站并提取评论数据；2）使用Python工具进行数据清洗和预处理；3）应用文本分析技术进行情感分析和内容分类；4）生成分析报告和可视化结果。
"""
        elif "帮我写一个斐波那契算法" in prompt:
            return """
CORE_INTENT:
用户需要实现斐波那契数列的算法，这是一个经典的数学编程问题，可能用于学习、作业或实际项目中。

TASK_CHARACTERISTICS:
这是一个纯编程任务，相对简单，属于单步骤执行。需要编写代码实现算法逻辑，可能包括递归、迭代或动态规划等不同实现方式。

TECHNICAL_REQUIREMENTS:
主要需要代码编写和执行能力，具体是Python编程环境。需要算法实现、代码验证、可能的性能测试等功能。

SCENARIO_CLASSIFICATION:
纯编程实现场景 - CODE_IMPLEMENTATION类型

ANALYSIS_CONFIDENCE: 0.95

STRATEGIC_APPROACH:
使用代码执行工具直接编写和运行斐波那契算法，提供多种实现方式（递归、迭代、动态规划），并包含性能比较和测试用例。
"""
        else:
            return """
CORE_INTENT:
用户的具体需求需要进一步分析

TASK_CHARACTERISTICS:
任务特征待确定

TECHNICAL_REQUIREMENTS:
技术需求待评估

SCENARIO_CLASSIFICATION:
通用分析场景

ANALYSIS_CONFIDENCE: 0.7

STRATEGIC_APPROACH:
采用通用处理策略
"""
    
    def _generate_toolkit_selection_response(self, prompt: str) -> str:
        """生成工具包选择响应"""
        if "网页数据挖掘与分析" in prompt or "评论" in prompt:
            return """
SELECTION_ANALYSIS:
根据任务需求分析，这是一个需要网页数据抓取和后续分析的复合任务。WebAutomationToolkit提供了完整的浏览器自动化能力，能够导航网站、定位元素、提取数据。CodeExecutionToolkit提供Python执行环境，支持数据处理、文本分析、统计计算等。两个工具包的组合能够完美覆盖整个任务流程。

SELECTED_TOOLKITS:
WebAutomationToolkit, CodeExecutionToolkit

SELECTION_REASONING:
选择WebAutomationToolkit是因为需要自动化浏览网页并提取评论数据，这个工具包提供了browser相关的所有功能。选择CodeExecutionToolkit是因为获取数据后需要进行复杂的文本分析和统计处理，Python环境最适合这类任务。

COMBINATION_STRATEGY:
先使用WebAutomationToolkit进行数据获取，将提取的评论数据传递给CodeExecutionToolkit进行分析处理。两个工具包按顺序协作，形成完整的数据处理管道。

CONFIDENCE: 0.92

ALTERNATIVE_OPTIONS:
如果网站数据可以通过API获取，可以仅使用CodeExecutionToolkit进行HTTP请求和数据处理
"""
        elif "斐波那契" in prompt or "算法" in prompt:
            return """
SELECTION_ANALYSIS:
这是一个纯编程任务，主要需要代码编写和执行能力。CodeExecutionToolkit提供了完整的Python执行环境，能够编写、运行和测试算法代码。其他工具包对于这个任务来说是不必要的。

SELECTED_TOOLKITS:
CodeExecutionToolkit

SELECTION_REASONING:
斐波那契算法是纯数学编程问题，只需要编程语言和执行环境。CodeExecutionToolkit提供了Python解释器，能够完成算法实现、测试和性能分析的所有需求。

COMBINATION_STRATEGY:
单一工具包即可完成任务，不需要组合策略。

CONFIDENCE: 0.98

ALTERNATIVE_OPTIONS:
无需替代方案，CodeExecutionToolkit完全满足需求
"""
        else:
            return """
SELECTION_ANALYSIS:
基于通用分析，选择最常用的工具包组合

SELECTED_TOOLKITS:
CodeExecutionToolkit

SELECTION_REASONING:
选择通用的代码执行工具包

COMBINATION_STRATEGY:
单一工具包策略

CONFIDENCE: 0.8

ALTERNATIVE_OPTIONS:
根据具体需求可能需要其他工具包
"""
    
    def _generate_tool_filtering_response(self, prompt: str) -> str:
        """生成工具筛选响应"""
        if "WebAutomationToolkit" in prompt and "CodeExecutionToolkit" in prompt:
            return """
TOOL_ANALYSIS:
从WebAutomationToolkit中，browser_tool是核心工具，提供网页导航、元素定位、文本提取等功能，完全符合数据获取需求。从CodeExecutionToolkit中，python_tool提供代码执行环境，支持数据处理、文本分析、机器学习等，能够处理获取到的评论数据。

SELECTED_TOOLS:
browser_tool, python_tool

FILTERING_REASONING:
browser_tool是网页数据提取的必备工具，能够自动化浏览器操作，提取评论内容。python_tool提供了强大的数据分析能力，包括pandas处理、nltk文本分析、matplotlib可视化等，是处理文本数据的最佳选择。

EXECUTION_PLAN:
1. 使用browser_tool导航到目标网站
2. 定位评论区域并提取评论文本
3. 将数据传递给python_tool进行预处理
4. 使用Python进行情感分析和统计分析
5. 生成分析报告和可视化图表

PARAMETER_REQUIREMENTS:
browser_tool需要: 目标URL、CSS选择器（用于定位评论）
python_tool需要: 处理代码（数据分析脚本）

CONFIDENCE: 0.94

FALLBACK_OPTIONS:
如果网站有反爬措施，可以尝试使用http_client进行API调用
"""
        elif "CodeExecutionToolkit" in prompt and "斐波那契" in prompt:
            return """
TOOL_ANALYSIS:
python_tool提供了完整的Python执行环境，能够编写和运行斐波那契算法。支持多种实现方式，包括递归、迭代、动态规划等，还能进行性能测试和结果验证。

SELECTED_TOOLS:
python_tool

FILTERING_REASONING:
python_tool是实现算法的最佳选择，提供了完整的编程环境，支持函数定义、循环、递归等所有必要的编程结构。还能进行性能测试和结果可视化。

EXECUTION_PLAN:
1. 编写多种斐波那契实现（递归、迭代、动态规划）
2. 创建测试用例验证算法正确性
3. 进行性能比较分析
4. 输出结果和性能数据

PARAMETER_REQUIREMENTS:
python_tool需要: 算法实现代码、测试参数（如计算第n项）

CONFIDENCE: 0.97

FALLBACK_OPTIONS:
无需备选方案，python_tool完全满足需求
"""
        else:
            return """
TOOL_ANALYSIS:
基于通用分析进行工具筛选

SELECTED_TOOLS:
python_tool

FILTERING_REASONING:
选择通用的Python执行工具

EXECUTION_PLAN:
基于具体需求执行

PARAMETER_REQUIREMENTS:
待定

CONFIDENCE: 0.8

FALLBACK_OPTIONS:
待评估
"""


async def demo_intelligent_discovery():
    """演示智能发现系统"""
    print("🚀 智能工具发现系统演示")
    print("=" * 60)
    
    # 初始化组件
    tool_registry = ToolRegistry()
    toolkit_registry = ToolkitRegistry(tool_registry)
    mock_llm = MockLLMClient()
    
    # 创建智能发现服务
    discovery_service = IntelligentDiscoveryService(
        tool_registry, toolkit_registry, mock_llm
    )
    
    # 测试场景1：复合任务 - 网页数据分析
    print("\n🔍 测试场景1：网页数据分析任务")
    print("-" * 40)
    
    query1 = "帮我分析这个网站的用户评论数据，了解用户满意度情况"
    result1 = await discovery_service.complete_intelligent_discovery(query1)
    
    print("\n📊 发现结果:")
    print(f"查询分析: {result1['query_analysis']['scenario_analysis']}")
    print(f"选择的工具包: {result1['toolkit_selection']['selected_toolkits']}")
    print(f"筛选的工具: {result1['tool_filtering']['selected_tools']}")
    print(f"执行策略: {result1['tool_filtering']['execution_strategy']}")
    print(f"总体置信度: {result1['overall_confidence']:.2f}")
    
    # 测试场景2：纯编程任务
    print("\n\n🔍 测试场景2：算法编程任务")
    print("-" * 40)
    
    query2 = "帮我写一个斐波那契算法，要求效率高"
    result2 = await discovery_service.complete_intelligent_discovery(query2)
    
    print("\n📊 发现结果:")
    print(f"查询分析: {result2['query_analysis']['scenario_analysis']}")
    print(f"选择的工具包: {result2['toolkit_selection']['selected_toolkits']}")
    print(f"筛选的工具: {result2['tool_filtering']['selected_tools']}")
    print(f"执行策略: {result2['tool_filtering']['execution_strategy']}")
    print(f"总体置信度: {result2['overall_confidence']:.2f}")
    
    print(f"\n🎯 总共进行了 {mock_llm.call_count} 次LLM调用")
    print("\n✨ 演示完成！系统完全基于Agent自主推理，无预定义规则")


if __name__ == "__main__":
    asyncio.run(demo_intelligent_discovery()) 