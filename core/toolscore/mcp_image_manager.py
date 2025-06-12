"""
MCP Docker镜像管理器
实现本地持久化缓存，确保MCP服务器镜像下载后永久保存
"""

import asyncio
import logging
import os
import hashlib
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
import docker
import aiofiles
import tarfile

from .interfaces import MCPServerSpec
from .dynamic_mcp_manager import MCPServerCandidate

logger = logging.getLogger(__name__)

class MCPImageManager:
    """MCP Docker镜像管理器 - 实现本地持久化缓存"""
    
    def __init__(self, cache_directory: str = "/app/mcp_images"):
        self.cache_directory = Path(cache_directory)
        self.docker_client = docker.from_env()
        self.image_registry = {}  # 镜像注册表
        self.cache_index_file = self.cache_directory / "image_index.json"
        
        # 确保缓存目录存在
        self.cache_directory.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"MCP镜像管理器初始化完成，缓存目录: {self.cache_directory}")
    
    async def initialize(self):
        """初始化镜像管理器，加载现有缓存索引"""
        try:
            await self._load_cache_index()
            await self._verify_cached_images()
            logger.info(f"发现 {len(self.image_registry)} 个已缓存的MCP镜像")
        except Exception as e:
            logger.error(f"初始化镜像管理器失败: {e}")
    
    async def _load_cache_index(self):
        """加载缓存索引文件"""
        if self.cache_index_file.exists():
            try:
                async with aiofiles.open(self.cache_index_file, 'r') as f:
                    content = await f.read()
                    self.image_registry = json.loads(content)
            except Exception as e:
                logger.warning(f"加载缓存索引失败: {e}")
                self.image_registry = {}
        else:
            self.image_registry = {}
    
    async def _save_cache_index(self):
        """保存缓存索引文件"""
        try:
            async with aiofiles.open(self.cache_index_file, 'w') as f:
                await f.write(json.dumps(self.image_registry, indent=2))
        except Exception as e:
            logger.error(f"保存缓存索引失败: {e}")
    
    async def _verify_cached_images(self):
        """验证已缓存的镜像是否仍然存在"""
        invalid_entries = []
        
        for image_key, image_info in self.image_registry.items():
            cache_path = Path(image_info["cache_path"])
            if not cache_path.exists():
                logger.warning(f"缓存文件不存在，移除索引项: {image_key}")
                invalid_entries.append(image_key)
        
        # 移除无效项
        for key in invalid_entries:
            del self.image_registry[key]
        
        if invalid_entries:
            await self._save_cache_index()
    
    def _generate_image_key(self, candidate: MCPServerCandidate) -> str:
        """为候选者生成唯一的镜像键"""
        # 使用仓库URL和名称生成唯一键
        key_content = f"{candidate.github_url}:{candidate.name}:{candidate.install_method}"
        return hashlib.md5(key_content.encode()).hexdigest()
    
    def _generate_image_name(self, candidate: MCPServerCandidate) -> str:
        """生成标准化的镜像名称"""
        safe_name = candidate.name.lower().replace(' ', '-').replace('_', '-')
        # 移除特殊字符
        safe_name = ''.join(c for c in safe_name if c.isalnum() or c == '-')
        return f"mcp-{safe_name}"
    
    async def check_cached_image(self, candidate: MCPServerCandidate) -> Optional[str]:
        """检查是否已缓存指定候选者的镜像"""
        image_key = self._generate_image_key(candidate)
        
        if image_key in self.image_registry:
            image_info = self.image_registry[image_key]
            cache_path = Path(image_info["cache_path"])
            
            if cache_path.exists():
                logger.info(f"找到已缓存的镜像: {candidate.name}")
                return image_info["image_id"]
            else:
                # 缓存文件不存在，移除索引
                del self.image_registry[image_key]
                await self._save_cache_index()
        
        return None
    
    async def cache_mcp_image(self, candidate: MCPServerCandidate) -> str:
        """下载并缓存MCP服务器镜像到本地"""
        image_key = self._generate_image_key(candidate)
        
        # 检查是否已缓存
        cached_image_id = await self.check_cached_image(candidate)
        if cached_image_id:
            return await self._load_cached_image(image_key)
        
        logger.info(f"开始缓存MCP镜像: {candidate.name}")
        
        try:
            # 构建新镜像
            image_name = self._generate_image_name(candidate)
            built_image = await self._build_mcp_image(candidate, image_name)
            
            # 保存镜像到本地缓存
            cache_path = await self._save_image_to_cache(built_image, image_key, candidate)
            
            # 更新镜像注册表
            self.image_registry[image_key] = {
                "candidate_name": candidate.name,
                "github_url": candidate.github_url,
                "image_id": built_image.id,
                "image_name": image_name,
                "cache_path": str(cache_path),
                "install_method": candidate.install_method,
                "cached_at": asyncio.get_event_loop().time(),
                "tags": candidate.tags
            }
            
            await self._save_cache_index()
            
            logger.info(f"镜像缓存完成: {candidate.name} -> {cache_path}")
            return built_image.id
            
        except Exception as e:
            logger.error(f"缓存MCP镜像失败: {candidate.name} - {e}")
            raise
    
    async def _build_mcp_image(self, candidate: MCPServerCandidate, image_name: str):
        """构建MCP镜像"""
        # 这里需要根据不同的安装方法构建镜像
        if candidate.install_method == "docker":
            return await self._build_docker_image(candidate, image_name)
        elif candidate.install_method == "docker_hub":
            return await self._pull_docker_hub_image(candidate, image_name)
        else:
            raise ValueError(f"不支持的安装方法: {candidate.install_method}")
    
    async def _build_docker_image(self, candidate: MCPServerCandidate, image_name: str):
        """从源码构建Docker镜像"""
        import tempfile
        import subprocess
        import aiohttp
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # 下载源码
            if candidate.github_url.endswith('.git'):
                repo_url = candidate.github_url
            else:
                repo_url = f"{candidate.github_url}.git"
            
            # 克隆仓库
            clone_cmd = ["git", "clone", repo_url, temp_dir]
            result = subprocess.run(clone_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"Git克隆失败: {result.stderr}")
            
            # 检查Dockerfile是否存在
            dockerfile_path = Path(temp_dir) / "Dockerfile"
            if not dockerfile_path.exists():
                # 如果没有Dockerfile，尝试生成一个基础的
                await self._generate_dockerfile(Path(temp_dir), candidate)
            
            # 构建镜像
            logger.info(f"构建Docker镜像: {image_name}")
            image, logs = self.docker_client.images.build(
                path=temp_dir,
                tag=image_name,
                rm=True,
                forcerm=True
            )
            
            return image
    
    async def _pull_docker_hub_image(self, candidate: MCPServerCandidate, image_name: str):
        """从Docker Hub拉取镜像"""
        # 从URL中提取镜像名称
        if "/docker.io/" in candidate.github_url or "hub.docker.com" in candidate.github_url:
            # 解析Docker Hub URL
            parts = candidate.github_url.split('/')
            docker_image = f"{parts[-2]}/{parts[-1]}"
        else:
            docker_image = candidate.github_url.split('/')[-1]
        
        logger.info(f"拉取Docker Hub镜像: {docker_image}")
        image = self.docker_client.images.pull(docker_image)
        
        # 重新标记镜像
        image.tag(image_name, "latest")
        
        return image
    
    async def _generate_dockerfile(self, build_dir: Path, candidate: MCPServerCandidate):
        """为没有Dockerfile的仓库生成基础Dockerfile"""
        dockerfile_content = f"""
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \\
    git \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# 复制源码
COPY . .

# 安装Python依赖
RUN if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
RUN if [ -f package.json ]; then npm install; fi

# 设置环境变量
ENV MCP_SERVER_NAME="{candidate.name}"
ENV MCP_SERVER_PORT=8080

# 暴露端口
EXPOSE 8080

# 启动命令 - 这需要根据具体的MCP服务器调整
CMD ["python", "-m", "src.main"]
"""
        
        dockerfile_path = build_dir / "Dockerfile"
        async with aiofiles.open(dockerfile_path, 'w') as f:
            await f.write(dockerfile_content.strip())
        
        logger.info(f"生成Dockerfile: {dockerfile_path}")
    
    async def _save_image_to_cache(self, image, image_key: str, candidate: MCPServerCandidate) -> Path:
        """保存Docker镜像到本地文件"""
        cache_filename = f"{image_key}.tar"
        cache_path = self.cache_directory / cache_filename
        
        logger.info(f"保存镜像到缓存: {cache_path}")
        
        # 使用Docker API保存镜像
        image_data = image.save()
        
        # 异步写入文件
        async with aiofiles.open(cache_path, 'wb') as f:
            for chunk in image_data:
                await f.write(chunk)
        
        return cache_path
    
    async def _load_cached_image(self, image_key: str) -> str:
        """从缓存加载Docker镜像"""
        if image_key not in self.image_registry:
            raise ValueError(f"镜像键不存在: {image_key}")
        
        image_info = self.image_registry[image_key]
        cache_path = Path(image_info["cache_path"])
        
        if not cache_path.exists():
            raise FileNotFoundError(f"缓存文件不存在: {cache_path}")
        
        logger.info(f"从缓存加载镜像: {cache_path}")
        
        # 加载镜像
        with open(cache_path, 'rb') as f:
            images = self.docker_client.images.load(f.read())
        
        # 为镜像添加标签
        for image in images:
            image.tag(image_info["image_name"], "latest")
            return image.id
        
        raise Exception("无法从缓存加载镜像")
    
    async def remove_cached_image(self, candidate: MCPServerCandidate) -> bool:
        """移除缓存的镜像"""
        image_key = self._generate_image_key(candidate)
        
        if image_key not in self.image_registry:
            logger.warning(f"要移除的镜像不在缓存中: {candidate.name}")
            return False
        
        image_info = self.image_registry[image_key]
        cache_path = Path(image_info["cache_path"])
        
        try:
            # 删除缓存文件
            if cache_path.exists():
                cache_path.unlink()
            
            # 尝试移除Docker镜像
            try:
                self.docker_client.images.remove(image_info["image_id"], force=True)
            except Exception as e:
                logger.warning(f"移除Docker镜像失败: {e}")
            
            # 从注册表移除
            del self.image_registry[image_key]
            await self._save_cache_index()
            
            logger.info(f"已移除缓存镜像: {candidate.name}")
            return True
            
        except Exception as e:
            logger.error(f"移除缓存镜像失败: {e}")
            return False
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total_size = 0
        image_count = len(self.image_registry)
        
        for image_info in self.image_registry.values():
            cache_path = Path(image_info["cache_path"])
            if cache_path.exists():
                total_size += cache_path.stat().st_size
        
        return {
            "total_images": image_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "cache_directory": str(self.cache_directory),
            "images": list(self.image_registry.values())
        }
    
    async def cleanup_orphaned_cache(self):
        """清理孤立的缓存文件"""
        if not self.cache_directory.exists():
            return
        
        # 获取注册表中的所有缓存文件
        registered_files = set()
        for image_info in self.image_registry.values():
            registered_files.add(Path(image_info["cache_path"]).name)
        
        # 扫描缓存目录，找到未注册的文件
        orphaned_files = []
        for file_path in self.cache_directory.glob("*.tar"):
            if file_path.name not in registered_files:
                orphaned_files.append(file_path)
        
        # 删除孤立文件
        for file_path in orphaned_files:
            try:
                file_path.unlink()
                logger.info(f"删除孤立缓存文件: {file_path}")
            except Exception as e:
                logger.error(f"删除孤立文件失败: {file_path} - {e}")
        
        logger.info(f"清理完成，删除了 {len(orphaned_files)} 个孤立文件")
    
    async def cleanup(self):
        """清理资源"""
        try:
            await self._save_cache_index()
            self.docker_client.close()
            logger.info("MCP镜像管理器清理完成")
        except Exception as e:
            logger.error(f"清理镜像管理器失败: {e}") 