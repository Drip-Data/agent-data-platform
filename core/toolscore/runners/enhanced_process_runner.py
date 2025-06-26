"""
增强的进程运行器
集成智能检测器、错误处理和重试机制，提供更稳定的MCP服务器管理
"""

import asyncio
import logging
import subprocess
import tempfile
import shutil
import time
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from .process_runner import ProcessRunner
from ..detectors import SmartEntryPointDetector, RuntimeDetector
from ..exceptions import (
    MCPInstallationError, EntryPointNotFoundError, DependencyInstallError,
    ServerStartupError, PortAllocationError, create_entry_point_error,
    create_dependency_error, create_startup_error
)

logger = logging.getLogger(__name__)


class EnhancedProcessRunner(ProcessRunner):
    """
    增强的进程运行器
    在原有ProcessRunner基础上添加智能检测、错误处理和重试机制
    """
    
    def __init__(self):
        super().__init__()
        
        # 智能检测器
        self.entry_point_detector = SmartEntryPointDetector()
        self.runtime_detector = RuntimeDetector()
        
        # 重试配置
        self.max_install_retries = 3
        self.max_startup_retries = 2
        self.retry_delays = [1.0, 2.0, 4.0]  # 指数退避
        
        # 统计信息
        self.installation_stats = {
            "total_attempts": 0,
            "successful_installs": 0,
            "failed_installs": 0,
            "retry_count": 0
        }
        
        # 错误历史
        self.error_history = []
        self.max_error_history = 100
    
    async def install_server_with_enhanced_detection(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用增强检测安装MCP服务器
        这是新的主要入口点，提供更好的错误处理和重试机制
        
        Args:
            candidate: 候选服务器配置
            
        Returns:
            安装结果字典
        """
        server_id = candidate.get('id', 'unknown')
        self.installation_stats["total_attempts"] += 1
        
        logger.info(f"🚀 开始安装MCP服务器: {server_id}")
        
        for attempt in range(self.max_install_retries):
            try:
                result = await self._install_with_detection(candidate, attempt + 1)
                
                if result.get("success"):
                    self.installation_stats["successful_installs"] += 1
                    logger.info(f"✅ 服务器安装成功: {server_id} (尝试 {attempt + 1}/{self.max_install_retries})")
                    return result
                else:
                    # 记录失败原因
                    error_msg = result.get("error_msg", "未知错误")
                    self._record_error(server_id, error_msg, attempt + 1)
                    
                    if attempt < self.max_install_retries - 1:
                        delay = self.retry_delays[min(attempt, len(self.retry_delays) - 1)]
                        logger.warning(f"⚠️ 安装失败，{delay}秒后重试: {error_msg}")
                        await asyncio.sleep(delay)
                        self.installation_stats["retry_count"] += 1
                    
            except Exception as e:
                error_msg = str(e)
                self._record_error(server_id, error_msg, attempt + 1)
                
                if attempt < self.max_install_retries - 1:
                    delay = self.retry_delays[min(attempt, len(self.retry_delays) - 1)]
                    logger.warning(f"⚠️ 安装异常，{delay}秒后重试: {error_msg}")
                    await asyncio.sleep(delay)
                    self.installation_stats["retry_count"] += 1
                else:
                    logger.error(f"❌ 服务器安装失败，已达最大重试次数: {server_id}")
        
        # 所有重试都失败了
        self.installation_stats["failed_installs"] += 1
        return {
            "success": False,
            "error_msg": f"安装失败，已重试{self.max_install_retries}次",
            "server_id": server_id,
            "error_history": self._get_error_history(server_id)
        }
    
    async def _install_with_detection(self, candidate: Dict[str, Any], attempt: int) -> Dict[str, Any]:
        """使用智能检测进行安装"""
        temp_dir = None
        server_id = candidate.get('id', 'unknown')
        
        try:
            # 1. 克隆仓库或使用本地路径
            temp_dir = await self._safe_clone_repository(candidate)
            if not temp_dir:
                # 如果没有URL且没有本地路径，则跳过此服务器
                logger.info(f"⏭️ 跳过服务器 {server_id}：无有效的安装路径")
                return {
                    "success": False,
                    "error_msg": "无有效的GitHub URL或本地路径",
                    "server_id": server_id,
                    "skipped": True
                }
            
            # 2. 智能检测项目类型
            project_type = self._detect_project_type_enhanced(temp_dir, candidate)
            logger.info(f"📊 检测到项目类型: {project_type}")
            
            # 3. 智能检测入口点
            entry_point = self._find_entry_point_enhanced(temp_dir, project_type, candidate)
            if not entry_point:
                raise create_entry_point_error(
                    str(temp_dir), 
                    project_type,
                    self.entry_point_detector.PYTHON_PATTERNS if project_type == "python" else self.entry_point_detector.NODEJS_PATTERNS
                )
            
            logger.info(f"🎯 检测到入口点: {entry_point}")
            
            # 4. 安装依赖
            await self._install_dependencies_enhanced(temp_dir, project_type, candidate)
            
            # 5. 启动服务器
            server_info = await self._start_server_enhanced(temp_dir, project_type, entry_point, candidate)
            
            return {
                "success": True,
                "server_info": server_info,
                "project_type": project_type,
                "entry_point": entry_point,
                "temp_dir": str(temp_dir),
                "attempt": attempt
            }
            
        except Exception as e:
            logger.error(f"❌ 安装步骤失败 (尝试 {attempt}): {e}")
            
            # 清理临时目录
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception as cleanup_error:
                    logger.warning(f"⚠️ 清理临时目录失败: {cleanup_error}")
            
            # 重新抛出异常，让上层处理重试
            raise e
    
    def _detect_project_type_enhanced(self, project_path: Path, candidate: Dict[str, Any]) -> str:
        """增强的项目类型检测"""
        try:
            # 1. 优先使用配置中指定的项目类型
            if 'project_type' in candidate:
                specified_type = candidate['project_type']
                logger.info(f"📋 使用配置指定的项目类型: {specified_type}")
                return specified_type
            
            # 2. 使用智能检测器
            detected_type = self.runtime_detector.detect_project_type(project_path)
            return detected_type.value
            
        except Exception as e:
            logger.warning(f"⚠️ 项目类型检测失败，使用默认值: {e}")
            return "python"  # 默认值
    
    def _find_entry_point_enhanced(self, project_path: Path, project_type: str, candidate: Dict[str, Any]) -> Optional[str]:
        """增强的入口点检测"""
        try:
            # 使用智能入口点检测器
            entry_point = self.entry_point_detector.detect_entry_point(
                project_path, 
                project_type, 
                candidate
            )
            
            if entry_point:
                # 验证入口点文件是否存在
                if self._validate_entry_point(project_path, entry_point):
                    return entry_point
                else:
                    logger.warning(f"⚠️ 检测到的入口点文件不存在: {entry_point}")
            
            # 如果智能检测失败，回退到原始方法
            logger.info("🔄 回退到原始入口点检测方法")
            return super()._find_entry_point(project_path, project_type)
            
        except Exception as e:
            logger.error(f"❌ 入口点检测失败: {e}")
            return None
    
    def _validate_entry_point(self, project_path: Path, entry_point: str) -> bool:
        """验证入口点的有效性"""
        if entry_point == "npm start":
            # 检查package.json和start脚本
            package_json = project_path / "package.json"
            return package_json.exists()
        
        entry_file = project_path / entry_point
        return entry_file.exists() and entry_file.is_file()
    
    async def _install_dependencies_enhanced(self, project_path: Path, project_type: str, candidate: Dict[str, Any]):
        """增强的依赖安装"""
        try:
            logger.info(f"📦 开始安装依赖: {project_type}")
            
            # 获取安装命令
            install_commands = self.runtime_detector.get_install_commands(project_path, self.runtime_detector.ProjectType(project_type))
            
            if not install_commands:
                logger.info("ℹ️ 无需安装依赖")
                return
            
            # 执行安装命令
            for i, cmd in enumerate(install_commands):
                try:
                    logger.info(f"🔧 执行安装命令 {i+1}/{len(install_commands)}: {' '.join(cmd)}")
                    
                    result = await asyncio.create_subprocess_exec(
                        *cmd,
                        cwd=project_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    
                    stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=300)
                    
                    if result.returncode == 0:
                        logger.info(f"✅ 安装命令执行成功: {' '.join(cmd)}")
                        return  # 成功就不执行后续命令
                    else:
                        logger.warning(f"⚠️ 安装命令失败: {stderr.decode()}")
                        
                except asyncio.TimeoutError:
                    logger.error(f"❌ 安装命令超时: {' '.join(cmd)}")
                except Exception as e:
                    logger.error(f"❌ 安装命令异常: {e}")
            
            # 如果所有命令都失败
            raise create_dependency_error(
                project_type,
                ' '.join(install_commands[0]) if install_commands else "unknown",
                "所有安装命令都失败"
            )
            
        except Exception as e:
            logger.error(f"❌ 依赖安装失败: {e}")
            raise e
    
    async def _start_server_enhanced(self, project_path: Path, project_type: str, entry_point: str, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """增强的服务器启动"""
        allocated_port = None
        process = None
        
        try:
            # 1. 分配端口
            allocated_port = self._allocate_port_enhanced()
            logger.info(f"🔌 分配端口: {allocated_port}")
            
            # 2. 构建启动命令
            cmd, env = self._build_startup_command_enhanced(project_path, project_type, entry_point, allocated_port, candidate)
            logger.info(f"🚀 启动命令: {' '.join(cmd)}")
            
            # 3. 启动进程
            process = await self._start_process_with_retry(cmd, project_path, env)
            
            # 4. 等待服务就绪
            if not await self._wait_for_service_ready(allocated_port, max_wait_time=30):
                raise ServerStartupError(
                    f"服务启动超时，端口: {allocated_port}",
                    server_id=candidate.get('id'),
                    startup_command=' '.join(cmd)
                )
            
            # 5. 记录运行信息
            server_info = {
                "id": candidate.get('id', f"server_{allocated_port}"),
                "name": candidate.get('name', 'Unknown Server'),
                "port": allocated_port,
                "host": "localhost",
                "pid": process.pid,
                "project_path": str(project_path),
                "project_type": project_type,
                "entry_point": entry_point,
                "startup_command": ' '.join(cmd),
                "status": "running",
                "started_at": datetime.now().isoformat()
            }
            
            # 保存到运行中的服务器列表
            self.running_servers[server_info["id"]] = {
                **server_info,
                "process": process
            }
            
            logger.info(f"✅ 服务器启动成功: {server_info['id']}")
            return server_info
            
        except Exception as e:
            # 清理资源
            if process:
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except:
                    pass
            
            if allocated_port:
                self.used_ports.discard(allocated_port)
            
            raise e
    
    def _allocate_port_enhanced(self) -> int:
        """增强的端口分配"""
        try:
            return super()._allocate_port()
        except Exception as e:
            # 如果原始方法失败，抛出更详细的错误
            attempted_ports = list(range(self.port_range_start, self.port_range_end + 1))
            raise PortAllocationError(
                f"端口分配失败: {e}",
                port_range=f"{self.port_range_start}-{self.port_range_end}",
                attempted_ports=attempted_ports
            )
    
    def _build_startup_command_enhanced(self, project_path: Path, project_type: str, entry_point: str, port: int, candidate: Dict[str, Any]) -> Tuple[List[str], Dict[str, str]]:
        """构建增强的启动命令"""
        env = dict(os.environ)
        env["PORT"] = str(port)
        
        # 添加自定义环境变量
        if 'env' in candidate:
            env.update(candidate['env'])
        
        # 根据项目类型构建命令
        if project_type == "python":
            if entry_point.endswith('.py'):
                cmd = ["python3", str(project_path / entry_point)]
            else:
                cmd = ["python3", "-m", entry_point]
        
        elif project_type in ["nodejs", "typescript"]:
            if entry_point == "npm start":
                cmd = ["npm", "start"]
            elif entry_point.endswith('.ts'):
                cmd = ["npx", "ts-node", str(project_path / entry_point)]
            else:
                cmd = ["node", str(project_path / entry_point)]
        
        else:
            # 回退到通用命令
            startup_template = self.runtime_detector.get_startup_command_template(
                self.runtime_detector.ProjectType(project_type)
            )
            if startup_template:
                cmd = startup_template + [str(project_path / entry_point)]
            else:
                raise ServerStartupError(f"不支持的项目类型: {project_type}")
        
        # 添加自定义参数
        if 'args' in candidate:
            cmd.extend(candidate['args'])
        
        return cmd, env
    
    async def _start_process_with_retry(self, cmd: List[str], cwd: Path, env: Dict[str, str]) -> asyncio.subprocess.Process:
        """带重试的进程启动"""
        for attempt in range(self.max_startup_retries):
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=cwd,
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                # 等待一小段时间检查进程是否立即退出
                await asyncio.sleep(1.0)
                
                if process.returncode is None:
                    # 进程仍在运行
                    return process
                else:
                    # 进程已退出
                    stdout, stderr = await process.communicate()
                    error_output = stderr.decode() if stderr else "进程立即退出"
                    logger.warning(f"⚠️ 进程启动失败 (尝试 {attempt + 1}): {error_output}")
                    
                    if attempt < self.max_startup_retries - 1:
                        await asyncio.sleep(2.0)  # 等待后重试
                    else:
                        raise create_startup_error("unknown", ' '.join(cmd), error_output)
                        
            except Exception as e:
                logger.error(f"❌ 进程启动异常 (尝试 {attempt + 1}): {e}")
                if attempt == self.max_startup_retries - 1:
                    raise create_startup_error("unknown", ' '.join(cmd), str(e))
                await asyncio.sleep(2.0)
        
        raise create_startup_error("unknown", ' '.join(cmd), "所有启动尝试都失败")
    
    async def _safe_clone_repository(self, candidate: Dict[str, Any]) -> Optional[Path]:
        """安全的仓库克隆"""
        try:
            # 检查多种可能的URL字段
            github_url = candidate.get('github_url') or candidate.get('repo_url') or candidate.get('url', '')
            server_id = candidate.get('id', 'unknown')
            
            if not github_url:
                logger.warning(f"⚠️ 服务器 {server_id} 缺少GitHub URL，跳过克隆步骤")
                # 检查是否是本地已存在的服务器
                local_path = candidate.get('local_path')
                if local_path and Path(local_path).exists():
                    logger.info(f"✅ 使用本地路径: {local_path}")
                    return Path(local_path)
                return None
            
            temp_dir = Path(tempfile.mkdtemp(prefix="mcp_server_"))
            logger.info(f"📁 创建临时目录: {temp_dir}")
            
            # 克隆仓库
            clone_cmd = ["git", "clone", github_url, str(temp_dir)]
            
            process = await asyncio.create_subprocess_exec(
                *clone_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
            
            if process.returncode == 0:
                logger.info(f"✅ 仓库克隆成功: {github_url}")
                return temp_dir
            else:
                error_msg = stderr.decode() if stderr else "未知错误"
                logger.error(f"❌ 仓库克隆失败: {error_msg}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None
                
        except asyncio.TimeoutError:
            logger.error("❌ 仓库克隆超时")
            return None
        except Exception as e:
            logger.error(f"❌ 仓库克隆异常: {e}")
            return None
    
    def _record_error(self, server_id: str, error_msg: str, attempt: int):
        """记录错误历史"""
        error_record = {
            "server_id": server_id,
            "error_msg": error_msg,
            "attempt": attempt,
            "timestamp": datetime.now().isoformat()
        }
        
        self.error_history.append(error_record)
        
        # 保持错误历史的大小限制
        if len(self.error_history) > self.max_error_history:
            self.error_history = self.error_history[-self.max_error_history:]
    
    def _get_error_history(self, server_id: str = None) -> List[Dict[str, Any]]:
        """获取错误历史"""
        if server_id:
            return [error for error in self.error_history if error["server_id"] == server_id]
        return self.error_history.copy()
    
    def get_installation_stats(self) -> Dict[str, Any]:
        """获取安装统计信息"""
        stats = self.installation_stats.copy()
        stats["success_rate"] = (
            stats["successful_installs"] / max(stats["total_attempts"], 1) * 100
        )
        stats["error_count"] = len(self.error_history)
        return stats
    
    def clear_error_history(self):
        """清理错误历史"""
        self.error_history.clear()
        logger.info("🧹 已清理错误历史")
    
    # 保持与原有ProcessRunner的兼容性
    async def install_server(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """
        原有的install_server方法，现在调用增强版本
        保持向后兼容性
        """
        logger.info("🔄 使用增强的安装方法")
        return await self.install_server_with_enhanced_detection(candidate)