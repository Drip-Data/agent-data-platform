"""
智能入口点检测器
解决当前入口点检测不准确的问题，提供多策略检测机制
"""

import json
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class SmartEntryPointDetector:
    """智能入口点检测器"""
    
    # Python 入口点搜索模式（按优先级排序）
    PYTHON_PATTERNS = [
        "main.py", "app.py", "server.py", "run.py", "__main__.py",
        "src/main.py", "src/app.py", "src/server.py", "src/__main__.py",
        "*/server.py", "*/main.py", "*/app.py",
        "mcp_server.py", "*/mcp_server.py", "server/main.py"
    ]
    
    # Node.js 入口点搜索模式
    NODEJS_PATTERNS = [
        "index.js", "server.js", "app.js", "main.js",
        "src/index.js", "src/server.js", "src/app.js", "src/main.js",
        "dist/index.js", "dist/server.js", "dist/main.js",
        "build/index.js", "build/server.js", "lib/index.js",
        "lib/server.js", "lib/main.js"
    ]
    
    # TypeScript 入口点搜索模式
    TYPESCRIPT_PATTERNS = [
        "index.ts", "server.ts", "app.ts", "main.ts",
        "src/index.ts", "src/server.ts", "src/app.ts", "src/main.ts"
    ]
    
    @classmethod
    def detect_entry_point(cls, project_path: Path, project_type: str, mcp_config: Dict = None) -> Optional[str]:
        """
        检测项目入口点
        优先使用配置，然后自动发现
        
        Args:
            project_path: 项目路径
            project_type: 项目类型 (python, nodejs, typescript等)
            mcp_config: MCP配置字典
            
        Returns:
            入口点路径或None
        """
        try:
            # 1. 优先使用配置中指定的入口点
            if mcp_config and 'entry_point' in mcp_config:
                entry_point = mcp_config['entry_point']
                if cls._validate_entry_point(project_path, entry_point):
                    logger.info(f"✅ 使用配置指定的入口点: {entry_point}")
                    return entry_point
                else:
                    logger.warning(f"⚠️ 配置的入口点不存在: {entry_point}")
            
            # 2. 根据项目类型自动检测
            if project_type.lower() == "python":
                return cls._detect_python_entry_point(project_path)
            elif project_type.lower() in ["nodejs", "node", "javascript"]:
                return cls._detect_nodejs_entry_point(project_path)
            elif project_type.lower() in ["typescript", "ts"]:
                return cls._detect_typescript_entry_point(project_path)
            else:
                logger.warning(f"🤔 未知项目类型: {project_type}，尝试通用检测")
                return cls._detect_generic_entry_point(project_path)
                
        except Exception as e:
            logger.error(f"❌ 入口点检测失败: {e}")
            return None
    
    @classmethod
    def _detect_python_entry_point(cls, project_path: Path) -> Optional[str]:
        """检测Python项目入口点"""
        
        # 1. 检查 pyproject.toml
        entry_point = cls._extract_from_pyproject(project_path / "pyproject.toml")
        if entry_point:
            logger.info(f"📋 从pyproject.toml发现入口点: {entry_point}")
            return entry_point
        
        # 2. 检查 setup.py
        entry_point = cls._extract_from_setup_py(project_path / "setup.py")
        if entry_point:
            logger.info(f"📋 从setup.py发现入口点: {entry_point}")
            return entry_point
        
        # 3. 检查是否是包模块
        if cls._is_python_package(project_path):
            package_main = cls._find_package_main(project_path)
            if package_main:
                logger.info(f"📦 发现Python包主模块: {package_main}")
                return package_main
        
        # 4. 模式匹配搜索
        for pattern in cls.PYTHON_PATTERNS:
            matches = list(project_path.glob(pattern))
            if matches:
                best_match = cls._select_best_python_entry(matches, project_path)
                if best_match:
                    rel_path = best_match.relative_to(project_path)
                    logger.info(f"🔍 模式匹配发现Python入口点: {rel_path}")
                    return str(rel_path)
        
        logger.warning(f"❌ 未找到Python入口点: {project_path}")
        return None
    
    @classmethod
    def _detect_nodejs_entry_point(cls, project_path: Path) -> Optional[str]:
        """检测Node.js项目入口点"""
        
        # 1. 检查 package.json
        entry_point = cls._extract_from_package_json(project_path / "package.json")
        if entry_point:
            logger.info(f"📋 从package.json发现入口点: {entry_point}")
            return entry_point
        
        # 2. 模式匹配搜索
        for pattern in cls.NODEJS_PATTERNS:
            matches = list(project_path.glob(pattern))
            if matches:
                best_match = cls._select_best_nodejs_entry(matches, project_path)
                if best_match:
                    rel_path = best_match.relative_to(project_path)
                    logger.info(f"🔍 模式匹配发现Node.js入口点: {rel_path}")
                    return str(rel_path)
        
        logger.warning(f"❌ 未找到Node.js入口点: {project_path}")
        return None
    
    @classmethod
    def _detect_typescript_entry_point(cls, project_path: Path) -> Optional[str]:
        """检测TypeScript项目入口点"""
        
        # 1. 检查 tsconfig.json
        entry_point = cls._extract_from_tsconfig(project_path / "tsconfig.json")
        if entry_point:
            logger.info(f"📋 从tsconfig.json发现入口点: {entry_point}")
            return entry_point
        
        # 2. 检查 package.json
        entry_point = cls._extract_from_package_json(project_path / "package.json")
        if entry_point and entry_point.endswith('.ts'):
            logger.info(f"📋 从package.json发现TypeScript入口点: {entry_point}")
            return entry_point
        
        # 3. 模式匹配搜索
        for pattern in cls.TYPESCRIPT_PATTERNS:
            matches = list(project_path.glob(pattern))
            if matches:
                best_match = cls._select_best_typescript_entry(matches, project_path)
                if best_match:
                    rel_path = best_match.relative_to(project_path)
                    logger.info(f"🔍 模式匹配发现TypeScript入口点: {rel_path}")
                    return str(rel_path)
        
        # 4. 如果找不到TypeScript文件，查找编译后的JavaScript文件
        logger.info("🔄 TypeScript源文件未找到，尝试查找编译后的JavaScript文件")
        return cls._detect_nodejs_entry_point(project_path)
    
    @classmethod
    def _detect_generic_entry_point(cls, project_path: Path) -> Optional[str]:
        """通用入口点检测"""
        
        # 尝试所有已知模式
        all_patterns = cls.PYTHON_PATTERNS + cls.NODEJS_PATTERNS + cls.TYPESCRIPT_PATTERNS
        
        for pattern in all_patterns:
            matches = list(project_path.glob(pattern))
            if matches:
                # 选择最可能的入口点
                best_match = min(matches, key=lambda p: len(p.parts))
                rel_path = best_match.relative_to(project_path)
                logger.info(f"🎯 通用检测发现入口点: {rel_path}")
                return str(rel_path)
        
        return None
    
    @classmethod
    def _extract_from_package_json(cls, package_json_path: Path) -> Optional[str]:
        """从 package.json 提取入口点"""
        if not package_json_path.exists():
            return None
        
        try:
            with open(package_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 1. 检查 scripts.start
            if 'scripts' in data and 'start' in data['scripts']:
                start_script = data['scripts']['start']
                entry_point = cls._parse_npm_start_script(start_script)
                if entry_point:
                    logger.debug(f"从scripts.start解析入口点: {entry_point}")
                    return entry_point
            
            # 2. 检查 main 字段
            if 'main' in data and data['main']:
                main_file = data['main']
                logger.debug(f"从main字段获取入口点: {main_file}")
                return main_file
            
        except Exception as e:
            logger.error(f"解析package.json失败: {e}")
        
        return None
    
    @classmethod
    def _parse_npm_start_script(cls, start_script: str) -> Optional[str]:
        """解析 npm start 脚本"""
        patterns = [
            r'node\s+(\S+\.js)',
            r'nodemon\s+(\S+\.js)',
            r'ts-node\s+(\S+\.ts)',
            r'tsx\s+(\S+\.ts)',
            r'npx\s+ts-node\s+(\S+\.ts)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, start_script)
            if match:
                entry_file = match.group(1)
                logger.debug(f"从启动脚本解析入口点: {entry_file}")
                return entry_file
        
        # 如果是简单的 "npm start"，返回标识
        if start_script.strip() == "npm start":
            return "npm start"
        
        return None
    
    @classmethod
    def _extract_from_tsconfig(cls, tsconfig_path: Path) -> Optional[str]:
        """从 tsconfig.json 提取入口点"""
        if not tsconfig_path.exists():
            return None
        
        try:
            with open(tsconfig_path, 'r', encoding='utf-8') as f:
                # 处理 JSON 注释
                content = f.read()
                content = re.sub(r'//.*', '', content)  # 移除单行注释
                content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)  # 移除多行注释
                data = json.loads(content)
            
            # 检查 compilerOptions.outDir 和 include
            if 'include' in data and data['include']:
                for include_pattern in data['include']:
                    if include_pattern.endswith('.ts'):
                        return include_pattern
            
        except Exception as e:
            logger.error(f"解析tsconfig.json失败: {e}")
        
        return None
    
    @classmethod
    def _select_best_python_entry(cls, matches: List[Path], project_path: Path) -> Optional[Path]:
        """选择最佳的Python入口点"""
        if not matches:
            return None
        
        def score_python_entry(path: Path) -> int:
            score = 0
            name = path.name
            rel_path = str(path.relative_to(project_path))
            
            # 文件名优先级
            if name == "main.py": score += 10
            elif name == "server.py": score += 8
            elif name == "app.py": score += 6
            elif name == "__main__.py": score += 5
            elif name == "run.py": score += 4
            
            # 路径优先级（根目录 > src > 其他）
            if "/" not in rel_path: score += 5
            elif rel_path.startswith("src/"): score += 3
            
            # MCP 特有加分
            if "mcp" in name.lower() or "mcp" in rel_path.lower(): score += 2
            
            return score
        
        return max(matches, key=score_python_entry)
    
    @classmethod
    def _select_best_nodejs_entry(cls, matches: List[Path], project_path: Path) -> Optional[Path]:
        """选择最佳的Node.js入口点"""
        if not matches:
            return None
        
        def score_nodejs_entry(path: Path) -> int:
            score = 0
            name = path.name
            rel_path = str(path.relative_to(project_path))
            
            # 文件名优先级
            if name == "index.js": score += 10
            elif name == "server.js": score += 8
            elif name == "app.js": score += 6
            elif name == "main.js": score += 5
            
            # 路径优先级
            if "/" not in rel_path: score += 5
            elif rel_path.startswith("src/"): score += 4
            elif rel_path.startswith("dist/"): score += 3
            elif rel_path.startswith("build/"): score += 2
            elif rel_path.startswith("lib/"): score += 2
            
            return score
        
        return max(matches, key=score_nodejs_entry)
    
    @classmethod
    def _select_best_typescript_entry(cls, matches: List[Path], project_path: Path) -> Optional[Path]:
        """选择最佳的TypeScript入口点"""
        if not matches:
            return None
        
        def score_typescript_entry(path: Path) -> int:
            score = 0
            name = path.name
            rel_path = str(path.relative_to(project_path))
            
            # 文件名优先级
            if name == "index.ts": score += 10
            elif name == "server.ts": score += 8
            elif name == "app.ts": score += 6
            elif name == "main.ts": score += 5
            
            # 路径优先级
            if "/" not in rel_path: score += 5
            elif rel_path.startswith("src/"): score += 4
            
            return score
        
        return max(matches, key=score_typescript_entry)
    
    @classmethod
    def _validate_entry_point(cls, project_path: Path, entry_point: str) -> bool:
        """验证入口点是否存在"""
        if entry_point == "npm start":
            # 检查是否有package.json和start脚本
            package_json = project_path / "package.json"
            if package_json.exists():
                try:
                    with open(package_json, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    return 'scripts' in data and 'start' in data['scripts']
                except:
                    return False
            return False
        
        entry_path = project_path / entry_point
        return entry_path.exists() and entry_path.is_file()
    
    @classmethod
    def _is_python_package(cls, project_path: Path) -> bool:
        """检查是否是Python包"""
        return len(list(project_path.rglob("__init__.py"))) > 0
    
    @classmethod
    def _find_package_main(cls, project_path: Path) -> Optional[str]:
        """查找包的主模块"""
        main_files = list(project_path.rglob("__main__.py"))
        if main_files:
            # 选择层级最少的__main__.py
            main_file = min(main_files, key=lambda p: len(p.parts))
            package_name = main_file.parent.name
            logger.debug(f"发现Python包主模块: {package_name}")
            return package_name
        return None
    
    @classmethod
    def _extract_from_pyproject(cls, pyproject_path: Path) -> Optional[str]:
        """从 pyproject.toml 提取入口点"""
        if not pyproject_path.exists():
            return None
        
        try:
            try:
                import tomllib
                with open(pyproject_path, 'rb') as f:
                    data = tomllib.load(f)
            except ImportError:
                try:
                    import toml
                    data = toml.load(pyproject_path)
                except ImportError:
                    logger.warning("无法导入toml解析库，跳过pyproject.toml解析")
                    return None
            
            # 检查 project.scripts
            scripts = data.get('project', {}).get('scripts', {})
            if scripts:
                return list(scripts.values())[0]
            
            # 检查 tool.poetry.scripts
            poetry_scripts = data.get('tool', {}).get('poetry', {}).get('scripts', {})
            if poetry_scripts:
                return list(poetry_scripts.values())[0]
                
        except Exception as e:
            logger.error(f"解析pyproject.toml失败: {e}")
        
        return None
    
    @classmethod
    def _extract_from_setup_py(cls, setup_py_path: Path) -> Optional[str]:
        """从 setup.py 提取入口点（简单实现）"""
        if not setup_py_path.exists():
            return None
        
        try:
            content = setup_py_path.read_text(encoding='utf-8')
            # 查找 entry_points
            match = re.search(r'entry_points\s*=\s*{[^}]*["\']console_scripts["\']\s*:\s*\[[^]]*["\']([^"\'=]+)', content)
            if match:
                return match.group(1).strip()
        except Exception as e:
            logger.error(f"解析setup.py失败: {e}")
        
        return None