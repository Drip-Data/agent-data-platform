"""
工具描述引擎
提供工具能力的动态描述生成和格式化
"""

import logging
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from .interfaces import ToolSpec, ToolCapability
from .tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class DescriptionTemplate:
    """描述模板"""
    template_id: str
    name: str
    format_type: str  # "markdown", "json", "plain_text"
    template_content: str


class DescriptionEngine:
    """工具描述引擎"""
    
    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry
        self._templates = self._initialize_templates()
    
    async def initialize(self):
        """初始化描述引擎"""
        logger.info("Description engine initialized")
    
    def _initialize_templates(self) -> Dict[str, DescriptionTemplate]:
        """初始化描述模板"""
        templates = {}
        
        # Agent友好的工具描述模板
        agent_template = DescriptionTemplate(
            template_id="agent_friendly",
            name="Agent友好描述",
            format_type="markdown",
            template_content="""
工具: {tool_name} (ID: {tool_id})
类型: {tool_type}
描述: {description}
标签: {tags}

可用功能:
{capabilities}

使用场景: 当需要{description_lower}时使用此工具
"""
        )
        templates[agent_template.template_id] = agent_template
        
        # 详细Markdown格式模板
        markdown_template = DescriptionTemplate(
            template_id="markdown_detailed",
            name="详细Markdown描述",
            format_type="markdown",
            template_content="""
# {tool_name}

**类型：** {tool_type}  
**版本：** {version}  
**标签：** {tags}

## 概述
{description}

## 功能列表

{capabilities}

## 使用统计
- 总调用次数：{usage_count}
- 成功率：{success_rate:.1%}
- 最后使用：{last_used}

---
*由 Datapresso Agent 工具库自动生成*
"""
        )
        templates[markdown_template.template_id] = markdown_template
        
        # JSON格式模板
        json_template = DescriptionTemplate(
            template_id="json_schema",
            name="JSON Schema格式",
            format_type="json",
            template_content="""
{
  "tool_id": "{tool_id}",
  "name": "{tool_name}",
  "description": "{description}",
  "type": "{tool_type}",
  "version": "{version}",
  "tags": {tags_json},
  "capabilities": {capabilities_json},
  "usage_info": {
    "usage_count": {usage_count},
    "success_rate": {success_rate},
    "last_used": "{last_used}"
  }
}
"""
        )
        templates[json_template.template_id] = json_template
        
        return templates
    
    async def generate_tool_description_for_agent(self, tool_id: str) -> str:
        """为Agent生成工具描述"""
        try:
            tool_spec = await self.tool_registry.get_tool_spec(tool_id)
            if not tool_spec:
                return "工具未找到"
            
            capabilities_desc = "\n".join([
                f"  - {cap.name}: {cap.description}"
                f"\n    参数: {self._format_parameters(cap.parameters)}"
                f"\n    示例: {cap.examples[0] if cap.examples else 'N/A'}"
                for cap in tool_spec.capabilities
            ])
            
            return f"""
工具: {tool_spec.name} (ID: {tool_spec.tool_id})
类型: {tool_spec.tool_type.value}
描述: {tool_spec.description}
标签: {', '.join(tool_spec.tags)}

可用功能:
{capabilities_desc}

使用场景: 当需要{tool_spec.description.lower()}时使用此工具
"""
        except Exception as e:
            logger.error(f"Failed to generate agent-friendly description: {e}")
            return f"生成工具描述失败: {str(e)}"
    
    async def generate_all_tools_description_for_agent(self) -> str:
        """为Agent生成所有工具的描述"""
        try:
            all_tools = await self.tool_registry.get_all_tools()
            
            descriptions = []
            for tool in all_tools:
                desc = await self.generate_tool_description_for_agent(tool.tool_id)
                descriptions.append(desc)
            
            if not descriptions:
                return "暂无可用工具"
            
            header = "\n" + "="*80 + "\n可用工具列表:\n" + "="*80
            footer = "\n" + "="*80
            
            return header + "\n" + "\n".join(descriptions) + footer
        except Exception as e:
            logger.error(f"Failed to generate all tools description: {e}")
            return "生成工具描述失败"
    
    async def get_tool_usage_examples(self, tool_id: str) -> List[Dict[str, Any]]:
        """获取工具使用示例"""
        try:
            tool_spec = await self.tool_registry.get_tool_spec(tool_id)
            if not tool_spec:
                return []
            
            examples = []
            for capability in tool_spec.capabilities:
                for example in capability.examples:
                    examples.append({
                        "capability": capability.name,
                        "description": capability.description,
                        "example": example
                    })
            
            return examples
        except Exception as e:
            logger.error(f"Failed to get tool usage examples: {e}")
            return []
    
    async def generate_tool_description(
        self, 
        tool_id: str, 
        template_id: str = "markdown_detailed",
        include_examples: bool = True
    ) -> str:
        """生成工具描述"""
        try:
            # 获取工具规范
            tool_spec = await self.tool_registry.get_tool_spec(tool_id)
            if not tool_spec:
                return "工具未找到"
            
            # 获取使用统计
            registry_entry = self.tool_registry._tools.get(tool_id)
            usage_count = registry_entry.usage_count if registry_entry else 0
            success_rate = registry_entry.success_rate if registry_entry else 0.0
            last_used = registry_entry.last_used.strftime("%Y-%m-%d %H:%M") if registry_entry and registry_entry.last_used else "从未使用"
            
            # 获取模板
            template = self._templates.get(template_id, self._templates["markdown_detailed"])
            
            # 准备变量
            variables = {
                "tool_id": tool_spec.tool_id,
                "tool_name": tool_spec.name,
                "description": tool_spec.description,
                "description_lower": tool_spec.description.lower(),
                "tool_type": tool_spec.tool_type.value,
                "version": tool_spec.version,
                "tags": ", ".join(tool_spec.tags),
                "usage_count": usage_count,
                "success_rate": success_rate,
                "last_used": last_used
            }
            
            # 生成能力描述
            if template.format_type == "markdown":
                variables["capabilities"] = self._format_capabilities_markdown(
                    tool_spec.capabilities, include_examples
                )
            elif template.format_type == "json":
                variables["capabilities_json"] = json.dumps(
                    [cap.to_dict() for cap in tool_spec.capabilities], 
                    ensure_ascii=False, indent=2
                )
                variables["tags_json"] = json.dumps(tool_spec.tags, ensure_ascii=False)
            
            # 填充模板
            return template.template_content.format(**variables)
            
        except Exception as e:
            logger.error(f"Failed to generate tool description: {e}")
            return f"生成工具描述失败: {str(e)}"
    
    def _format_capabilities_markdown(self, capabilities: List[ToolCapability], include_examples: bool) -> str:
        """格式化能力为Markdown"""
        markdown_parts = []
        
        for i, capability in enumerate(capabilities, 1):
            markdown_parts.append(f"### {i}. {capability.name}")
            markdown_parts.append(f"{capability.description}")
            
            # 参数列表
            if capability.parameters:
                markdown_parts.append("**参数：**")
                for param_name, param_info in capability.parameters.items():
                    param_type = param_info.get("type", "string")
                    required = "必填" if param_info.get("required", False) else "可选"
                    param_desc = param_info.get("description", "")
                    
                    markdown_parts.append(f"- `{param_name}` ({param_type}, {required}): {param_desc}")
            
            # 使用示例
            if include_examples and capability.examples:
                markdown_parts.append("**示例：**")
                for j, example in enumerate(capability.examples[:2], 1):  # 最多显示2个
                    markdown_parts.append(f"```json")
                    markdown_parts.append(f"// 示例 {j}")
                    markdown_parts.append(json.dumps(example, ensure_ascii=False, indent=2))
                    markdown_parts.append("```")
            
            markdown_parts.append("")  # 空行分隔
        
        return "\n".join(markdown_parts)
    
    def _format_parameters(self, parameters: Dict[str, Any]) -> str:
        """格式化参数信息"""
        if not parameters:
            return "无"
        
        param_strs = []
        for param_name, param_info in parameters.items():
            if isinstance(param_info, dict):
                param_type = param_info.get("type", "any")
                required = "必填" if param_info.get("required", False) else "可选"
                param_strs.append(f"{param_name}({param_type}, {required})")
            else:
                param_strs.append(param_name)
        
        return ", ".join(param_strs)
    
    def register_custom_template(self, template: DescriptionTemplate) -> bool:
        """注册自定义模板"""
        try:
            self._templates[template.template_id] = template
            logger.info(f"Registered custom template: {template.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to register template: {e}")
            return False
    
    def get_available_templates(self) -> List[Dict[str, str]]:
        """获取可用模板列表"""
        return [
            {
                "template_id": template.template_id,
                "name": template.name,
                "format_type": template.format_type
            }
            for template in self._templates.values()
        ] 