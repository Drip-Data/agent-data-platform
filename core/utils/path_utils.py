"""
项目路径工具模块
提供统一的路径管理功能，确保所有组件使用正确的工作目录
"""

import os
from pathlib import Path
from typing import Union


def get_project_root() -> Path:
    """获取项目根目录"""
    # 从当前文件向上寻找项目根目录
    current_file = Path(__file__).resolve()
    
    # 查找包含 main.py 的目录作为项目根目录
    for parent in [current_file.parent] + list(current_file.parents):
        if (parent / 'main.py').exists() and (parent / 'requirements.txt').exists():
            return parent
    
    # 如果找不到，返回当前文件的父目录的父目录（core的父目录）
    return current_file.parent.parent


def get_output_dir(subdir: str = "") -> Path:
    """获取输出目录路径"""
    output_dir = get_project_root() / "output"
    if subdir:
        output_dir = output_dir / subdir
    
    # 确保目录存在
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_logs_dir() -> Path:
    """获取日志目录路径"""
    logs_dir = get_project_root() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_config_dir() -> Path:
    """获取配置目录路径"""
    config_dir = get_project_root() / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_data_dir() -> Path:
    """获取数据目录路径"""
    data_dir = get_project_root() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def ensure_output_structure():
    """确保输出目录结构完整"""
    base_dirs = [
        "trajectories",
        "python_execution", 
        "screenshots",
        "logs"
    ]
    
    for dirname in base_dirs:
        get_output_dir(dirname)


# 向后兼容的路径获取函数
def get_trajectories_dir() -> str:
    """获取轨迹存储目录"""
    return str(get_output_dir("trajectories"))


def get_python_execution_dir() -> str:
    """获取Python执行结果目录"""
    return str(get_output_dir("python_execution"))


def get_screenshots_dir() -> Path:
    """获取截图存储目录"""
    return get_output_dir("screenshots")
