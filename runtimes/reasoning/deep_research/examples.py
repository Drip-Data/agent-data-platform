"""
Deep Research Module Examples
深度研究模块使用示例
"""

import asyncio
import logging
from typing import Dict, Any
from .graph import create_research_graph, quick_research
from .config import ConfigTemplates
from ..tools.deep_research_tool import deep_research_tool

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def example_basic_research():
    """基础研究示例"""
    print("=== 基础深度研究示例 ===")
    
    try:
        result = await quick_research(
            "什么是大型语言模型的最新发展趋势？"
        )
        
        print(f"✅ 研究完成")
        print(f"📊 使用了 {len(result.get('search_query', []))} 个查询")
        print(f"📚 收集了 {len(result.get('sources_gathered', []))} 个信息源")
        print(f"🔄 执行了 {result.get('research_loop_count', 0)} 个研究循环")
        print(f"\n📝 最终答案:\n{result.get('final_answer', '未生成答案')[:500]}...")
        
        return result
        
    except Exception as e:
        print(f"❌ 研究失败: {str(e)}")
        return None


async def example_custom_config():
    """自定义配置示例"""
    print("\n=== 自定义配置研究示例 ===")
    
    # 使用高质量配置
    config = {
        "initial_search_query_count": 2,
        "max_research_loops": 2,
        "reasoning_model": "gemini-2.0-flash-exp"
    }
    
    try:
        result = await quick_research(
            "人工智能在医疗领域的应用现状如何？",
            config
        )
        
        print(f"✅ 高质量研究完成")
        print(f"🎯 配置: {config}")
        print(f"📊 研究结果长度: {len(result.get('final_answer', ''))}")
        
        return result
        
    except Exception as e:
        print(f"❌ 研究失败: {str(e)}")
        return None


async def example_tool_interface():
    """工具接口示例"""
    print("\n=== 工具接口使用示例 ===")
    
    try:
        result = await deep_research_tool.execute(
            query="量子计算的商业化前景如何？",
            config={
                "initial_search_query_count": 3,
                "max_research_loops": 2
            }
        )
        
        if result.get("success"):
            print(f"✅ 工具调用成功")
            print(f"📈 元数据: {result.get('metadata', {})}")
            print(f"🔗 信息源数量: {len(result.get('sources_gathered', []))}")
        else:
            print(f"❌ 工具调用失败: {result.get('error')}")
        
        return result
        
    except Exception as e:
        print(f"❌ 工具调用异常: {str(e)}")
        return None


async def example_multiple_topics():
    """多主题研究示例"""
    print("\n=== 多主题并行研究示例 ===")
    
    topics = [
        "区块链技术的最新发展",
        "可再生能源的投资机会",
        "元宇宙的技术挑战"
    ]
    
    # 使用快速配置进行并行研究
    config = ConfigTemplates.fast().to_dict()
    
    tasks = [
        quick_research(topic, config)
        for topic in topics
    ]
    
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        print(f"✅ 完成 {len(topics)} 个主题的研究")
        
        for i, (topic, result) in enumerate(zip(topics, results)):
            if isinstance(result, Exception):
                print(f"❌ 主题 {i+1} 失败: {str(result)}")
            else:
                answer_length = len(result.get('final_answer', ''))
                print(f"📊 主题 {i+1}: {topic} - 答案长度: {answer_length}")
        
        return results
        
    except Exception as e:
        print(f"❌ 并行研究失败: {str(e)}")
        return None


async def example_error_handling():
    """错误处理示例"""
    print("\n=== 错误处理示例 ===")
    
    # 测试无效配置
    invalid_config = {
        "initial_search_query_count": 100,  # 超出范围
        "max_research_loops": -1,  # 无效值
    }
    
    try:
        result = await deep_research_tool.execute(
            query="测试错误处理",
            config=invalid_config
        )
        
        if result.get("success"):
            print("😮 意外成功了")
        else:
            print(f"✅ 正确处理了错误: {result.get('error')}")
        
        return result
        
    except Exception as e:
        print(f"✅ 捕获到异常: {str(e)}")
        return None


def example_sync_usage():
    """同步使用示例"""
    print("\n=== 同步接口示例 ===")
    
    try:
        result = deep_research_tool.execute_sync(
            query="同步调用测试",
            config={"initial_search_query_count": 1, "max_research_loops": 1}
        )
        
        if result.get("success"):
            print("✅ 同步调用成功")
            print(f"📝 答案预览: {result.get('final_answer', '')[:100]}...")
        else:
            print(f"❌ 同步调用失败: {result.get('error')}")
        
        return result
        
    except Exception as e:
        print(f"❌ 同步调用异常: {str(e)}")
        return None


async def example_capabilities_demo():
    """功能演示示例"""
    print("\n=== 功能能力演示 ===")
    
    # 获取工具能力信息
    capabilities = deep_research_tool.get_capabilities()
    print(f"🔧 工具能力: {capabilities['name']}")
    print(f"📖 描述: {capabilities['description']}")
    print(f"⚙️ 参数: {list(capabilities['parameters'].keys())}")
    print(f"📤 输出: {list(capabilities['outputs'].keys())}")
    
    # 演示配置模板
    print(f"\n📋 可用配置模板:")
    templates = {
        "开发": ConfigTemplates.development(),
        "生产": ConfigTemplates.production(),
        "高质量": ConfigTemplates.high_quality(),
        "快速": ConfigTemplates.fast()
    }
    
    for name, template in templates.items():
        print(f"  {name}: 查询={template.initial_search_query_count}, 循环={template.max_research_loops}")
    
    return capabilities


async def run_all_examples():
    """运行所有示例"""
    print("🚀 开始运行深度研究模块示例")
    print("=" * 50)
    
    examples = [
        ("基础研究", example_basic_research),
        ("自定义配置", example_custom_config),
        ("工具接口", example_tool_interface),
        ("多主题研究", example_multiple_topics),
        ("错误处理", example_error_handling),
        ("功能演示", example_capabilities_demo),
    ]
    
    results = {}
    
    for name, example_func in examples:
        try:
            print(f"\n🔄 执行示例: {name}")
            result = await example_func()
            results[name] = result
            print(f"✅ 示例 '{name}' 完成")
        except Exception as e:
            print(f"❌ 示例 '{name}' 失败: {str(e)}")
            results[name] = None
    
    # 运行同步示例
    try:
        print(f"\n🔄 执行同步示例")
        sync_result = example_sync_usage()
        results["同步接口"] = sync_result
        print(f"✅ 同步示例完成")
    except Exception as e:
        print(f"❌ 同步示例失败: {str(e)}")
        results["同步接口"] = None
    
    print("\n" + "=" * 50)
    print("📊 示例执行总结:")
    
    success_count = sum(1 for result in results.values() if result is not None)
    total_count = len(results)
    
    print(f"✅ 成功: {success_count}/{total_count}")
    print(f"❌ 失败: {total_count - success_count}/{total_count}")
    
    for name, result in results.items():
        status = "✅" if result is not None else "❌"
        print(f"  {status} {name}")
    
    return results


if __name__ == "__main__":
    # 运行示例
    asyncio.run(run_all_examples())