#!/usr/bin/env python3
"""
结构化工具系统测试脚本
验证Pydantic工具定义、JSON Schema校验和预校验中间件
"""

import sys
import os
import json
import pytest
from typing import Dict, Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.toolscore.structured_tools import tool_registry, LLMRequest, ToolValidationError
from core.toolscore.tool_definitions import *
from core.llm.validation_middleware import validation_middleware


def test_tool_registration():
    """测试工具注册"""
    print("=== 测试工具注册 ===")
    
    tools = tool_registry.get_all_tools()
    print(f"已注册工具数量: {len(tools)}")
    
    expected_tools = ["mcp-deepsearch", "microsandbox-mcp-server", "browser-use-mcp-server", "mcp-search-tool"]
    registered_tool_ids = [tool.id for tool in tools]
    
    for expected in expected_tools:
        if expected in registered_tool_ids:
            print(f"✅ {expected} 已注册")
        else:
            print(f"❌ {expected} 未注册")
    
    return len(tools) >= 4


def test_valid_request_validation():
    """测试有效请求的校验"""
    print("\n=== 测试有效请求校验 ===")
    
    valid_request = {
        "thinking": "用户要求研究Python asyncio，应该使用deepsearch工具",
        "action": "research",
        "tool_id": "mcp-deepsearch",
        "parameters": {
            "query": "Python asyncio最佳实践",
            "max_results": 10
        },
        "confidence": 0.9
    }
    
    try:
        is_valid, validated_data, error = validation_middleware.validate_before_llm_call(valid_request)
        if is_valid:
            print("✅ 有效请求校验通过")
            print(f"   校验后数据: {json.dumps(validated_data, ensure_ascii=False, indent=2)}")
            return True
        else:
            print(f"❌ 有效请求校验失败: {error}")
            return False
    except Exception as e:
        print(f"❌ 校验过程出错: {e}")
        return False


def test_invalid_request_correction():
    """测试无效请求的自动纠正"""
    print("\n=== 测试无效请求自动纠正 ===")
    
    # 这是我们之前遇到的典型错误：search_and_install_tools 被错误分配给 mcp-deepsearch
    invalid_request = {
        "thinking": "需要搜索和安装工具",
        "action": "search_and_install_tools",  # 错误：这个action不属于mcp-deepsearch
        "tool_id": "mcp-deepsearch",          # 错误的工具ID
        "parameters": {
            "task_description": "需要处理PDF文件"
        },
        "confidence": 0.8
    }
    
    try:
        is_valid, validated_data, error = validation_middleware.validate_before_llm_call(invalid_request)
        if is_valid:
            print("✅ 无效请求已自动纠正")
            print(f"   原始: {invalid_request['tool_id']}.{invalid_request['action']}")
            print(f"   纠正: {validated_data['tool_id']}.{validated_data['action']}")
            return True
        else:
            print(f"❌ 无效请求无法纠正: {error}")
            return False
    except Exception as e:
        print(f"❌ 纠正过程出错: {e}")
        return False


def test_parameter_validation():
    """测试参数校验"""
    print("\n=== 测试参数校验 ===")
    
    # 测试缺少必需参数的情况
    invalid_params_request = {
        "thinking": "要执行代码但没提供code参数",
        "action": "microsandbox_execute",
        "tool_id": "microsandbox-mcp-server",
        "parameters": {
            # 缺少必需的 "code" 参数
            "timeout": 30
        },
        "confidence": 0.7
    }
    
    try:
        is_valid, validated_data, error = validation_middleware.validate_before_llm_call(invalid_params_request)
        if not is_valid and "参数校验失败" in error:
            print("✅ 参数校验正确识别了缺失的必需参数")
            print(f"   错误信息: {error}")
            return True
        else:
            print(f"❌ 参数校验未能识别错误")
            return False
    except Exception as e:
        print(f"❌ 参数校验过程出错: {e}")
        return False


def test_tool_description_generation():
    """测试工具描述生成"""
    print("\n=== 测试工具描述生成 ===")
    
    try:
        description = tool_registry.generate_llm_tools_description()
        print("✅ 工具描述生成成功")
        print("--- 生成的工具描述 ---")
        print(description[:500] + "..." if len(description) > 500 else description)
        
        # 检查是否包含关键信息
        checks = [
            "mcp-deepsearch" in description,
            "microsandbox-mcp-server" in description,
            "research" in description,
            "microsandbox_execute" in description
        ]
        
        if all(checks):
            print("✅ 工具描述包含所有必要信息")
            return True
        else:
            print("❌ 工具描述缺少某些关键信息")
            return False
            
    except Exception as e:
        print(f"❌ 工具描述生成失败: {e}")
        return False


def test_validation_stats():
    """测试校验统计"""
    print("\n=== 测试校验统计 ===")
    
    # 重置统计
    validation_middleware.reset_stats()
    
    # 执行几个测试请求
    test_requests = [
        {"thinking": "test1", "action": "research", "tool_id": "mcp-deepsearch", "parameters": {"question": "test"}},
        {"thinking": "test2", "action": "search_and_install_tools", "tool_id": "mcp-deepsearch", "parameters": {"task_description": "test"}},  # 需要纠正
        {"thinking": "test3", "action": "invalid_action", "tool_id": "invalid_tool", "parameters": {}},  # 无效
    ]
    
    for req in test_requests:
        try:
            validation_middleware.validate_before_llm_call(req)
        except:
            pass  # 忽略错误，只关注统计
    
    stats = validation_middleware.get_validation_stats()
    print(f"✅ 校验统计:")
    print(f"   总请求数: {stats['total_requests']}")
    print(f"   有效请求: {stats['valid_requests']}")
    print(f"   自动纠正: {stats['auto_corrected']}")
    print(f"   失败请求: {stats['invalid_requests']}")
    
    return stats['total_requests'] == 3


def main():
    """运行所有测试"""
    print("🚀 开始结构化工具系统测试\n")
    
    tests = [
        ("工具注册", test_tool_registration),
        ("有效请求校验", test_valid_request_validation),
        ("无效请求自动纠正", test_invalid_request_correction),
        ("参数校验", test_parameter_validation),
        ("工具描述生成", test_tool_description_generation),
        ("校验统计", test_validation_stats),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                print(f"✅ {test_name} - 通过")
                passed += 1
            else:
                print(f"❌ {test_name} - 失败")
        except Exception as e:
            print(f"💥 {test_name} - 异常: {e}")
    
    print(f"\n📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！结构化工具系统工作正常。")
        return 0
    else:
        print("⚠️ 部分测试失败，需要检查实现。")
        return 1


if __name__ == "__main__":
    exit(main())