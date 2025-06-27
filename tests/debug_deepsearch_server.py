#!/usr/bin/env python3
"""
DeepSearch Server 快速调试测试
基于从日志中发现的问题进行针对性调试
"""

import asyncio
import sys
import json
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mcp_servers.deepsearch_server.main import DeepSearchMCPServer
from core.config_manager import ConfigManager

async def debug_deepsearch_server():
    """调试DeepSearch服务器的关键问题"""
    print("🐛 DeepSearch Server 调试分析")
    print("="*60)
    
    # 初始化
    config_manager = ConfigManager()
    server = DeepSearchMCPServer(config_manager)
    
    print("✅ 服务器初始化成功")
    
    # 问题1: JSON解析失败
    print("\n🔍 问题1: JSON解析失败")
    print("从日志看到: 'Failed to parse query generation response as JSON'")
    print("原因: LLM返回的是markdown格式的JSON，需要提取```json```中的内容")
    
    # 问题2: 参数映射
    print("\n🔍 问题2: 参数映射测试")
    try:
        # 测试query->question映射
        result = await server.handle_tool_action("research", {"query": "简单测试查询"})
        print(f"query映射测试: {'✅ 成功' if result.get('success') else '❌ 失败'}")
        
        # 测试task_description->question映射
        result = await server.handle_tool_action("research", {"task_description": "测试任务"})
        print(f"task_description映射测试: {'✅ 成功' if result.get('success') else '❌ 失败'}")
        
    except Exception as e:
        print(f"❌ 参数映射测试失败: {e}")
    
    # 问题3: 性能问题
    print("\n🔍 问题3: 性能分析")
    print("从日志看到单次研究耗时27.35秒，这导致了测试超时")
    print("建议: 为测试环境设置更短的超时时间或使用mock")
    
    # 问题4: 配置一致性
    print("\n🔍 问题4: 配置一致性检查")
    
    # 检查service.json
    service_json_path = project_root / "mcp_servers" / "deepsearch_server" / "service.json"
    if service_json_path.exists():
        with open(service_json_path, 'r') as f:
            service_config = json.load(f)
        
        print(f"service.json存在: ✅")
        print(f"服务ID: {service_config.get('service_id')}")
        print(f"端口: {service_config.get('port')}")
        print(f"能力数量: {len(service_config.get('capabilities', []))}")
    else:
        print("service.json不存在: ❌")
    
    # 检查unified配置
    unified_config_path = project_root / "config" / "unified_tool_definitions.yaml"
    if unified_config_path.exists():
        print(f"unified_tool_definitions.yaml存在: ✅")
    else:
        print("unified_tool_definitions.yaml不存在: ❌")
    
    # 问题5: 工具实现问题
    print("\n🔍 问题5: 工具实现分析")
    
    # 检查工具文件
    unified_tool_path = project_root / "mcp_servers" / "deepsearch_server" / "deepsearch_tool_unified.py"
    original_tool_path = project_root / "mcp_servers" / "deepsearch_server" / "deepsearch_tool.py"
    
    print(f"unified工具实现: {'✅ 存在' if unified_tool_path.exists() else '❌ 不存在'}")
    print(f"原始工具实现: {'✅ 存在' if original_tool_path.exists() else '❌ 不存在'}")
    
    if unified_tool_path.exists() and original_tool_path.exists():
        print("⚠️ 警告: 存在两个工具实现，可能导致混乱")
    
    # 问题6: 快速功能测试
    print("\n🔍 问题6: 快速功能测试")
    try:
        start_time = time.time()
        result = await server.handle_tool_action("quick_research", {"question": "快速测试"})
        duration = time.time() - start_time
        
        success = result.get("success", False)
        print(f"快速研究测试: {'✅ 成功' if success else '❌ 失败'}")
        print(f"耗时: {duration:.2f}秒")
        
        if success:
            data = result.get("data", {})
            answer_length = len(str(data.get("answer", "")))
            print(f"回答长度: {answer_length} 字符")
            
    except Exception as e:
        print(f"❌ 快速功能测试失败: {e}")

def analyze_json_parsing_issue():
    """分析JSON解析问题"""
    print("\n📋 JSON解析问题分析")
    print("="*30)
    
    # 模拟LLM返回的markdown格式
    mock_llm_response = '''```json
{
  "queries": [
    "AI发展趋势 2024 2025 预测 报告",
    "人工智能最新技术突破 2024 2025 行业应用"
  ],
  "rationale": "查询设计基于时效性和技术深度"
}
```'''
    
    print("LLM返回示例:")
    print(mock_llm_response[:200] + "...")
    
    # 当前解析方式会失败
    try:
        result = json.loads(mock_llm_response)
        print("✅ 直接JSON解析成功")
    except json.JSONDecodeError as e:
        print(f"❌ 直接JSON解析失败: {e}")
    
    # 正确的解析方式
    import re
    json_match = re.search(r'```json\s*\n(.*?)\n```', mock_llm_response, re.DOTALL)
    if json_match:
        json_content = json_match.group(1)
        try:
            result = json.loads(json_content)
            print("✅ Markdown提取后JSON解析成功")
            print(f"提取的查询数量: {len(result.get('queries', []))}")
        except json.JSONDecodeError as e:
            print(f"❌ 提取后JSON解析仍失败: {e}")
    else:
        print("❌ 未找到JSON代码块")

def generate_optimization_recommendations():
    """生成优化建议"""
    print("\n💡 优化建议")
    print("="*30)
    
    recommendations = [
        "🔧 修复JSON解析: 使用正则表达式提取markdown中的JSON内容",
        "⚡ 优化性能: 为测试环境添加超时控制和mock选项",
        "📋 清理重复实现: 移除未使用的deepsearch_tool.py或标记为废弃",
        "🔄 统一配置: 确保service.json与unified_tool_definitions.yaml一致",
        "🧪 改进测试: 使用更短的测试查询和mock LLM响应",
        "📊 添加监控: 记录研究任务的执行时间和成功率",
        "🛡️ 错误处理: 改进JSON解析失败时的回退机制"
    ]
    
    for i, rec in enumerate(recommendations, 1):
        print(f"{i}. {rec}")

async def main():
    """主函数"""
    await debug_deepsearch_server()
    analyze_json_parsing_issue()
    generate_optimization_recommendations()
    
    print(f"\n🎯 总结")
    print("DeepSearch服务器存在的主要问题:")
    print("1. JSON解析失败 - LLM返回markdown格式需要特殊处理")
    print("2. 性能过慢 - 单次查询27秒导致测试超时")
    print("3. 配置不一致 - 多个配置文件间可能存在差异")
    print("4. 代码重复 - 存在两个工具实现")
    
    print("\n下一步建议: 修复JSON解析问题，这是最高优先级的bug")

if __name__ == "__main__":
    asyncio.run(main())