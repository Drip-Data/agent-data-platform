"""
Python Executor Tool for Reasoning Runtime
支持Python代码执行、数据分析、可视化等操作
"""

import asyncio
import os
import sys
import tempfile
import traceback
import logging
import uuid
import re
from io import StringIO
from typing import Dict, Any, Optional
import subprocess
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core.path_utils import get_python_execution_dir

# Delay matplotlib imports to avoid import errors in other containers
def _get_matplotlib():
    """Lazy import of matplotlib to avoid import errors in containers without it"""
    try:
        import matplotlib
        matplotlib.use('Agg')  # 使用非交互式后端
        import matplotlib.pyplot as plt
        return matplotlib, plt
    except ImportError:
        return None, None

def _get_pandas():
    """Lazy import of pandas to avoid import errors in containers without it"""
    try:
        import pandas as pd
        return pd
    except ImportError:
        return None

def _get_numpy():
    """Lazy import of numpy to avoid import errors in containers without it"""
    try:
        import numpy as np
        return np
    except ImportError:
        return None

logger = logging.getLogger(__name__)

class PythonExecutorTool:
    """Python执行器工具"""
    def __init__(self):
        # 使用统一的路径管理
        self.output_dir = get_python_execution_dir()
        self.temp_dir = tempfile.mkdtemp()
        self._setup_matplotlib()
    
    def _setup_matplotlib(self):
        """设置matplotlib"""
        matplotlib, plt = _get_matplotlib()
        if plt:
            plt.style.use('default')
            plt.rcParams['figure.figsize'] = (10, 6)
            plt.rcParams['font.size'] = 10
    
    def _is_safe_code(self, code: str) -> tuple[bool, str]:
        """基本的代码安全检查"""
        dangerous_patterns = [
            r'import\s+os\s*;.*os\.system',
            r'subprocess\.',
            r'eval\s*\(',
            r'exec\s*\(',
            r'__import__',
            r'open\s*\([^)]*["\'][rwa]',
            r'file\s*\(',
            r'input\s*\(',
            r'raw_input\s*\(',
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                return False, f"Potentially dangerous code detected: {pattern}"
        
        return True, ""
    
    async def execute_code(self, code: str, timeout: int = 30) -> Dict[str, Any]:
        """执行Python代码"""
        # 基本安全检查
        is_safe, reason = self._is_safe_code(code)
        if not is_safe:
            return {
                "success": False,
                "error": f"Code execution blocked: {reason}"
            }
        
        # 使用UUID生成唯一文件名避免竞态条件
        script_path = os.path.join(self.temp_dir, f"script_{uuid.uuid4().hex}.py")
        
        try:
            # 写入代码
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(code)
            
            # 执行代码
            process = await asyncio.create_subprocess_exec(
                sys.executable, script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.temp_dir
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                
                return {
                    "success": process.returncode == 0,
                    "stdout": stdout.decode('utf-8', errors='replace'),
                    "stderr": stderr.decode('utf-8', errors='replace'),
                    "return_code": process.returncode,
                    "execution_time": timeout if process.returncode != 0 else None
                }
            
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "success": False,
                    "error": "Code execution timeout",
                    "timeout": timeout
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
        
        finally:
            # 清理临时文件
            try:
                if os.path.exists(script_path):
                    os.remove(script_path)
            except:
                pass
    
    async def analyze_data(self, data: Any, operation: str = "describe") -> Dict[str, Any]:
        """数据分析"""
        try:
            pd = _get_pandas()
            if not pd:
                return {
                    "success": False,
                    "error": "pandas not available in this environment"
                }
                
            if isinstance(data, (list, tuple)):
                df = pd.DataFrame(data)
            elif isinstance(data, dict):
                df = pd.DataFrame([data]) if not isinstance(list(data.values())[0], (list, tuple)) else pd.DataFrame(data)
            else:
                return {"success": False, "error": "Unsupported data type"}
            
            if operation == "describe":
                result = df.describe()
            elif operation == "info":
                # 使用StringIO而不是list作为缓冲区
                buffer = StringIO()
                df.info(buf=buffer)
                result = buffer.getvalue()
            elif operation == "head":
                result = df.head()
            elif operation == "tail":
                result = df.tail()
            else:
                result = df
            
            return {
                "success": True,
                "result": result.to_string() if hasattr(result, 'to_string') else str(result),
                "data_shape": df.shape,
                "columns": df.columns.tolist()
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
    
    async def create_visualization(self, data: Any, plot_type: str = "line", 
                                 title: str = "Data Visualization", 
                                 save_path: Optional[str] = None) -> Dict[str, Any]:
        """创建可视化图表"""
        try:
            matplotlib, plt = _get_matplotlib()
            if not matplotlib or not plt:
                return {
                    "success": False,
                    "error": "matplotlib not available in this environment"
                }
                
            plt.figure(figsize=(10, 6))
            
            if isinstance(data, (list, tuple)):
                if plot_type == "line":
                    plt.plot(data)
                elif plot_type == "bar":
                    plt.bar(range(len(data)), data)
                elif plot_type == "hist":
                    plt.hist(data, bins=20)
                elif plot_type == "scatter":
                    if len(data) >= 2 and all(isinstance(x, (list, tuple)) for x in data[:2]):
                        plt.scatter(data[0], data[1])
                    else:
                        plt.scatter(range(len(data)), data)
            
            elif isinstance(data, dict):
                if plot_type == "bar":
                    plt.bar(data.keys(), data.values())
                elif plot_type == "pie":
                    plt.pie(data.values(), labels=data.keys(), autopct='%1.1f%%')
            
            plt.title(title)
            plt.grid(True, alpha=0.3)
            
            if not save_path:
                # 使用UUID生成唯一文件名避免竞态条件
                save_path = os.path.join(self.output_dir, f"plot_{uuid.uuid4().hex}.png")
            
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            plt.close()
            
            return {
                "success": True,
                "plot_path": save_path,
                "plot_type": plot_type,
                "message": f"Visualization saved to {save_path}"
            }
        
        except Exception as e:
            matplotlib, plt = _get_matplotlib()
            if plt:
                plt.close()  # 确保关闭图形
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
    
    def _is_safe_package_name(self, package_name: str) -> bool:
        """验证包名是否安全"""
        # 基本的包名验证
        if not re.match(r'^[a-zA-Z0-9_-]+([.][a-zA-Z0-9_-]+)*$', package_name):
            return False
        
        # 检查是否包含危险字符
        dangerous_chars = ['&', '|', ';', '`', '$', '(', ')', '{', '}']
        if any(char in package_name for char in dangerous_chars):
            return False
            
        return True
    
    async def install_package(self, package_name: str) -> Dict[str, Any]:
        """安装Python包"""
        # 验证包名安全性
        if not self._is_safe_package_name(package_name):
            return {
                "success": False,
                "error": "Invalid or potentially unsafe package name",
                "package": package_name
            }
        
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", package_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            return {
                "success": process.returncode == 0,
                "package": package_name,
                "stdout": stdout.decode('utf-8', errors='replace'),
                "stderr": stderr.decode('utf-8', errors='replace'),
                "return_code": process.returncode
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "package": package_name
            }
    
    def cleanup(self):
        """清理资源"""
        try:
            if os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir)
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

# 全局Python执行器实例
python_executor_tool = PythonExecutorTool()
