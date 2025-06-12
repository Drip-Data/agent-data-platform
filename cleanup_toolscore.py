#!/usr/bin/env python3
"""
ToolScore 目录精简脚本
安全删除冗余文件，保留核心功能
"""

import os
import shutil
from pathlib import Path

def cleanup_toolscore():
    """精简 core/toolscore 目录"""
    
    toolscore_dir = Path("core/toolscore")
    backup_dir = Path("toolscore_backup")
    
    print("🔍 开始分析 core/toolscore 目录结构...")
    
    # 要删除的冗余文件
    files_to_remove = [
        # 功能重复的管理器文件 (已合并到 core_manager.py)
        "tool_sync_manager.py",           # 功能已合并到 core_manager
        "persistent_container_manager.py", # 功能已合并到 core_manager  
        "mcp_image_manager.py",           # 功能已合并到 core_manager
        "real_time_registry.py",          # 功能已合并到 core_manager
        "mcp_cache_manager.py",           # 功能已合并到 core_manager
        "auto_register.py",               # 功能已合并到 core_manager
        "persistent_storage.py",          # 简化的持久化已合并到 core_manager
        
        # 过度设计的适配器文件
        "adapters.py",                    # 适配器模式过度设计，功能简单
        
        # 简单功能文件 (可内联到其他文件)
        "description_engine.py",          # 功能简单，可内联到 unified_tool_library
        "unified_dispatcher.py",          # 分发逻辑简单，可内联
        
        # 内置工具注册文件 (功能可合并)
        "builtin_tools.py",               # 注册逻辑可合并到 unified_tool_library
    ]
    
    # 确保要保留的核心文件存在
    core_files = [
        "interfaces.py",                  # 接口定义，必需
        "unified_tool_library.py",       # 核心工具库，必需
        "monitoring_api.py",              # API接口，必需
        "dynamic_mcp_manager.py",         # MCP管理核心，必需
        "mcp_search_tool.py",             # 工具搜索，已优化
        "tool_registry.py",               # 工具注册表，核心功能
        "mcp_client.py",                  # MCP客户端，必需
        "core_manager.py",                # 新的核心管理器，整合功能
        "__init__.py",                    # 模块导出
    ]
    
    print("📋 将删除以下冗余文件:")
    for file in files_to_remove:
        file_path = toolscore_dir / file
        if file_path.exists():
            print(f"  ❌ {file}")
        else:
            print(f"  ⚠️ {file} (不存在)")
    
    print("\n📋 将保留以下核心文件:")
    for file in core_files:
        file_path = toolscore_dir / file
        if file_path.exists():
            print(f"  ✅ {file}")
        else:
            print(f"  ⚠️ {file} (不存在)")
    
    # 创建备份
    print(f"\n💾 创建备份到 {backup_dir}...")
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    shutil.copytree(toolscore_dir, backup_dir)
    print("✅ 备份完成")
    
    # 确认删除
    response = input("\n❓ 确认删除冗余文件? (y/N): ")
    if response.lower() != 'y':
        print("❌ 已取消删除操作")
        return
    
    # 删除冗余文件
    print("\n🗑️ 开始删除冗余文件...")
    deleted_count = 0
    for file in files_to_remove:
        file_path = toolscore_dir / file
        if file_path.exists():
            try:
                file_path.unlink()
                print(f"  ✅ 已删除: {file}")
                deleted_count += 1
            except Exception as e:
                print(f"  ❌ 删除失败: {file} - {e}")
        else:
            print(f"  ⚠️ 文件不存在: {file}")
    
    print(f"\n🎯 删除完成: 删除了 {deleted_count} 个冗余文件")
    
    # 统计结果
    remaining_files = list(toolscore_dir.glob("*.py"))
    print(f"📊 精简结果:")
    print(f"  - 删除文件: {deleted_count}")
    print(f"  - 保留文件: {len(remaining_files)}")
    print(f"  - 备份位置: {backup_dir}")
    
    print("\n📝 精简后的文件结构:")
    for file_path in sorted(remaining_files):
        size_kb = file_path.stat().st_size / 1024
        print(f"  📄 {file_path.name} ({size_kb:.1f} KB)")
    
    print("\n✨ 精简完成! 如需恢复，请使用备份目录")

def show_analysis():
    """显示文件分析结果"""
    toolscore_dir = Path("core/toolscore")
    
    if not toolscore_dir.exists():
        print("❌ core/toolscore 目录不存在")
        return
    
    print("📊 ToolScore 目录分析结果:")
    print("=" * 50)
    
    # 按功能分类
    categories = {
        "🟢 核心必需": [
            "interfaces.py", "unified_tool_library.py", "monitoring_api.py",
            "dynamic_mcp_manager.py", "mcp_search_tool.py", "tool_registry.py",
            "mcp_client.py", "core_manager.py", "__init__.py"
        ],
        "🟡 功能重复": [
            "tool_sync_manager.py", "persistent_container_manager.py",
            "mcp_image_manager.py", "real_time_registry.py", "mcp_cache_manager.py",
            "auto_register.py", "tool_registry.py", "persistent_storage.py"
        ],
        "🔴 过度设计": [
            "adapters.py", "description_engine.py", "unified_dispatcher.py",
            "builtin_tools.py"
        ]
    }
    
    total_size = 0
    for category, files in categories.items():
        print(f"\n{category}:")
        category_size = 0
        for file in files:
            file_path = toolscore_dir / file
            if file_path.exists():
                size_kb = file_path.stat().st_size / 1024
                total_size += size_kb
                category_size += size_kb
                print(f"  📄 {file:<30} ({size_kb:>6.1f} KB)")
            else:
                print(f"  ⚠️ {file:<30} (不存在)")
        print(f"    小计: {category_size:.1f} KB")
    
    print(f"\n📊 总大小: {total_size:.1f} KB")
    
    # 统计文件数量
    py_files = list(toolscore_dir.glob("*.py"))
    print(f"📊 Python文件总数: {len(py_files)}")
    
    print("\n💡 精简建议:")
    print("  - 可删除 🟡功能重复 和 🔴过度设计 的文件")
    print("  - 功能已合并到 core_manager.py 中")
    print("  - 预计可减少约 50% 的文件数量")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "analyze":
        show_analysis()
    else:
        cleanup_toolscore() 