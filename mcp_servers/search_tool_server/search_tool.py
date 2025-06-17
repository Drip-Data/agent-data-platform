import logging
import asyncio
import os
import re
from typing import Dict, Any, List, Optional
import ast

logger = logging.getLogger(__name__)

class SearchTool:
    """提供文件内容搜索和代码定义搜索功能的工具"""

    def __init__(self):
        logger.info("SearchTool 初始化完成。")

    async def search_file_content(self, file_path: str, regex_pattern: str) -> Dict:
        """
        在指定文件中搜索匹配正则表达式的内容。
        """
        logger.info(f"在文件 '{file_path}' 中搜索模式: '{regex_pattern}'")
        if not os.path.exists(file_path):
            return {
                "success": False,
                "output": None,
                "error_message": f"文件不存在: {file_path}",
                "error_type": "FileNotFound"
            }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            matches = []
            for line_num, line in enumerate(content.splitlines()):
                if re.search(regex_pattern, line):
                    matches.append(f"Line {line_num + 1}: {line.strip()}")
            
            if matches:
                return {
                    "success": True,
                    "output": {"matches": matches, "count": len(matches)},
                    "error_message": None,
                    "error_type": None
                }
            else:
                return {
                    "success": True,
                    "output": {"matches": [], "count": 0},
                    "error_message": "未找到匹配项。",
                    "error_type": None
                }
        except Exception as e:
            logger.error(f"搜索文件内容失败: {e}", exc_info=True)
            return {
                "success": False,
                "output": None,
                "error_message": f"搜索文件内容时发生错误: {str(e)}",
                "error_type": "SearchError"
            }

    async def list_code_definitions(self, file_path: Optional[str] = None, directory_path: Optional[str] = None) -> Dict:
        """
        列出指定文件或目录中Python代码的类、函数和方法定义。
        """
        logger.info(f"列出代码定义 - 文件: {file_path}, 目录: {directory_path}")
        
        definitions = []
        
        if file_path:
            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "output": None,
                    "error_message": f"文件不存在: {file_path}",
                    "error_type": "FileNotFound"
                }
            if not file_path.endswith('.py'):
                return {
                    "success": False,
                    "output": None,
                    "error_message": f"不支持的文件类型，只支持Python文件: {file_path}",
                    "error_type": "UnsupportedFileType"
                }
            definitions.extend(self._parse_python_file(file_path))
        elif directory_path:
            if not os.path.isdir(directory_path):
                return {
                    "success": False,
                    "output": None,
                    "error_message": f"目录不存在: {directory_path}",
                    "error_type": "DirectoryNotFound"
                }
            for root, _, files in os.walk(directory_path):
                for file in files:
                    if file.endswith('.py'):
                        full_path = os.path.join(root, file)
                        definitions.extend(self._parse_python_file(full_path))
        else:
            return {
                "success": False,
                "output": None,
                "error_message": "必须提供文件路径或目录路径。",
                "error_type": "MissingParameter"
            }
            
        if definitions:
            return {
                "success": True,
                "output": {"definitions": definitions, "count": len(definitions)},
                "error_message": None,
                "error_type": None
            }
        else:
            return {
                "success": True,
                "output": {"definitions": [], "count": 0},
                "error_message": "未找到任何代码定义。",
                "error_type": None
            }

    def _parse_python_file(self, file_path: str) -> List[Dict[str, Any]]:
        """解析Python文件以提取类、函数和方法定义。"""
        file_definitions = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read(), filename=file_path)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    file_definitions.append({
                        "type": "class",
                        "name": node.name,
                        "file": file_path,
                        "line": node.lineno
                    })
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            file_definitions.append({
                                "type": "method",
                                "name": f"{node.name}.{item.name}",
                                "file": file_path,
                                "line": item.lineno
                            })
                elif isinstance(node, ast.FunctionDef):
                    # 确保不是类内部的方法，因为方法已经在ClassDef中处理
                    if not isinstance(getattr(node, 'parent', None), ast.ClassDef):
                        file_definitions.append({
                            "type": "function",
                            "name": node.name,
                            "file": file_path,
                            "line": node.lineno
                        })
        except Exception as e:
            logger.warning(f"解析Python文件 '{file_path}' 失败: {e}", exc_info=True)
        return file_definitions