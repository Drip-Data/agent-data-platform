"""
多语言运行时检测器
支持Python、Node.js、TypeScript、Rust、Go等多种项目类型的智能检测
"""

import json
import subprocess
import shutil
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import logging

from ..exceptions import ProjectTypeDetectionError

logger = logging.getLogger(__name__)


class ProjectType(Enum):
    """支持的项目类型"""
    PYTHON = "python"
    NODEJS = "nodejs"
    TYPESCRIPT = "typescript"
    RUST = "rust"
    GO = "go"
    UNKNOWN = "unknown"


class RuntimeDetector:
    """多语言项目运行时环境检测器"""
    
    # 项目类型检测规则（文件指示器及其权重）
    DETECTION_RULES = {
        ProjectType.PYTHON: {
            "requirements.txt": 10,
            "pyproject.toml": 15,
            "setup.py": 12,
            "setup.cfg": 8,
            "Pipfile": 10,
            "poetry.lock": 12,
            "conda.yaml": 8,
            "environment.yml": 8,
            "*.py": 5
        },
        ProjectType.NODEJS: {
            "package.json": 15,
            "yarn.lock": 10,
            "package-lock.json": 10,
            "pnpm-lock.yaml": 10,
            "node_modules": 8,
            "*.js": 5,
            "*.mjs": 5
        },
        ProjectType.TYPESCRIPT: {
            "tsconfig.json": 15,
            "*.ts": 10,
            "*.tsx": 8,
            "package.json": 5  # 可能是TypeScript项目
        },
        ProjectType.RUST: {
            "Cargo.toml": 15,
            "Cargo.lock": 10,
            "src/main.rs": 12,
            "src/lib.rs": 10,
            "*.rs": 5
        },
        ProjectType.GO: {
            "go.mod": 15,
            "go.sum": 10,
            "main.go": 12,
            "*.go": 5
        }
    }
    
    # 依赖管理器检测
    PACKAGE_MANAGERS = {
        ProjectType.PYTHON: {
            "pip": {"command": ["pip", "--version"], "install_templates": ["pip install -r requirements.txt", "pip install -e ."]},
            "poetry": {"command": ["poetry", "--version"], "install_templates": ["poetry install"]},
            "pipenv": {"command": ["pipenv", "--version"], "install_templates": ["pipenv install"]},
            "conda": {"command": ["conda", "--version"], "install_templates": ["conda env create -f environment.yml"]}
        },
        ProjectType.NODEJS: {
            "npm": {"command": ["npm", "--version"], "install_templates": ["npm install"]},
            "yarn": {"command": ["yarn", "--version"], "install_templates": ["yarn install"]},
            "pnpm": {"command": ["pnpm", "--version"], "install_templates": ["pnpm install"]}
        },
        ProjectType.TYPESCRIPT: {
            "npm": {"command": ["npm", "--version"], "install_templates": ["npm install", "npx tsc"]},
            "yarn": {"command": ["yarn", "--version"], "install_templates": ["yarn install", "yarn build"]},
            "pnpm": {"command": ["pnpm", "--version"], "install_templates": ["pnpm install", "pnpm build"]}
        },
        ProjectType.RUST: {
            "cargo": {"command": ["cargo", "--version"], "install_templates": ["cargo build --release"]}
        },
        ProjectType.GO: {
            "go": {"command": ["go", "version"], "install_templates": ["go mod download", "go build"]}
        }
    }
    
    def __init__(self):
        self.cache = {}  # 缓存检测结果
        
    def detect_project_type(self, project_path: Path) -> ProjectType:
        """
        智能检测项目类型
        使用多重指标和评分机制
        
        Args:
            project_path: 项目路径
            
        Returns:
            检测到的项目类型
            
        Raises:
            ProjectTypeDetectionError: 检测失败时抛出
        """
        try:
            # 检查缓存
            cache_key = str(project_path.resolve())
            if cache_key in self.cache:
                logger.debug(f"🔄 使用缓存的项目类型: {self.cache[cache_key]}")
                return self.cache[cache_key]
            
            if not project_path.exists():
                raise ProjectTypeDetectionError(f"项目路径不存在: {project_path}")
            
            # 计算每种类型的匹配分数
            scores = self._calculate_type_scores(project_path)
            
            # 特殊处理：TypeScript可能被识别为Node.js
            scores = self._handle_typescript_detection(project_path, scores)
            
            # 选择得分最高的类型
            if not scores or max(scores.values()) == 0:
                detected_type = ProjectType.UNKNOWN
                logger.warning(f"⚠️ 无法确定项目类型: {project_path}")
            else:
                detected_type = max(scores, key=scores.get)
                logger.info(f"✅ 检测到项目类型: {detected_type.value} (得分: {scores[detected_type]})")
                
                # 记录详细的检测信息
                self._log_detection_details(project_path, scores, detected_type)
            
            # 缓存结果
            self.cache[cache_key] = detected_type
            return detected_type
            
        except Exception as e:
            logger.error(f"❌ 项目类型检测失败: {e}")
            raise ProjectTypeDetectionError(f"项目类型检测失败: {e}", project_path=str(project_path))
    
    def _calculate_type_scores(self, project_path: Path) -> Dict[ProjectType, int]:
        """计算各项目类型的匹配分数"""
        scores = {ptype: 0 for ptype in ProjectType if ptype != ProjectType.UNKNOWN}
        
        for project_type, indicators in self.DETECTION_RULES.items():
            if project_type == ProjectType.UNKNOWN:
                continue
                
            for indicator, weight in indicators.items():
                if self._check_indicator(project_path, indicator):
                    scores[project_type] += weight
                    logger.debug(f"✓ {project_type.value}: 找到 {indicator} (+{weight}分)")
        
        return scores
    
    def _check_indicator(self, project_path: Path, indicator: str) -> bool:
        """检查项目中是否存在指定的指示器"""
        if indicator.startswith("*."):
            # 检查文件扩展名
            extension = indicator[1:]  # 去掉 *
            return len(list(project_path.rglob(f"*{extension}"))) > 0
        else:
            # 检查具体文件或目录
            return (project_path / indicator).exists()
    
    def _handle_typescript_detection(self, project_path: Path, scores: Dict[ProjectType, int]) -> Dict[ProjectType, int]:
        """处理TypeScript检测的特殊情况"""
        # 如果存在tsconfig.json，很可能是TypeScript项目
        if (project_path / "tsconfig.json").exists():
            scores[ProjectType.TYPESCRIPT] += 10
            
            # 检查package.json中的TypeScript相关依赖
            package_json_path = project_path / "package.json"
            if package_json_path.exists():
                try:
                    with open(package_json_path, 'r', encoding='utf-8') as f:
                        package_data = json.load(f)
                    
                    # 检查TypeScript相关依赖
                    deps = {**package_data.get('dependencies', {}), **package_data.get('devDependencies', {})}
                    typescript_deps = ['typescript', '@types/node', 'ts-node', 'tsx']
                    
                    for dep in typescript_deps:
                        if dep in deps:
                            scores[ProjectType.TYPESCRIPT] += 5
                            logger.debug(f"✓ TypeScript: 发现依赖 {dep} (+5分)")
                            
                except Exception as e:
                    logger.warning(f"解析package.json失败: {e}")
        
        return scores
    
    def _log_detection_details(self, project_path: Path, scores: Dict[ProjectType, int], detected_type: ProjectType):
        """记录详细的检测信息"""
        logger.info(f"📊 项目类型检测详情 - {project_path}")
        for ptype, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            status = "🏆" if ptype == detected_type else "  "
            logger.info(f"{status} {ptype.value}: {score}分")
    
    def detect_package_manager(self, project_path: Path, project_type: ProjectType) -> Optional[str]:
        """
        检测项目使用的包管理器
        
        Args:
            project_path: 项目路径
            project_type: 项目类型
            
        Returns:
            包管理器名称或None
        """
        if project_type not in self.PACKAGE_MANAGERS:
            return None
        
        managers = self.PACKAGE_MANAGERS[project_type]
        
        # 1. 根据锁文件检测
        lock_file_mapping = {
            "yarn.lock": "yarn",
            "pnpm-lock.yaml": "pnpm",
            "package-lock.json": "npm",
            "poetry.lock": "poetry",
            "Pipfile.lock": "pipenv"
        }
        
        for lock_file, manager in lock_file_mapping.items():
            if (project_path / lock_file).exists() and manager in managers:
                logger.info(f"📦 根据锁文件检测到包管理器: {manager}")
                return manager
        
        # 2. 检测系统中可用的包管理器
        for manager, config in managers.items():
            if self._check_command_available(config["command"]):
                logger.info(f"📦 检测到可用的包管理器: {manager}")
                return manager
        
        return None
    
    def get_install_commands(self, project_path: Path, project_type: ProjectType) -> List[List[str]]:
        """
        获取依赖安装命令列表
        支持多个包管理器，提供备选方案
        
        Args:
            project_path: 项目路径
            project_type: 项目类型
            
        Returns:
            安装命令列表
        """
        commands = []
        
        if project_type not in self.PACKAGE_MANAGERS:
            logger.warning(f"⚠️ 不支持的项目类型: {project_type}")
            return commands
        
        # 检测包管理器
        package_manager = self.detect_package_manager(project_path, project_type)
        
        if package_manager:
            # 使用检测到的包管理器
            manager_config = self.PACKAGE_MANAGERS[project_type][package_manager]
            for template in manager_config["install_templates"]:
                commands.append(template.split())
        else:
            # 使用所有可用的包管理器作为备选
            for manager, config in self.PACKAGE_MANAGERS[project_type].items():
                if self._check_command_available(config["command"]):
                    for template in config["install_templates"]:
                        commands.append(template.split())
        
        # 特殊处理
        commands = self._customize_install_commands(project_path, project_type, commands)
        
        logger.info(f"📋 生成安装命令: {commands}")
        return commands
    
    def _customize_install_commands(self, project_path: Path, project_type: ProjectType, commands: List[List[str]]) -> List[List[str]]:
        """根据项目特点定制安装命令"""
        
        if project_type == ProjectType.PYTHON:
            # 检查是否有特定的依赖文件
            if (project_path / "pyproject.toml").exists():
                commands = [["pip", "install", "-e", "."]] + commands
            elif (project_path / "requirements.txt").exists():
                commands = [["pip", "install", "-r", "requirements.txt"]] + commands
            
        elif project_type == ProjectType.TYPESCRIPT:
            # 确保TypeScript编译命令在安装后执行
            has_tsc = any("tsc" in " ".join(cmd) for cmd in commands)
            if not has_tsc and (project_path / "tsconfig.json").exists():
                commands.append(["npx", "tsc"])
        
        return commands
    
    def get_startup_command_template(self, project_type: ProjectType) -> Optional[List[str]]:
        """获取启动命令模板"""
        templates = {
            ProjectType.PYTHON: ["python3"],
            ProjectType.NODEJS: ["node"],
            ProjectType.TYPESCRIPT: ["node"],  # 编译后使用node运行
            ProjectType.RUST: ["cargo", "run"],
            ProjectType.GO: ["go", "run"]
        }
        return templates.get(project_type)
    
    def get_runtime_info(self, project_path: Path) -> Dict[str, Any]:
        """
        获取项目的完整运行时信息
        
        Returns:
            包含项目类型、包管理器、安装命令等信息的字典
        """
        project_type = self.detect_project_type(project_path)
        package_manager = self.detect_package_manager(project_path, project_type)
        install_commands = self.get_install_commands(project_path, project_type)
        startup_template = self.get_startup_command_template(project_type)
        
        info = {
            "project_type": project_type.value,
            "package_manager": package_manager,
            "install_commands": install_commands,
            "startup_template": startup_template,
            "project_path": str(project_path),
            "detection_timestamp": self._get_timestamp()
        }
        
        # 添加特定类型的额外信息
        if project_type == ProjectType.NODEJS:
            info["node_version"] = self._get_node_version()
        elif project_type == ProjectType.PYTHON:
            info["python_version"] = self._get_python_version()
        
        return info
    
    def _check_command_available(self, command: List[str]) -> bool:
        """检查命令是否可用"""
        try:
            result = subprocess.run(
                command, 
                capture_output=True, 
                timeout=10,
                check=False
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _get_node_version(self) -> Optional[str]:
        """获取Node.js版本"""
        try:
            result = subprocess.run(
                ["node", "--version"], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except:
            return None
    
    def _get_python_version(self) -> Optional[str]:
        """获取Python版本"""
        try:
            result = subprocess.run(
                ["python3", "--version"], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except:
            return None
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def clear_cache(self):
        """清理检测缓存"""
        self.cache.clear()
        logger.info("🔄 已清理运行时检测缓存")