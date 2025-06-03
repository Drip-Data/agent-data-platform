#!/usr/bin/env python3
"""
Synthesis数据库初始化工具命令行入口
"""

import sys
from ..init_synthesis_db import init_synthesis_database as init_database

def main():
    """命令行入口点"""
    import argparse
    
    parser = argparse.ArgumentParser(description="初始化synthesis数据库")
    parser.add_argument("--db", default="output/synthesis.db", help="数据库路径（此参数暂时无效，使用环境变量SYNTHESIS_DB）")
    parser.add_argument("--force", action="store_true", help="强制重新初始化（此参数暂时无效）")
    
    args = parser.parse_args()
    
    try:
        # 注意：当前的init_synthesis_database函数不接受参数
        # 它从环境变量SYNTHESIS_DB读取数据库路径
        success = init_database()
        if success:
            print("✅ 数据库初始化成功")
            return 0
        else:
            print("❌ 数据库初始化失败")
            return 1
    except Exception as e:
        print(f"❌ 数据库初始化失败: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 