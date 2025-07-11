#!/usr/bin/env python3
"""
Prompt 模板基础框架
提供模板化管理、参数化填充、版本控制等功能
"""

import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Union
from enum import Enum

logger = logging.getLogger(__name__)


class PromptType(Enum):
    """Prompt 类型枚举"""
    TASK_GENERATION = "task_generation"
    TASK_VALIDATION = "task_validation"
    TASK_SYNTHESIS = "task_synthesis"
    CONCLUSION_EXTRACTION = "conclusion_extraction"
    ATOMICITY_CHECK = "atomicity_check"
    TOOL_NECESSITY = "tool_necessity"
    REASONING_SUFFICIENCY = "reasoning_sufficiency"


@dataclass
class PromptTemplate:
    """
    Prompt 模板类
    
    功能：
    1. 模板存储和参数化
    2. 参数验证和填充
    3. 版本管理
    4. 使用统计
    """
    name: str
    template: str
    description: str
    prompt_type: PromptType
    required_params: List[str] = field(default_factory=list)
    optional_params: Dict[str, Any] = field(default_factory=dict)
    version: str = "1.0"
    usage_count: int = field(default=0, init=False)
    
    def __post_init__(self):
        """初始化后验证模板格式"""
        self._validate_template()
    
    def _validate_template(self):
        """验证模板格式和参数"""
        # 提取模板中的参数
        template_params = set(re.findall(r'\{(\w+)\}', self.template))
        required_set = set(self.required_params)
        optional_set = set(self.optional_params.keys())
        
        # 检查模板参数是否都有定义
        undefined_params = template_params - required_set - optional_set
        if undefined_params:
            logger.warning(f"模板 {self.name} 包含未定义的参数: {undefined_params}")
        
        # 检查定义的参数是否都在模板中使用
        unused_params = (required_set | optional_set) - template_params
        if unused_params:
            logger.warning(f"模板 {self.name} 定义了未使用的参数: {unused_params}")
    
    def render(self, **kwargs) -> str:
        """
        渲染模板，填充参数
        
        Args:
            **kwargs: 模板参数
            
        Returns:
            str: 渲染后的 Prompt
            
        Raises:
            ValueError: 缺少必需参数或参数验证失败
        """
        # 检查必需参数
        missing_params = set(self.required_params) - set(kwargs.keys())
        if missing_params:
            raise ValueError(f"模板 {self.name} 缺少必需参数: {missing_params}")
        
        # 合并默认值
        params = self.optional_params.copy()
        params.update(kwargs)
        
        try:
            # 渲染模板
            rendered = self.template.format(**params)
            self.usage_count += 1
            logger.debug(f"模板 {self.name} 渲染成功，使用次数: {self.usage_count}")
            return rendered
        except KeyError as e:
            raise ValueError(f"模板 {self.name} 参数错误: {e}")
        except Exception as e:
            raise ValueError(f"模板 {self.name} 渲染失败: {e}")
    
    def get_info(self) -> Dict[str, Any]:
        """获取模板信息"""
        return {
            "name": self.name,
            "description": self.description,
            "type": self.prompt_type.value,
            "version": self.version,
            "required_params": self.required_params,
            "optional_params": list(self.optional_params.keys()),
            "usage_count": self.usage_count
        }


class PromptModule(ABC):
    """
    Prompt 模块抽象基类
    每个具体的 Prompt 模块都应继承此类
    """
    
    @abstractmethod
    def get_templates(self) -> Dict[str, PromptTemplate]:
        """返回模块中的所有模板"""
        pass
    
    @abstractmethod
    def get_module_info(self) -> Dict[str, Any]:
        """返回模块信息"""
        pass


class PromptManager:
    """
    Prompt 管理器
    
    功能：
    1. 统一管理所有 Prompt 模板
    2. 提供模板查找和渲染接口
    3. 模板使用统计和监控
    4. 版本控制和更新
    """
    
    def __init__(self):
        self.modules: Dict[str, PromptModule] = {}
        self.templates: Dict[str, PromptTemplate] = {}
        
        logger.info("✅ PromptManager 初始化完成")
    
    def register_module(self, module_name: str, module_class: type):
        """注册 Prompt 模块"""
        try:
            module_instance = module_class()
            self.modules[module_name] = module_instance
            
            # 注册模块中的所有模板
            module_templates = module_instance.get_templates()
            for template_name, template in module_templates.items():
                full_name = f"{module_name}.{template_name}"
                self.templates[full_name] = template
                # 只注册短名称（如果没有冲突）
                if template_name not in self.templates:
                    self.templates[template_name] = template
                else:
                    logger.warning(f"模板名称冲突: {template_name}，请使用完整名称: {full_name}")
            
            logger.info(f"✅ 注册 Prompt 模块: {module_name}, 包含 {len(module_templates)} 个模板")
            
        except Exception as e:
            logger.error(f"❌ 注册 Prompt 模块失败: {module_name}, 错误: {e}")
            raise
    
    def get_template(self, template_name: str) -> Optional[PromptTemplate]:
        """获取模板"""
        return self.templates.get(template_name)
    
    def render_template(self, template_name: str, **kwargs) -> str:
        """渲染模板"""
        template = self.get_template(template_name)
        if not template:
            raise ValueError(f"模板不存在: {template_name}")
        
        return template.render(**kwargs)
    
    def list_templates(self, module_name: Optional[str] = None, 
                      prompt_type: Optional[PromptType] = None) -> List[Dict[str, Any]]:
        """列出模板"""
        templates = []
        
        for name, template in self.templates.items():
            # 过滤模块
            if module_name and not name.startswith(f"{module_name}."):
                continue
            
            # 过滤类型
            if prompt_type and template.prompt_type != prompt_type:
                continue
            
            templates.append(template.get_info())
        
        return templates
    
    def get_usage_statistics(self) -> Dict[str, Any]:
        """获取使用统计"""
        stats = {
            "total_templates": len(self.templates),
            "total_modules": len(self.modules),
            "usage_by_template": {},
            "usage_by_type": {},
            "most_used_templates": []
        }
        
        # 按模板统计
        for name, template in self.templates.items():
            stats["usage_by_template"][name] = template.usage_count
            
            # 按类型统计
            type_name = template.prompt_type.value
            if type_name not in stats["usage_by_type"]:
                stats["usage_by_type"][type_name] = 0
            stats["usage_by_type"][type_name] += template.usage_count
        
        # 最常用模板
        sorted_templates = sorted(
            self.templates.items(),
            key=lambda x: x[1].usage_count,
            reverse=True
        )
        stats["most_used_templates"] = [
            {"name": name, "usage_count": template.usage_count}
            for name, template in sorted_templates[:10]
        ]
        
        return stats
    
    def validate_all_templates(self) -> Dict[str, List[str]]:
        """验证所有模板"""
        validation_results = {
            "valid": [],
            "warnings": [],
            "errors": []
        }
        
        for name, template in self.templates.items():
            try:
                template._validate_template()
                validation_results["valid"].append(name)
            except Exception as e:
                validation_results["errors"].append(f"{name}: {e}")
        
        return validation_results