#!/usr/bin/env python3
"""
路径修复验证脚本
检查并验证所有组件的路径设置是否正确使用项目相对路径
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.utils.path_utils import (
    get_project_root, 
    get_output_dir, 
    get_trajectories_dir,
    get_synthesis_task_dir,
    get_logs_dir,
    get_config_dir,
    get_data_dir,
    ensure_output_structure
)

def test_path_functions():
    """测试路径函数"""
    print("=== 路径函数测试 ===")
    
    paths = {
        "项目根目录": get_project_root(),
        "输出目录": get_output_dir(),
        "轨迹目录": get_trajectories_dir(),
        "合成任务目录": get_synthesis_task_dir(),
        "日志目录": get_logs_dir(),
        "配置目录": get_config_dir(),
        "数据目录": get_data_dir()
    }
    
    for name, path in paths.items():
        print(f"{name}: {path}")
        if not Path(path).exists():
            print(f"  ⚠️ 目录不存在，将创建")
        else:
            print(f"  ✅ 目录存在")
    
    print("\n=== 确保输出结构完整 ===")
    ensure_output_structure()
    print("✅ 输出目录结构已确保完整")


def check_hardcoded_paths():
    """检查代码中是否还有硬编码路径"""
    print("\n=== 检查硬编码路径 ===")
    
    # 要检查的模式
    patterns = [
        "/app/output",
        "output/",
        "../output",
        "./output"
    ]
    
    # 要检查的文件
    files_to_check = [
        "main.py",
        "core/task_manager.py",
        "runtimes/reasoning/enhanced_runtime.py",
        "mcp_servers/microsandbox_server/main.py",
        # "mcp_servers/python_executor_server/python_executor_tool.py",  # DEPRECATED
        # "mcp_servers/browser_navigator_server/browser_tool.py",  # DEPRECATED
        "scripts/batch_test_tasks.py"
    ]
    
    issues_found = []
    
    for file_path in files_to_check:
        full_path = project_root / file_path
        if not full_path.exists():
            print(f"⚠️ 文件不存在: {file_path}")
            continue
            
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            for pattern in patterns:
                if pattern in content:
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        if pattern in line and not line.strip().startswith('#'):
                            issues_found.append(f"{file_path}:{i} - {line.strip()}")
                            
        except Exception as e:
            print(f"❌ 读取文件失败 {file_path}: {e}")
    
    if issues_found:
        print("发现硬编码路径:")
        for issue in issues_found:
            print(f"  ⚠️ {issue}")
    else:
        print("✅ 未发现硬编码路径问题")


def test_component_imports():
    """测试组件是否能正确导入和使用路径工具"""
    print("\n=== 测试组件导入 ===")
    
    try:
        from core.task_manager import TaskManager
        print("✅ TaskManager 导入成功")
    except Exception as e:
        print(f"❌ TaskManager 导入失败: {e}")
    
    try:
        from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime
        print("✅ EnhancedReasoningRuntime 导入成功")
    except Exception as e:
        print(f"❌ EnhancedReasoningRuntime 导入失败: {e}")
    
    try:
        # from mcp_servers.python_executor_server.python_executor_tool import PythonExecutorTool  # DEPRECATED
        from mcp_servers.microsandbox_server.main import MicroSandboxMCPServer
        print("✅ MicroSandbox Server 导入成功 (已替换PythonExecutorTool)")
    except Exception as e:
        print(f"❌ MicroSandbox Server 导入失败: {e}")
    
    try:
        # from mcp_servers.browser_navigator_server.browser_tool import BrowserTool  # DEPRECATED
        from mcp_servers.browser_use_server.main import BrowserUseMCPServer
        print("✅ Browser-Use Server 导入成功 (已替换BrowserTool)")
    except Exception as e:
        print(f"❌ Browser-Use Server 导入失败: {e}")


def create_test_output():
    """创建测试输出文件，验证路径工作正常"""
    print("\n=== 创建测试输出 ===")
    
    try:
        # 测试轨迹目录
        test_trajectory = {
            "task_id": "test_path_validation",
            "task_description": "路径验证测试",
            "success": True,
            "created_at": "2025-06-15T10:00:00"
        }
        
        trajectory_file = Path(get_trajectories_dir()) / "test_trajectory.json"
        with open(trajectory_file, 'w', encoding='utf-8') as f:
            import json
            json.dump(test_trajectory, f, ensure_ascii=False, indent=2)
        print(f"✅ 测试轨迹文件创建: {trajectory_file}")
        
        # 测试合成任务目录
        synthesis_test_file = Path(get_synthesis_task_dir()) / "test_synthesis.txt"
        with open(synthesis_test_file, 'w', encoding='utf-8') as f:
            f.write("合成任务路径验证测试\n")
        print(f"✅ 测试合成任务文件创建: {synthesis_test_file}")
        
        print("✅ 所有测试输出文件创建成功")
        
    except Exception as e:
        print(f"❌ 创建测试输出失败: {e}")


def cleanup_test_files():
    """清理测试文件"""
    print("\n=== 清理测试文件 ===")
    
    test_files = [
        Path(get_trajectories_dir()) / "test_trajectory.json",
        Path(get_synthesis_task_dir()) / "test_synthesis.txt"
    ]
    
    for file_path in test_files:
        try:
            if file_path.exists():
                file_path.unlink()
                print(f"✅ 已删除测试文件: {file_path}")
        except Exception as e:
            print(f"⚠️ 删除测试文件失败 {file_path}: {e}")


def main():
    """主函数"""
    print("🔍 Agent Data Platform 路径验证")
    print(f"项目根目录: {project_root}")
    print("=" * 60)
    
    # 1. 测试路径函数
    test_path_functions()
    
    # 2. 检查硬编码路径
    check_hardcoded_paths()
    
    # 3. 测试组件导入
    test_component_imports()
    
    # 4. 创建测试输出
    create_test_output()
    
    # 5. 清理测试文件
    cleanup_test_files()
    
    print("\n" + "=" * 60)
    print("✅ 路径验证完成")
    print("💡 如果发现问题，请根据上述报告进行修复")


if __name__ == "__main__":
    main()
