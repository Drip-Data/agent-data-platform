#!/usr/bin/env python3
"""
测试auto_select智能action选择功能
Test Auto-Select Intelligent Action Selection
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime

def test_auto_select_logic():
    """测试auto_select逻辑"""
    print("🧪 测试auto_select智能action选择")
    
    # 创建mock runtime实例 (只为了测试_auto_select_action方法)
    class MockRuntime:
        def _auto_select_action(self, tool_id: str, params: dict, thinking: str):
            # 复制enhanced_runtime的逻辑
            instruction = params.get('instruction', '').lower()
            
            if tool_id == 'microsandbox':
                if any(keyword in instruction for keyword in ['install', 'pip', 'package', '安装']):
                    words = instruction.split()
                    package_name = None
                    for word in words:
                        if word not in ['install', 'pip', 'package', '安装'] and not word.startswith('-'):
                            package_name = word
                            break
                    if package_name:
                        return 'microsandbox_install_package', {'package_name': package_name}
                elif any(keyword in instruction for keyword in ['session', 'list', '会话', '列表']):
                    return 'microsandbox_list_sessions', {}
                else:
                    return 'microsandbox_execute', {'code': params.get('instruction', '')}
                    
            elif tool_id == 'mcp-deepsearch':
                if any(keyword in instruction for keyword in ['quick', 'fast', '快速', '简单']):
                    return 'quick_research', {'question': params.get('instruction', '')}
                elif any(keyword in instruction for keyword in ['comprehensive', 'detailed', '全面', '详细']):
                    return 'comprehensive_research', {'question': params.get('instruction', '')}
                else:
                    return 'research', {'question': params.get('instruction', '')}
                    
            elif tool_id == 'browser_use':
                if any(keyword in instruction for keyword in ['navigate', 'goto', 'visit', '访问', '导航']):
                    words = instruction.split()
                    url = None
                    for word in words:
                        if 'http' in word or '.' in word:
                            url = word
                            break
                    if url:
                        return 'browser_navigate', {'url': url}
                elif any(keyword in instruction for keyword in ['search', 'google', '搜索']):
                    return 'browser_search_google', {'query': params.get('instruction', '')}
                else:
                    return 'browser_use_execute_task', {'task': params.get('instruction', '')}
                    
            elif tool_id == 'mcp-search-tool':
                if any(keyword in instruction for keyword in ['definition', 'define', '定义', '查找']):
                    return 'list_code_definitions', {'directory_path': 'src/'}
                elif any(keyword in instruction for keyword in ['analyze', 'need', '分析', '需求']):
                    return 'analyze_tool_needs', {'task_description': params.get('instruction', '')}
                else:
                    return 'search_file_content', {
                        'regex_pattern': params.get('instruction', ''),
                        'file_path': 'src/'
                    }
            
            return 'execute', {'instruction': params.get('instruction', '')}
    
    runtime = MockRuntime()
    
    # 测试用例
    test_cases = [
        # Microsandbox测试
        {
            "name": "代码执行",
            "tool_id": "microsandbox", 
            "instruction": "print('Hello World')\nx = 1 + 1",
            "expected_action": "microsandbox_execute"
        },
        {
            "name": "包安装 - pip install",
            "tool_id": "microsandbox",
            "instruction": "install numpy",
            "expected_action": "microsandbox_install_package",
            "expected_params": {"package_name": "numpy"}
        },
        {
            "name": "包安装 - 中文",
            "tool_id": "microsandbox", 
            "instruction": "安装 pandas",
            "expected_action": "microsandbox_install_package",
            "expected_params": {"package_name": "pandas"}
        },
        {
            "name": "会话列表",
            "tool_id": "microsandbox",
            "instruction": "list all sessions",
            "expected_action": "microsandbox_list_sessions"
        },
        
        # DeepSearch测试
        {
            "name": "普通研究",
            "tool_id": "mcp-deepsearch",
            "instruction": "Python machine learning libraries",
            "expected_action": "research"
        },
        {
            "name": "快速研究",
            "tool_id": "mcp-deepsearch",
            "instruction": "quick overview of React hooks",
            "expected_action": "quick_research"
        },
        {
            "name": "全面研究",
            "tool_id": "mcp-deepsearch",
            "instruction": "comprehensive analysis of blockchain trends",
            "expected_action": "comprehensive_research"
        },
        
        # Browser测试
        {
            "name": "网页导航",
            "tool_id": "browser_use",
            "instruction": "navigate to https://github.com",
            "expected_action": "browser_navigate",
            "expected_params": {"url": "https://github.com"}
        },
        {
            "name": "Google搜索",
            "tool_id": "browser_use",
            "instruction": "search for Python tutorials on Google",
            "expected_action": "browser_search_google"
        },
        {
            "name": "浏览器任务",
            "tool_id": "browser_use",
            "instruction": "fill out the contact form with my details",
            "expected_action": "browser_use_execute_task"
        },
        
        # Search Tool测试
        {
            "name": "代码定义查找",
            "tool_id": "mcp-search-tool",
            "instruction": "find all function definitions in the project",
            "expected_action": "list_code_definitions"
        },
        {
            "name": "工具需求分析",
            "tool_id": "mcp-search-tool",
            "instruction": "analyze what tools are needed for this task",
            "expected_action": "analyze_tool_needs"
        },
        {
            "name": "文件搜索",
            "tool_id": "mcp-search-tool",
            "instruction": "class.*Manager",
            "expected_action": "search_file_content"
        }
    ]
    
    print(f"📋 运行 {len(test_cases)} 个测试用例")
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n🔍 [{i}] 测试: {test['name']}")
        print(f"   工具: {test['tool_id']}")
        print(f"   指令: {test['instruction']}")
        
        # 执行auto_select
        action, params = runtime._auto_select_action(
            test['tool_id'],
            {'instruction': test['instruction']},
            "test thinking"
        )
        
        print(f"   结果: {action}")
        print(f"   参数: {params}")
        
        # 验证action
        if action == test['expected_action']:
            print("   ✅ Action匹配")
            action_ok = True
        else:
            print(f"   ❌ Action不匹配，期望: {test['expected_action']}")
            action_ok = False
        
        # 验证参数（如果有期望参数）
        params_ok = True
        if 'expected_params' in test:
            for key, expected_value in test['expected_params'].items():
                if params.get(key) == expected_value:
                    print(f"   ✅ 参数 {key} 匹配: {expected_value}")
                else:
                    print(f"   ❌ 参数 {key} 不匹配，期望: {expected_value}, 实际: {params.get(key)}")
                    params_ok = False
        
        if action_ok and params_ok:
            print("   🎉 测试通过")
            passed += 1
        else:
            print("   💥 测试失败")
            failed += 1
    
    print(f"\n📊 测试结果:")
    print(f"   ✅ 通过: {passed}")
    print(f"   ❌ 失败: {failed}")
    print(f"   📈 成功率: {passed/(passed+failed)*100:.1f}%")
    
    if failed == 0:
        print("🎉 所有auto_select测试通过！")
    else:
        print(f"⚠️ 有 {failed} 个测试失败")
    
    return failed == 0

if __name__ == "__main__":
    test_auto_select_logic()