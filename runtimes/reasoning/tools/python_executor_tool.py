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
from typing import Dict, Any, Optional
import subprocess

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
        self.output_dir = "/app/output"
        self.temp_dir = tempfile.mkdtemp()
        self._setup_matplotlib()
    
    def _setup_matplotlib(self):
        """设置matplotlib"""
        matplotlib, plt = _get_matplotlib()
        if plt:
            plt.style.use('default')
            plt.rcParams['figure.figsize'] = (10, 6)
            plt.rcParams['font.size'] = 10
    
    async def execute_code(self, code: str, timeout: int = 30) -> Dict[str, Any]:
        """执行Python代码"""
        # 创建临时文件
        script_path = os.path.join(self.temp_dir, f"script_{asyncio.get_event_loop().time()}.py")
        
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
                buffer = []
                df.info(buf=buffer)
                result = '\n'.join(buffer)
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
                save_path = os.path.join(self.output_dir, f"plot_{int(asyncio.get_event_loop().time())}.png")
            
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
    
    async def install_package(self, package_name: str) -> Dict[str, Any]:
        """安装Python包"""
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
