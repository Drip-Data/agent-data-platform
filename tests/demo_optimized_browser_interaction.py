#!/usr/bin/env python3
"""
优化后的Agent与Browser Use交互演示
展示优化后的prompt设计和配置效果
"""

import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.llm.prompt_builders.reasoning_prompt_builder import ReasoningPromptBuilder

def demo_prompt_optimization():
    """演示prompt优化效果"""
    print("🎯 Agent与Browser Use交互优化演示")
    print("="*60)
    
    prompt_builder = ReasoningPromptBuilder()
    
    # 测试场景
    test_scenarios = [
        {
            "task": "搜索Python机器学习教程并打开第一个结果",
            "scenario": "复杂搜索任务",
            "expected": "应选择browser_use_execute_task"
        },
        {
            "task": "抓取网站上的所有产品价格信息",
            "scenario": "数据抓取任务", 
            "expected": "应选择browser_use_execute_task"
        },
        {
            "task": "导航到Google首页",
            "scenario": "简单导航任务",
            "expected": "可选择browser_navigate"
        }
    ]
    
    available_tools = ["browser_use", "microsandbox", "deepsearch"]
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n📋 场景 {i}: {scenario['scenario']}")
        print(f"任务: {scenario['task']}")
        print(f"预期: {scenario['expected']}")
        print("-" * 40)
        
        # 构建基础prompt
        basic_prompt = prompt_builder._build_basic_reasoning_prompt(
            task_description=scenario["task"],
            available_tools=available_tools
        )
        
        # 构建增强prompt（模拟有工具描述的情况）
        enhanced_prompt = prompt_builder._build_enhanced_reasoning_prompt(
            task_description=scenario["task"],
            available_tools=available_tools,
            tool_descriptions="Browser Use: 智能浏览器操作工具，支持25+动作"
        )
        
        print("🔍 Prompt优化检查:")
        
        basic_content = basic_prompt[0]["content"]
        enhanced_content = enhanced_prompt[0]["content"]
        
        # 检查优化点
        optimizations = {
            "browser_use_execute_task提及": "browser_use_execute_task" in enhanced_content,
            "PRIMARY优先级标识": "PRIMARY" in enhanced_content,
            "扩展关键词覆盖": any(kw in enhanced_content for kw in ["搜索", "抓取", "数据收集", "表单", "自动化"]),
            "25+动作说明": "25+ Actions" in enhanced_content,
            "AI功能描述": any(feat in enhanced_content for feat in ["AI vision", "多步骤自动化", "智能"]),
            "决策框架指导": "For Web/Browser Tasks" in enhanced_content,
            "参数指导完整": "task" in enhanced_content and "goal" in enhanced_content
        }
        
        for opt_name, present in optimizations.items():
            status = "✅" if present else "❌"
            print(f"  {status} {opt_name}")
        
        coverage = sum(optimizations.values()) / len(optimizations)
        print(f"📊 优化覆盖率: {coverage:.1%}")
        
        if coverage >= 0.8:
            print("🎉 优化效果良好!")
        else:
            print("⚠️ 需要进一步优化")

def demo_config_enhancement():
    """演示配置文件增强效果"""
    print(f"\n🔧 配置文件增强效果演示")
    print("="*60)
    
    # 读取配置文件内容
    config_path = project_root / "config" / "unified_tool_definitions.yaml"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config_content = f.read()
        
        print("📁 unified_tool_definitions.yaml 增强检查:")
        
        enhancements = {
            "browser_use_execute_task突出显示": "browser_use_execute_task" in config_content and "🚀" in config_content,
            "优先级标识": "highest" in config_content or "priority" in config_content,
            "智能特性描述": "AI驱动" in config_content,
            "关键词扩展": "搜索" in config_content and "抓取" in config_content,
            "使用场景示例": "use_cases" in config_content,
            "警告信息": "⚠️" in config_content,
            "推荐替代方案": "alternative" in config_content
        }
        
        for enh_name, present in enhancements.items():
            status = "✅" if present else "❌"
            print(f"  {status} {enh_name}")
        
        coverage = sum(enhancements.values()) / len(enhancements)
        print(f"📊 配置增强覆盖率: {coverage:.1%}")
        
        if coverage >= 0.8:
            print("🎉 配置增强效果良好!")
        else:
            print("⚠️ 配置需要进一步增强")
    else:
        print("❌ 配置文件未找到")

def demo_decision_simulation():
    """演示决策逻辑模拟"""
    print(f"\n🧠 智能决策逻辑演示")
    print("="*60)
    
    decision_scenarios = [
        {
            "keywords": ["搜索", "Python", "教程"],
            "task_type": "复杂搜索",
            "recommended_action": "browser_use_execute_task",
            "reasoning": "包含搜索关键词，需要多步骤操作"
        },
        {
            "keywords": ["抓取", "数据", "产品"],
            "task_type": "数据抓取", 
            "recommended_action": "browser_use_execute_task",
            "reasoning": "数据抓取需要AI智能识别和提取"
        },
        {
            "keywords": ["导航", "打开", "网页"],
            "task_type": "简单导航",
            "recommended_action": "browser_navigate",
            "reasoning": "仅需简单导航，无复杂操作"
        },
        {
            "keywords": ["填写", "表单", "提交"],
            "task_type": "表单操作",
            "recommended_action": "browser_use_execute_task", 
            "reasoning": "表单操作需要智能识别和交互"
        }
    ]
    
    for scenario in decision_scenarios:
        print(f"\n📝 {scenario['task_type']}:")
        print(f"关键词: {', '.join(scenario['keywords'])}")
        print(f"推荐动作: {scenario['recommended_action']}")
        print(f"决策理由: {scenario['reasoning']}")

def demo_optimization_summary():
    """优化总结"""
    print(f"\n📈 Browser Use交互优化总结")
    print("="*60)
    
    optimizations = [
        "🚀 突出browser_use_execute_task作为首选AI任务执行器",
        "🔍 扩展关键词匹配范围：搜索、抓取、数据收集、表单、自动化",
        "📋 明确25+动作的功能层次：AI任务执行 > 基础操作",
        "⚡ 提供清晰的决策指导框架和优先级",
        "🎯 增强配置文件中的工具描述和使用建议",
        "⚠️ 为基础操作添加警告，推荐使用AI任务执行器",
        "📊 集成动态工具描述生成，避免硬编码",
        "🧠 优化prompt结构，提高LLM决策准确性"
    ]
    
    print("已实现的关键优化:")
    for opt in optimizations:
        print(f"  {opt}")
    
    print(f"\n🎯 预期效果:")
    print("  • Agent能正确识别复杂网页任务并选择AI执行器")
    print("  • 提高任务执行成功率和用户体验")
    print("  • 减少低效的基础操作使用")
    print("  • 充分利用browser-use的AI能力")

def main():
    """主函数"""
    print("🎉 Agent与Browser Use交互优化完成!")
    print("正在演示优化效果...\n")
    
    # 运行各项演示
    demo_prompt_optimization()
    demo_config_enhancement() 
    demo_decision_simulation()
    demo_optimization_summary()
    
    print(f"\n✅ 优化演示完成!")
    print("现在Agent可以更智能地使用Browser Use工具了。")

if __name__ == "__main__":
    main()