"""
轻量级服务安装器
实现智能、高效的MCP服务安装机制
"""

import asyncio
import json
import logging
import shutil
import tempfile
try:
    import aiohttp
except ImportError:
    aiohttp = None
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from .models import ServiceConfig, ServiceType, InstallMethod, InstallationResult, ServiceCapability

logger = logging.getLogger(__name__)


class LightweightInstaller:
    """轻量级服务安装器"""
    
    def __init__(self, install_base_dir: str = "installed_services"):
        self.install_base_dir = Path(install_base_dir)
        self.install_base_dir.mkdir(exist_ok=True)
        
        # 支持的安装方法
        self.installers = {
            InstallMethod.CONFIG_ONLY: self._install_config_only,
            InstallMethod.LIGHTWEIGHT: self._install_lightweight,
            InstallMethod.FULL_CLONE: self._install_full_clone,
            InstallMethod.DOCKER_PULL: self._install_docker
        }
    
    async def install_service(self, service_spec: Dict[str, Any]) -> InstallationResult:
        """安装服务的主入口"""
        start_time = datetime.now()
        
        try:
            # 解析服务规格
            service_config = await self._parse_service_spec(service_spec)
            
            # 检查是否已安装
            if await self._is_already_installed(service_config):
                existing_config = await self._load_existing_config(service_config)
                if existing_config:
                    logger.info(f"✅ 服务已安装: {service_config.name}")
                    return InstallationResult(
                        success=True,
                        service_config=existing_config,
                        details={"status": "already_installed"}
                    )
            
            # 选择并执行安装方法
            installer = self.installers.get(service_config.install_method)
            if not installer:
                return InstallationResult(
                    success=False,
                    error_message=f"不支持的安装方法: {service_config.install_method}"
                )
            
            logger.info(f"🚀 开始安装服务: {service_config.name} (方法: {service_config.install_method.value})")
            
            result = await installer(service_config)
            
            if result.success:
                # 保存安装配置
                await self._save_installation_config(result.service_config)
                
                install_time = (datetime.now() - start_time).total_seconds()
                result.installation_time_seconds = install_time
                
                logger.info(f"✅ 服务安装成功: {service_config.name} (耗时: {install_time:.1f}s)")
            else:
                logger.error(f"❌ 服务安装失败: {service_config.name} - {result.error_message}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 安装服务异常: {e}")
            return InstallationResult(
                success=False,
                error_message=f"安装异常: {str(e)}"
            )
    
    async def _parse_service_spec(self, service_spec: Dict[str, Any]) -> ServiceConfig:
        """解析服务规格为标准配置"""
        # 基础信息
        service_config = ServiceConfig(
            service_id=service_spec.get("id", service_spec.get("service_id", "unknown")),
            name=service_spec.get("name", "Unknown Service"),
            description=service_spec.get("description", ""),
            version=service_spec.get("version", "1.0.0"),
            service_type=ServiceType.EXTERNAL
        )
        
        # 安装方法判断
        if "docker_image" in service_spec:
            service_config.install_method = InstallMethod.DOCKER_PULL
            service_config.docker_image = service_spec["docker_image"]
        elif "github_url" in service_spec:
            # 根据配置决定轻量级还是完整克隆
            if service_spec.get("lightweight", True):
                service_config.install_method = InstallMethod.LIGHTWEIGHT
            else:
                service_config.install_method = InstallMethod.FULL_CLONE
            service_config.github_url = service_spec["github_url"]
            service_config.source_url = service_spec["github_url"]
        elif "config_url" in service_spec:
            service_config.install_method = InstallMethod.CONFIG_ONLY
            service_config.source_url = service_spec["config_url"]
        else:
            service_config.install_method = InstallMethod.CONFIG_ONLY
        
        # 其他配置
        service_config.entry_point = service_spec.get("entry_point")
        service_config.host = service_spec.get("host", "localhost")
        service_config.port = service_spec.get("port")
        service_config.tags = service_spec.get("tags", [])
        service_config.author = service_spec.get("author")
        service_config.license = service_spec.get("license")
        service_config.documentation_url = service_spec.get("documentation_url")
        
        # 解析能力
        if "capabilities" in service_spec:
            service_config.capabilities = [
                ServiceCapability(
                    name=cap.get("name"),
                    description=cap.get("description", ""),
                    parameters=cap.get("parameters", {}),
                    required_params=cap.get("required_params", []),
                    optional_params=cap.get("optional_params", []),
                    examples=cap.get("examples", [])
                )
                for cap in service_spec["capabilities"]
            ]
        
        return service_config
    
    async def _install_config_only(self, service_config: ServiceConfig) -> InstallationResult:
        """仅配置安装 - 最轻量级的安装方式"""
        try:
            install_dir = self.install_base_dir / service_config.service_id
            install_dir.mkdir(exist_ok=True)
            
            # 如果有配置URL，下载配置文件
            if service_config.source_url:
                config_content = await self._download_config(service_config.source_url)
                if config_content:
                    config_file = install_dir / "service_config.json"
                    with open(config_file, 'w', encoding='utf-8') as f:
                        json.dump(config_content, f, indent=2, ensure_ascii=False)
            
            # 更新服务配置
            service_config.local_path = str(install_dir)
            service_config.created_at = datetime.now()
            
            return InstallationResult(
                success=True,
                service_config=service_config,
                install_path=str(install_dir),
                details={"method": "config_only", "files_downloaded": 1}
            )
            
        except Exception as e:
            return InstallationResult(
                success=False,
                error_message=f"配置安装失败: {str(e)}"
            )
    
    async def _install_lightweight(self, service_config: ServiceConfig) -> InstallationResult:
        """轻量级安装 - 只下载必要文件"""
        try:
            install_dir = self.install_base_dir / service_config.service_id
            install_dir.mkdir(exist_ok=True)
            
            # 解析GitHub URL获取仓库信息
            repo_info = self._parse_github_url(service_config.github_url)
            if not repo_info:
                return InstallationResult(
                    success=False,
                    error_message="无效的GitHub URL"
                )
            
            # 下载必要文件
            files_downloaded = await self._download_essential_files(repo_info, install_dir, service_config)
            
            if files_downloaded == 0:
                return InstallationResult(
                    success=False,
                    error_message="未能下载任何必要文件"
                )
            
            # 更新服务配置
            service_config.local_path = str(install_dir)
            service_config.created_at = datetime.now()
            
            return InstallationResult(
                success=True,
                service_config=service_config,
                install_path=str(install_dir),
                details={
                    "method": "lightweight", 
                    "files_downloaded": files_downloaded,
                    "repo": repo_info
                }
            )
            
        except Exception as e:
            return InstallationResult(
                success=False,
                error_message=f"轻量级安装失败: {str(e)}"
            )
    
    async def _install_full_clone(self, service_config: ServiceConfig) -> InstallationResult:
        """完整克隆安装 - 传统的克隆方式"""
        try:
            install_dir = self.install_base_dir / service_config.service_id
            
            # 使用git克隆
            clone_cmd = [
                "git", "clone", 
                service_config.github_url, 
                str(install_dir)
            ]
            
            process = await asyncio.create_subprocess_exec(
                *clone_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "未知克隆错误"
                return InstallationResult(
                    success=False,
                    error_message=f"Git克隆失败: {error_msg}"
                )
            
            # 更新服务配置
            service_config.local_path = str(install_dir)
            service_config.created_at = datetime.now()
            
            return InstallationResult(
                success=True,
                service_config=service_config,
                install_path=str(install_dir),
                details={"method": "full_clone", "repo_size": self._get_dir_size(install_dir)}
            )
            
        except asyncio.TimeoutError:
            return InstallationResult(
                success=False,
                error_message="Git克隆超时"
            )
        except Exception as e:
            return InstallationResult(
                success=False,
                error_message=f"完整克隆失败: {str(e)}"
            )
    
    async def _install_docker(self, service_config: ServiceConfig) -> InstallationResult:
        """Docker安装"""
        try:
            # 检查Docker可用性
            docker_check = await asyncio.create_subprocess_exec(
                "docker", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await docker_check.communicate()
            
            if docker_check.returncode != 0:
                return InstallationResult(
                    success=False,
                    error_message="Docker不可用"
                )
            
            # 拉取镜像
            pull_cmd = ["docker", "pull", service_config.docker_image]
            
            process = await asyncio.create_subprocess_exec(
                *pull_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "未知拉取错误"
                return InstallationResult(
                    success=False,
                    error_message=f"Docker镜像拉取失败: {error_msg}"
                )
            
            # 创建配置目录
            install_dir = self.install_base_dir / service_config.service_id
            install_dir.mkdir(exist_ok=True)
            
            service_config.local_path = str(install_dir)
            service_config.created_at = datetime.now()
            
            return InstallationResult(
                success=True,
                service_config=service_config,
                install_path=str(install_dir),
                details={"method": "docker", "image": service_config.docker_image}
            )
            
        except asyncio.TimeoutError:
            return InstallationResult(
                success=False,
                error_message="Docker镜像拉取超时"
            )
        except Exception as e:
            return InstallationResult(
                success=False,
                error_message=f"Docker安装失败: {str(e)}"
            )
    
    def _parse_github_url(self, github_url: str) -> Optional[Dict[str, str]]:
        """解析GitHub URL"""
        try:
            # 支持 https://github.com/owner/repo 格式
            if github_url.startswith("https://github.com/"):
                parts = github_url.replace("https://github.com/", "").strip("/").split("/")
                if len(parts) >= 2:
                    return {
                        "owner": parts[0],
                        "repo": parts[1],
                        "base_url": f"https://api.github.com/repos/{parts[0]}/{parts[1]}"
                    }
            return None
        except Exception:
            return None
    
    async def _download_essential_files(self, repo_info: Dict[str, str], install_dir: Path, service_config: ServiceConfig) -> int:
        """下载必要文件"""
        files_downloaded = 0
        essential_files = [
            "package.json",
            "pyproject.toml", 
            "requirements.txt",
            "Cargo.toml",
            "go.mod",
            "README.md",
            "mcp.json",
            "service.json"
        ]
        
        # 如果指定了入口点，也要下载
        if service_config.entry_point:
            essential_files.append(service_config.entry_point)
        
        if not aiohttp:
            logger.error("aiohttp not available for downloading files")
            return 0
            
        async with aiohttp.ClientSession() as session:
            for file_name in essential_files:
                try:
                    file_url = f"{repo_info['base_url']}/contents/{file_name}"
                    async with session.get(file_url) as response:
                        if response.status == 200:
                            content_data = await response.json()
                            if content_data.get("type") == "file":
                                # 解码base64内容
                                import base64
                                file_content = base64.b64decode(content_data["content"]).decode("utf-8")
                                
                                # 保存文件
                                file_path = install_dir / file_name
                                with open(file_path, 'w', encoding='utf-8') as f:
                                    f.write(file_content)
                                
                                files_downloaded += 1
                                logger.debug(f"📥 下载文件: {file_name}")
                
                except Exception as e:
                    logger.debug(f"⏭️ 跳过文件 {file_name}: {e}")
        
        return files_downloaded
    
    async def _download_config(self, config_url: str) -> Optional[Dict[str, Any]]:
        """下载配置文件"""
        try:
            if not aiohttp:
                logger.error("aiohttp not available for downloading config")
                return None
            
            async with aiohttp.ClientSession() as session:
                async with session.get(config_url) as response:
                    if response.status == 200:
                        return await response.json()
            return None
        except Exception as e:
            logger.error(f"❌ 下载配置失败: {e}")
            return None
    
    async def _is_already_installed(self, service_config: ServiceConfig) -> bool:
        """检查服务是否已安装"""
        install_dir = self.install_base_dir / service_config.service_id
        config_file = install_dir / "installation_config.json"
        return config_file.exists()
    
    async def _load_existing_config(self, service_config: ServiceConfig) -> Optional[ServiceConfig]:
        """加载已安装的服务配置"""
        try:
            install_dir = self.install_base_dir / service_config.service_id
            config_file = install_dir / "installation_config.json"
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # 重新构建ServiceConfig对象
            existing_config = ServiceConfig(**config_data)
            return existing_config
            
        except Exception as e:
            logger.error(f"❌ 加载已安装配置失败: {e}")
            return None
    
    async def _save_installation_config(self, service_config: ServiceConfig) -> None:
        """保存安装配置"""
        try:
            install_dir = Path(service_config.local_path)
            config_file = install_dir / "installation_config.json"
            
            # 转换为可序列化的字典
            config_data = service_config.to_dict()
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"❌ 保存安装配置失败: {e}")
    
    def _get_dir_size(self, dir_path: Path) -> int:
        """计算目录大小"""
        try:
            total_size = 0
            for file_path in dir_path.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
            return total_size
        except Exception:
            return 0
    
    async def uninstall_service(self, service_id: str) -> bool:
        """卸载服务"""
        try:
            install_dir = self.install_base_dir / service_id
            
            if install_dir.exists():
                shutil.rmtree(install_dir)
                logger.info(f"✅ 服务卸载成功: {service_id}")
                return True
            else:
                logger.warning(f"⚠️ 服务未安装: {service_id}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 服务卸载失败: {service_id} - {e}")
            return False
    
    def list_installed_services(self) -> List[str]:
        """列出已安装的服务"""
        try:
            return [
                dir_name for dir_name in self.install_base_dir.iterdir()
                if dir_name.is_dir() and (dir_name / "installation_config.json").exists()
            ]
        except Exception:
            return []