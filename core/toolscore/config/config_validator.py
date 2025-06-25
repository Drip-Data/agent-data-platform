"""
MCP配置验证器
提供配置验证、格式检查和兼容性验证功能
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from pydantic import ValidationError

from .schemas import (
    ToolConfigSchema, 
    ServerConfigSchema, 
    ToolRegistrySchema,
    MCPConfigSchema,
    ToolConfigUpdateSchema,
    ServerConfigUpdateSchema
)
from ..exceptions import MCPConfigurationError

logger = logging.getLogger(__name__)


class MCPConfigValidator:
    """MCP配置验证器"""
    
    def __init__(self):
        self.validation_errors = []
        self.warnings = []
    
    def validate_tool_config(self, config: Dict[str, Any]) -> ToolConfigSchema:
        """
        验证单个工具配置
        
        Args:
            config: 工具配置字典
            
        Returns:
            验证后的配置对象
            
        Raises:
            MCPConfigurationError: 配置验证失败
        """
        try:
            self.validation_errors.clear()
            self.warnings.clear()
            
            # 基础验证
            validated_config = ToolConfigSchema(**config)
            
            # 附加验证
            self._validate_tool_compatibility(validated_config)
            self._validate_tool_security(validated_config)
            
            if self.validation_errors:
                raise MCPConfigurationError(
                    f"工具配置验证失败: {'; '.join(self.validation_errors)}",
                    config_key="tool_config",
                    details={"errors": self.validation_errors, "warnings": self.warnings}
                )
            
            if self.warnings:
                logger.warning(f"⚠️ 工具配置警告: {'; '.join(self.warnings)}")
            
            logger.info(f"✅ 工具配置验证通过: {validated_config.id}")
            return validated_config
            
        except ValidationError as e:
            error_msg = self._format_validation_error(e)
            raise MCPConfigurationError(
                f"工具配置格式错误: {error_msg}",
                config_key="tool_config",
                details={"validation_errors": str(e)}
            )
    
    def validate_server_config(self, config: Dict[str, Any]) -> ServerConfigSchema:
        """
        验证服务器配置
        
        Args:
            config: 服务器配置字典
            
        Returns:
            验证后的配置对象
            
        Raises:
            MCPConfigurationError: 配置验证失败
        """
        try:
            self.validation_errors.clear()
            self.warnings.clear()
            
            # 基础验证
            validated_config = ServerConfigSchema(**config)
            
            # 附加验证
            self._validate_server_path(validated_config)
            self._validate_server_port(validated_config)
            
            if self.validation_errors:
                raise MCPConfigurationError(
                    f"服务器配置验证失败: {'; '.join(self.validation_errors)}",
                    config_key="server_config",
                    details={"errors": self.validation_errors, "warnings": self.warnings}
                )
            
            if self.warnings:
                logger.warning(f"⚠️ 服务器配置警告: {'; '.join(self.warnings)}")
            
            logger.info(f"✅ 服务器配置验证通过: {validated_config.id}")
            return validated_config
            
        except ValidationError as e:
            error_msg = self._format_validation_error(e)
            raise MCPConfigurationError(
                f"服务器配置格式错误: {error_msg}",
                config_key="server_config",
                details={"validation_errors": str(e)}
            )
    
    def validate_tool_registry(self, config: Dict[str, Any]) -> ToolRegistrySchema:
        """
        验证工具注册表配置
        
        Args:
            config: 注册表配置字典
            
        Returns:
            验证后的配置对象
            
        Raises:
            MCPConfigurationError: 配置验证失败
        """
        try:
            self.validation_errors.clear()
            self.warnings.clear()
            
            # 基础验证
            validated_config = ToolRegistrySchema(**config)
            
            # 附加验证
            self._validate_registry_tools(validated_config)
            
            if self.validation_errors:
                raise MCPConfigurationError(
                    f"注册表配置验证失败: {'; '.join(self.validation_errors)}",
                    config_key="tool_registry",
                    details={"errors": self.validation_errors, "warnings": self.warnings}
                )
            
            if self.warnings:
                logger.warning(f"⚠️ 注册表配置警告: {'; '.join(self.warnings)}")
            
            logger.info(f"✅ 注册表配置验证通过，包含{len(validated_config.tools)}个工具")
            return validated_config
            
        except ValidationError as e:
            error_msg = self._format_validation_error(e)
            raise MCPConfigurationError(
                f"注册表配置格式错误: {error_msg}",
                config_key="tool_registry",
                details={"validation_errors": str(e)}
            )
    
    def validate_config_file(self, config_path: Path) -> MCPConfigSchema:
        """
        验证配置文件
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            验证后的配置对象
            
        Raises:
            MCPConfigurationError: 配置验证失败
        """
        if not config_path.exists():
            raise MCPConfigurationError(
                f"配置文件不存在: {config_path}",
                config_file=str(config_path)
            )
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            return self.validate_full_config(config_data)
            
        except json.JSONDecodeError as e:
            raise MCPConfigurationError(
                f"配置文件JSON格式错误: {e}",
                config_file=str(config_path),
                details={"json_error": str(e)}
            )
        except Exception as e:
            raise MCPConfigurationError(
                f"读取配置文件失败: {e}",
                config_file=str(config_path),
                details={"error": str(e)}
            )
    
    def validate_full_config(self, config: Dict[str, Any]) -> MCPConfigSchema:
        """
        验证完整配置
        
        Args:
            config: 完整配置字典
            
        Returns:
            验证后的配置对象
        """
        try:
            return MCPConfigSchema(**config)
        except ValidationError as e:
            error_msg = self._format_validation_error(e)
            raise MCPConfigurationError(
                f"完整配置验证失败: {error_msg}",
                details={"validation_errors": str(e)}
            )
    
    def validate_partial_update(self, update_data: Dict[str, Any], config_type: str) -> Union[ToolConfigUpdateSchema, ServerConfigUpdateSchema]:
        """
        验证部分配置更新
        
        Args:
            update_data: 更新数据
            config_type: 配置类型 ("tool" 或 "server")
            
        Returns:
            验证后的更新对象
        """
        try:
            if config_type == "tool":
                return ToolConfigUpdateSchema(**update_data)
            elif config_type == "server":
                return ServerConfigUpdateSchema(**update_data)
            else:
                raise MCPConfigurationError(f"不支持的配置类型: {config_type}")
        except ValidationError as e:
            error_msg = self._format_validation_error(e)
            raise MCPConfigurationError(
                f"{config_type}配置更新验证失败: {error_msg}",
                details={"validation_errors": str(e)}
            )
    
    def _validate_tool_compatibility(self, config: ToolConfigSchema):
        """验证工具兼容性"""
        
        # 检查项目类型与入口点的一致性
        if config.entry_point:
            if config.project_type.value == "python" and not (
                config.entry_point.endswith('.py') or 
                config.entry_point == "npm start" or
                '.' not in config.entry_point  # 可能是包名
            ):
                self.validation_errors.append(f"Python项目的入口点格式不正确: {config.entry_point}")
            
            elif config.project_type.value in ["nodejs", "typescript"] and not (
                config.entry_point.endswith(('.js', '.ts', '.mjs')) or
                config.entry_point == "npm start"
            ):
                self.validation_errors.append(f"Node.js/TypeScript项目的入口点格式不正确: {config.entry_point}")
        
        # 检查依赖配置与项目类型的一致性
        if config.dependencies:
            if config.project_type.value == "python" and config.dependencies.nodejs:
                self.warnings.append("Python项目配置了Node.js依赖，请确认这是预期的")
            elif config.project_type.value in ["nodejs", "typescript"] and config.dependencies.python:
                self.warnings.append("Node.js项目配置了Python依赖，请确认这是预期的")
    
    def _validate_tool_security(self, config: ToolConfigSchema):
        """验证工具安全性"""
        
        # 检查GitHub URL的安全性
        if config.github_url:
            if "github.com" not in config.github_url:
                self.warnings.append("非GitHub仓库可能存在安全风险")
            
            # 检查是否是官方或知名组织
            if not any(org in config.github_url for org in [
                "github.com/microsoft/", 
                "github.com/openai/",
                "github.com/anthropics/",
                "github.com/modelcontextprotocol/"
            ]):
                if not config.security_score or config.security_score < 70:
                    self.warnings.append("第三方工具安全评分较低，建议谨慎使用")
        
        # 检查安全评分
        if config.security_score is not None and config.security_score < 50:
            self.warnings.append(f"工具安全评分过低: {config.security_score}")
    
    def _validate_server_path(self, config: ServerConfigSchema):
        """验证服务器路径"""
        server_path = Path(config.path)
        
        if not server_path.exists():
            self.validation_errors.append(f"服务器路径不存在: {config.path}")
        elif not server_path.is_dir():
            self.validation_errors.append(f"服务器路径不是目录: {config.path}")
    
    def _validate_server_port(self, config: ServerConfigSchema):
        """验证服务器端口"""
        if config.port:
            # 检查端口范围
            if config.port < 1024:
                self.warnings.append(f"使用系统端口 {config.port} 可能需要管理员权限")
            elif config.port > 65535:
                self.validation_errors.append(f"端口号超出有效范围: {config.port}")
    
    def _validate_registry_tools(self, config: ToolRegistrySchema):
        """验证注册表中的工具"""
        
        # 检查工具数量
        if len(config.tools) == 0:
            self.warnings.append("注册表中没有工具")
        elif len(config.tools) > 1000:
            self.warnings.append(f"注册表工具数量过多: {len(config.tools)}")
        
        # 检查工具质量
        low_quality_tools = []
        for tool in config.tools:
            if tool.popularity_score is not None and tool.popularity_score < 30:
                low_quality_tools.append(tool.id)
        
        if low_quality_tools:
            self.warnings.append(f"发现低质量工具: {', '.join(low_quality_tools[:5])}")
    
    def _format_validation_error(self, error: ValidationError) -> str:
        """格式化验证错误信息"""
        errors = []
        for err in error.errors():
            field = " -> ".join(str(loc) for loc in err['loc'])
            message = err['msg']
            errors.append(f"{field}: {message}")
        return "; ".join(errors)
    
    def get_validation_summary(self) -> Dict[str, Any]:
        """获取验证摘要"""
        return {
            "errors": self.validation_errors.copy(),
            "warnings": self.warnings.copy(),
            "error_count": len(self.validation_errors),
            "warning_count": len(self.warnings),
            "is_valid": len(self.validation_errors) == 0
        }
    
    def clear_results(self):
        """清理验证结果"""
        self.validation_errors.clear()
        self.warnings.clear()