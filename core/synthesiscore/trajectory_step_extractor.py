#!/usr/bin/env python3
"""
轨迹步骤提取器和变体生成器
实现基于真实轨迹的原子步拆分和变体扩散
"""

import re
import logging
import json
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class AtomicStep:
    """原子步骤数据结构"""
    step_id: str
    step_type: str  # tool_call, reasoning, summary
    tool_name: Optional[str]
    operation: str  # 具体操作描述
    content: str    # 操作内容
    domain: str     # 领域
    complexity: str # 复杂度
    requires_tools: List[str]
    original_trajectory_id: str
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "step_id": self.step_id,
            "step_type": self.step_type,
            "tool_name": self.tool_name,
            "operation": self.operation,
            "content": self.content,
            "domain": self.domain,
            "complexity": self.complexity,
            "requires_tools": self.requires_tools,
            "original_trajectory_id": self.original_trajectory_id
        }


@dataclass
class StepVariant:
    """步骤变体数据结构"""
    variant_id: str
    base_step: AtomicStep
    variant_operation: str
    variant_content: str
    variant_domain: str
    substitution_mapping: Dict[str, str]  # 实体替换映射
    creativity_level: int
    generated_at: datetime
    
    def to_task_dict(self) -> Dict[str, Any]:
        """转换为任务格式"""
        return {
            "question": self.variant_operation,
            "expected_answer": f"基于{self.variant_domain}领域的{self.variant_content}",
            "task_type": "tool_required",
            "domain": self.variant_domain,
            "difficulty": self.base_step.complexity,
            "required_tools": self.base_step.requires_tools,
            "reasoning_steps": [f"执行{self.variant_operation}", f"获取{self.variant_content}"],
            "relation_pattern": f"step_variant_from_{self.base_step.step_type}",
            "entity_generalization": str(self.substitution_mapping),
            "creativity_level": str(self.creativity_level),
            "creativity_explanation": f"基于真实轨迹步骤的变体生成，原始步骤：{self.base_step.operation}",
            "reverse_reasoning": f"从轨迹步骤'{self.base_step.operation}'衍生出变体'{self.variant_operation}'"
        }


class TrajectoryStepExtractor:
    """轨迹步骤提取器"""
    
    def __init__(self):
        self.tool_patterns = [
            r'<(browser_search_google)>([^<]+)</\1>',
            r'<(browser_extract_content)>([^<]+)</\1>',
            r'<(browser_use_execute_task)>([^<]+)</\1>',
            r'<(browser_navigate)>([^<]+)</\1>',
            r'<(browser_click_element)>([^<]+)</\1>',
            r'<(browser_input_text)>([^<]+)</\1>',
            r'<(microsandbox_execute)>([^<]+)</\1>',
            r'<(microsandbox_install_package)>([^<]+)</\1>',
            r'<(deepsearch)><research>([^<]+)</research></\1>',
            r'<(deepsearch)><quick_research>([^<]+)</quick_research></\1>',
            r'<(deepsearch)><comprehensive_research>([^<]+)</comprehensive_research></\1>',
            r'<(search_file_content)>([^<]+)</\1>',
            r'<(list_code_definitions)>([^<]+)</\1>',
            r'<(search_and_install_tools)>([^<]+)</\1>',
            r'<(memory_staging)>([^<]+)</\1>'
        ]
        
        self.operation_templates = {
            "browser_search_google": "搜索{content}",
            "browser_extract_content": "提取{content}",
            "browser_use_execute_task": "执行浏览器任务{content}",
            "browser_navigate": "导航到{content}",
            "browser_click_element": "点击{content}",
            "browser_input_text": "输入{content}",
            "microsandbox_execute": "执行{content}",
            "microsandbox_install_package": "安装包{content}",
            "deepsearch": "深度研究{content}",
            "search_file_content": "搜索文件{content}",
            "list_code_definitions": "列出代码定义{content}",
            "search_and_install_tools": "搜索工具{content}",
            "memory_staging": "内存操作{content}"
        }
    
    def extract_atomic_steps(self, trajectory: Dict) -> List[AtomicStep]:
        """从轨迹中提取原子步骤"""
        raw_response = trajectory.get("raw_response", "")
        task_id = trajectory.get("task_id", "unknown")
        domain = self._infer_domain(trajectory.get("task_description", ""))
        
        steps = []
        step_counter = 0
        
        # 1. 提取工具调用步骤
        for pattern in self.tool_patterns:
            matches = re.findall(pattern, raw_response, re.DOTALL)
            for tool_name, content in matches:
                step_counter += 1
                
                # 清理内容
                clean_content = self._clean_content(content)
                if not clean_content:
                    continue
                
                # 生成操作描述
                operation = self._generate_operation_description(tool_name, clean_content)
                
                step = AtomicStep(
                    step_id=f"{task_id}_step_{step_counter}",
                    step_type="tool_call",
                    tool_name=tool_name,
                    operation=operation,
                    content=clean_content,
                    domain=domain,
                    complexity=self._assess_complexity(clean_content),
                    requires_tools=[tool_name],
                    original_trajectory_id=task_id
                )
                steps.append(step)
        
        # 2. 提取推理步骤
        reasoning_steps = self._extract_reasoning_steps(raw_response, task_id, domain)
        steps.extend(reasoning_steps)
        
        # 3. 提取总结步骤
        summary_steps = self._extract_summary_steps(raw_response, task_id, domain)
        steps.extend(summary_steps)
        
        logger.info(f"✅ 从轨迹 {task_id} 提取到 {len(steps)} 个原子步骤")
        return steps
    
    def _clean_content(self, content: str) -> str:
        """清理和标准化内容"""
        # 移除多余的空白和特殊字符
        clean = re.sub(r'\s+', ' ', content.strip())
        
        # 移除过长的内容
        if len(clean) > 200:
            clean = clean[:200] + "..."
        
        # 移除空内容
        if len(clean) < 5:
            return ""
        
        return clean
    
    def _generate_operation_description(self, tool_name: str, content: str) -> str:
        """生成操作描述"""
        template = self.operation_templates.get(tool_name, f"使用{tool_name}处理{{content}}")
        
        # 提取关键词用于替换
        key_content = self._extract_key_content(content)
        
        return template.format(content=key_content)
    
    def _extract_key_content(self, content: str) -> str:
        """从内容中提取关键词"""
        # 移除代码和技术细节，提取核心概念
        if "import" in content or "def " in content:
            return "代码分析"
        elif "http" in content:
            return "网络资源"
        elif any(keyword in content for keyword in ["股票", "价格", "金融"]):
            return "金融数据"
        elif any(keyword in content for keyword in ["量子", "机器学习", "AI"]):
            return "AI技术"
        else:
            # 提取前几个有意义的词
            words = content.split()[:3]
            return " ".join(words)
    
    def _extract_reasoning_steps(self, raw_response: str, task_id: str, domain: str) -> List[AtomicStep]:
        """提取推理步骤"""
        steps = []
        
        # 提取think块
        think_blocks = re.findall(r'<think>(.*?)</think>', raw_response, re.DOTALL)
        
        for i, think in enumerate(think_blocks):
            clean_think = self._clean_content(think)
            if clean_think:
                step = AtomicStep(
                    step_id=f"{task_id}_reasoning_{i+1}",
                    step_type="reasoning",
                    tool_name=None,
                    operation=f"分析推理{clean_think[:30]}",
                    content=clean_think,
                    domain=domain,
                    complexity="中等",
                    requires_tools=[],
                    original_trajectory_id=task_id
                )
                steps.append(step)
        
        return steps
    
    def _extract_summary_steps(self, raw_response: str, task_id: str, domain: str) -> List[AtomicStep]:
        """提取总结步骤"""
        steps = []
        
        # 提取answer块
        answer_blocks = re.findall(r'<answer>(.*?)</answer>', raw_response, re.DOTALL)
        
        for i, answer in enumerate(answer_blocks):
            clean_answer = self._clean_content(answer)
            if clean_answer:
                step = AtomicStep(
                    step_id=f"{task_id}_summary_{i+1}",
                    step_type="summary",
                    tool_name=None,
                    operation=f"总结{domain}结果",
                    content=clean_answer,
                    domain=domain,
                    complexity="简单",
                    requires_tools=[],
                    original_trajectory_id=task_id
                )
                steps.append(step)
        
        return steps
    
    def _infer_domain(self, content: str) -> str:
        """推断领域"""
        domain_keywords = {
            "股票|股价|金融|投资": "金融",
            "量子|物理|科学": "科学研究",
            "代码|编程|Python|算法": "编程",
            "搜索|研究|论文": "研究分析",
            "大学|学校|教育": "教育",
            "蛋白质|生物|医学": "生物医学"
        }
        
        for pattern, domain in domain_keywords.items():
            if re.search(pattern, content):
                return domain
        
        return "通用"
    
    def _assess_complexity(self, content: str) -> str:
        """评估复杂度"""
        if len(content) > 100 or any(keyword in content for keyword in ["计算", "分析", "对比"]):
            return "困难"
        elif len(content) > 50:
            return "中等"
        else:
            return "简单"


class LLMDrivenVariantGenerator:
    """LLM驱动的变体生成器 - 使用语义联想生成有意义的变体"""
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
        
        # 语义变体生成的Prompt模板
        self.semantic_variant_prompt = """你是一个创意任务设计专家。基于给定的原子步骤，生成有意义的变体任务。

原子步骤信息：
- 操作：{operation}
- 内容：{content}  
- 领域：{domain}
- 工具：{tool_name}

系统可用工具全景：
**🔍 研究工具**
- deepsearch: 深度研究、快速研究、全面研究
- search_file_content: 搜索文件内容
- list_code_definitions: 列出代码定义

**🌐 浏览器工具**  
- browser_search_google: Google搜索
- browser_extract_content: 提取页面内容
- browser_use_execute_task: 复杂AI浏览器任务
- browser_navigate: 导航到URL
- browser_click_element: 点击页面元素
- browser_input_text: 输入文本

**💻 代码执行工具**
- microsandbox_execute: 执行Python代码
- microsandbox_install_package: 安装Python包

**🔧 工具管理**
- search_and_install_tools: 搜索并安装新工具

变体生成策略：
1. **概念扩展**：将核心概念扩展到相关领域，智能分配合适工具
2. **复杂度递增**：在原有基础上增加分析、比较、评估等要求
3. **应用场景变化**：改变应用上下文但保持核心技能
4. **跨域联想**：基于相同技能要求联想到其他领域
5. **工具多样化**：根据任务特性选择最合适的工具组合

生成{max_variants}个变体，每个变体应该：
- 保持与原始任务的语义相关性
- 具有独立的任务价值  
- 适度提升复杂度
- 具备清晰的执行路径
- 智能选择合适的工具组合

工具选择指南与多样化要求：
- **信息研究类**: 优先使用 deepsearch 系列工具
- **网页交互类**: 优先使用 browser_use_execute_task, browser_navigate
- **内容提取类**: 使用 browser_extract_content
- **搜索类**: 避免过度使用 browser_search_google，优先选择 deepsearch
- **代码分析类**: 使用 microsandbox_execute, search_file_content
- **数据处理类**: 使用 microsandbox_execute
- **文档查找类**: 使用 list_code_definitions, search_file_content

⚠️ 工具多样化要求：
- 必须避免所有变体都使用相同工具 (如都用browser_search_google)
- 每个变体应使用不同的工具组合
- 优先选择更智能、更复杂的工具 (如browser_use_execute_task而非browser_search_google)
- 展示系统完整的工具生态，而不是局限于简单工具

示例变体思路：
- 如果原始是"搜索大学信息"，变体可以是：
  * "使用深度研究工具分析全球顶尖大学的排名趋势" (deepsearch)
  * "通过浏览器自动化收集多所大学的官网数据" (browser_use_execute_task)
- 如果原始是"执行Python代码"，变体可以是：
  * "分析Python项目中的函数定义和依赖关系" (list_code_definitions)
  * "自动化安装和测试Python包的兼容性" (microsandbox_install_package)

返回JSON格式：
{{
    "variants": [
        {{
            "question": "具体的变体任务描述",
            "expected_answer": "预期答案类型描述", 
            "reasoning_steps": ["步骤1", "步骤2"],
            "semantic_relation": "与原始任务的语义关系说明",
            "complexity_level": "简单|中等|困难",
            "required_tools": ["基于任务特性智能选择的工具"],
            "creativity_explanation": "变体生成的创意思路和工具选择理由",
            "domain": "任务领域"
        }}
    ]
}}"""
    
    async def generate_step_variants(self, step: AtomicStep, max_variants: int = 3) -> List[Dict[str, Any]]:
        """为原子步骤生成LLM驱动的语义变体"""
        try:
            prompt = self.semantic_variant_prompt.format(
                operation=step.operation,
                content=step.content,
                domain=step.domain,
                tool_name=step.tool_name or "通用工具",
                max_variants=max_variants
            )
            
            # 调用LLM生成变体 - 使用系统标准的_call_api方法
            messages = [{"role": "user", "content": prompt}]
            response = await self.llm_client._call_api(messages, timeout=60)
            
            # 解析LLM响应
            variants = self._parse_variant_response(response, step, max_variants)
            
            logger.info(f"✨ 为步骤 {step.step_id} 生成了 {len(variants)} 个LLM驱动的变体")
            return variants
            
        except Exception as e:
            logger.error(f"❌ LLM变体生成失败: {e}")
            # 回退到简单变体
            return self._generate_fallback_variants(step, max_variants)
    
    def _parse_variant_response(self, response: str, step: AtomicStep, max_variants: int) -> List[Dict[str, Any]]:
        """解析LLM响应并转换为变体格式"""
        try:
            # 提取JSON部分
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                parsed_data = json.loads(json_str)
                
                variants = []
                for i, variant_data in enumerate(parsed_data.get("variants", [])[:max_variants]):
                    variant = {
                        "question": variant_data.get("question", f"变体任务{i+1}"),
                        "expected_answer": variant_data.get("expected_answer", "变体任务的预期答案"),
                        "task_type": "tool_required",
                        "domain": variant_data.get("domain", step.domain),
                        "difficulty": variant_data.get("complexity_level", "中等"),
                        "required_tools": variant_data.get("required_tools", step.requires_tools),
                        "reasoning_steps": variant_data.get("reasoning_steps", [f"执行{variant_data.get('question', '变体任务')}"]),
                        "relation_pattern": "llm_semantic_variant",
                        "creativity_level": str(4 + i),  # LLM变体创造性较高
                        "creativity_explanation": variant_data.get("creativity_explanation", "LLM生成的语义变体"),
                        "reverse_reasoning": f"基于原始步骤'{step.operation}'的语义联想",
                        "entity_generalization": variant_data.get("semantic_relation", "语义扩展"),
                        "semantic_relation": variant_data.get("semantic_relation", "与原始任务语义相关")
                    }
                    variants.append(variant)
                
                return variants
            else:
                raise ValueError("响应中没有找到有效的JSON格式")
                
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"⚠️ LLM变体响应解析失败: {e}")
            return self._generate_fallback_variants(step, max_variants)
    
    def _generate_fallback_variants(self, step: AtomicStep, max_variants: int) -> List[Dict[str, Any]]:
        """生成回退变体（智能的基于规则的变体）"""
        variants = []
        
        # 基于原始工具智能推荐新工具的映射 - 增强工具多样化
        tool_diversification_map = {
            "browser_search_google": ["deepsearch", "browser_use_execute_task", "browser_extract_content"],
            "microsandbox_execute": ["search_file_content", "list_code_definitions", "microsandbox_install_package"],
            "deepsearch": ["browser_use_execute_task", "search_file_content", "browser_navigate"],
            "browser_extract_content": ["browser_use_execute_task", "deepsearch", "browser_navigate"],
            "browser_use_execute_task": ["deepsearch", "browser_extract_content", "search_file_content"],
            "browser_navigate": ["browser_use_execute_task", "browser_extract_content", "deepsearch"],
            "search_file_content": ["list_code_definitions", "microsandbox_execute", "deepsearch"],
            "list_code_definitions": ["search_file_content", "microsandbox_execute", "microsandbox_install_package"],
            "microsandbox_install_package": ["microsandbox_execute", "search_and_install_tools", "list_code_definitions"],
            "memory_staging": ["microsandbox_execute", "search_file_content", "list_code_definitions"],
            "search_and_install_tools": ["microsandbox_install_package", "list_code_definitions", "search_file_content"]
        }
        
        # 基于领域的智能变体模式 - 增强工具多样化
        domain_patterns = {
            "教育": [
                ("深度研究{content}的教育价值和影响", ["deepsearch"]),
                ("通过浏览器自动化收集{content}的官方信息", ["browser_use_execute_task"]),
                ("分析{content}相关的学术代码和文档", ["list_code_definitions"]),
                ("智能导航并提取{content}的详细内容", ["browser_navigate", "browser_extract_content"])
            ],
            "金融": [
                ("使用代码分析{content}的市场数据趋势", ["microsandbox_execute"]),
                ("深度研究{content}的金融政策影响", ["deepsearch"]),
                ("自动化获取{content}的实时金融信息", ["browser_use_execute_task"]),
                ("搜索并安装{content}相关的金融分析工具", ["search_and_install_tools"])
            ],
            "科学研究": [
                ("执行{content}相关的数据分析代码", ["microsandbox_execute"]),
                ("深度研究{content}领域的最新文献", ["deepsearch"]),
                ("分析{content}项目的代码结构和依赖", ["search_file_content"]),
                ("安装并测试{content}研究所需的工具包", ["microsandbox_install_package"])
            ],
            "编程": [
                ("智能分析{content}的代码定义和结构", ["list_code_definitions"]),
                ("深度研究{content}的最佳实践和案例", ["deepsearch"]),
                ("自动化安装{content}开发环境和依赖", ["microsandbox_install_package"]),
                ("搜索{content}相关的开发工具和库", ["search_and_install_tools"])
            ]
        }
        
        # 获取当前领域的变体模式，如果没有则使用通用模式 - 增强工具多样化
        patterns = domain_patterns.get(step.domain, [
            ("深度研究{content}的核心特征和趋势", ["deepsearch"]),
            ("通过浏览器自动化收集{content}的详细信息", ["browser_use_execute_task"]),
            ("使用代码工具分析{content}的数据模式", ["microsandbox_execute"]),
            ("搜索{content}相关的文件内容和结构", ["search_file_content"]),
            ("分析{content}的代码定义和架构", ["list_code_definitions"]),
            ("自动化安装{content}相关的工具和依赖", ["search_and_install_tools"])
        ])
        
        # 如果有原始工具，尝试多样化工具选择
        if step.tool_name and step.tool_name in tool_diversification_map:
            suggested_tools = tool_diversification_map[step.tool_name]
            # 将建议的工具融入到变体中
            for i, (pattern_template, default_tools) in enumerate(patterns[:max_variants]):
                if i < len(suggested_tools):
                    selected_tools = [suggested_tools[i]]
                else:
                    selected_tools = default_tools
                    
                pattern = pattern_template.format(content=step.content)
                variant = {
                    "question": pattern,
                    "expected_answer": f"关于{step.content}的{['深度分析', '自动化处理', '数据分析'][i % 3]}结果",
                    "task_type": "tool_required",
                    "domain": step.domain,
                    "difficulty": "中等",
                    "required_tools": selected_tools,
                    "reasoning_steps": [f"使用{selected_tools[0]}执行{pattern}"],
                    "relation_pattern": "intelligent_fallback_variant",
                    "creativity_level": str(3 + i),
                    "creativity_explanation": f"智能回退变体：从{step.tool_name}扩展到{selected_tools[0]}，{pattern}",
                    "reverse_reasoning": f"基于原始步骤'{step.operation}'的工具多样化扩展",
                    "entity_generalization": f"工具多样化：{step.tool_name} -> {selected_tools[0]}"
                }
                variants.append(variant)
        else:
            # 没有原始工具时，使用标准变体
            for i, (pattern_template, default_tools) in enumerate(patterns[:max_variants]):
                pattern = pattern_template.format(content=step.content)
                variant = {
                    "question": pattern,
                    "expected_answer": f"关于{step.content}的{['研究', '分析', '处理'][i]}结果",
                    "task_type": "tool_required",
                    "domain": step.domain,
                    "difficulty": "中等",
                    "required_tools": default_tools,
                    "reasoning_steps": [f"使用{default_tools[0]}执行{pattern}"],
                    "relation_pattern": "domain_fallback_variant",
                    "creativity_level": str(2 + i),
                    "creativity_explanation": f"领域回退变体：{pattern}",
                    "reverse_reasoning": f"基于原始步骤'{step.operation}'的领域特定扩展",
                    "entity_generalization": f"领域特定变体生成：{step.domain}"
                }
                variants.append(variant)
        
        return variants


# 保留StepVariant数据类以维护兼容性，但标记为弃用
@dataclass 
class StepVariant:
    """步骤变体数据结构（已弃用，保留以维护兼容性）"""
    variant_id: str
    base_step: AtomicStep
    variant_operation: str
    variant_content: str
    variant_domain: str
    substitution_mapping: Dict[str, str]
    creativity_level: int
    generated_at: datetime
    
    def to_task_dict(self) -> Dict[str, Any]:
        """转换为任务格式"""
        return {
            "question": self.variant_operation,
            "expected_answer": f"基于{self.variant_domain}领域的{self.variant_content}",
            "task_type": "tool_required",
            "domain": self.variant_domain,
            "difficulty": self.base_step.complexity,
            "required_tools": self.base_step.requires_tools,
            "reasoning_steps": [f"执行{self.variant_operation}", f"获取{self.variant_content}"],
            "relation_pattern": f"step_variant_from_{self.base_step.step_type}",
            "entity_generalization": str(self.substitution_mapping),
            "creativity_level": str(self.creativity_level),
            "creativity_explanation": f"基于真实轨迹步骤的变体生成，原始步骤：{self.base_step.operation}",
            "reverse_reasoning": f"从轨迹步骤'{self.base_step.operation}'衍生出变体'{self.variant_operation}'"
        }


class EnhancedTrajectoryBasedTaskGenerator:
    """增强的基于轨迹的任务生成器"""
    
    def __init__(self, llm_client, validator):
        self.step_extractor = TrajectoryStepExtractor()
        self.step_validator = AtomicStepValidator(llm_client, validator)
        self.variant_generator = LLMDrivenVariantGenerator(llm_client)
        self.generated_tasks_cache: Set[str] = set()  # 防重复
    
    async def generate_evidence_based_tasks(self, trajectories: List[Dict], max_tasks: int = 10) -> List[Dict]:
        """生成基于证据的任务 - 混合直接转换和LLM变体"""
        all_tasks = []
        direct_tasks = []  # 直接从原子步转换的任务
        variant_tasks = []  # LLM变体任务
        
        logger.info(f"🔄 开始基于 {len(trajectories)} 个轨迹生成有依据的任务")
        
        for trajectory in trajectories:
            if len(all_tasks) >= max_tasks:
                break
            
            try:
                # 步骤1：提取原子步
                atomic_steps = self.step_extractor.extract_atomic_steps(trajectory)
                logger.debug(f"📋 从轨迹 {trajectory.get('task_id', 'unknown')} 提取了 {len(atomic_steps)} 个原子步")
                
                for step in atomic_steps:
                    if len(all_tasks) >= max_tasks:
                        break
                    
                    # 步骤2：验证原子性并修改（如果需要）
                    is_atomic, direct_task = await self.step_validator.validate_and_fix_atomicity(step)
                    
                    # 防重复检查
                    task_signature = f"{direct_task['question']}_{direct_task['domain']}"
                    if task_signature not in self.generated_tasks_cache:
                        self.generated_tasks_cache.add(task_signature)
                        direct_tasks.append(direct_task)
                        
                        logger.debug(f"✅ 生成直接任务: {direct_task['question'][:50]}... (原子性: {'通过' if is_atomic else 'LLM修复'})")
                    
                    # 步骤3：生成LLM驱动的变体（如果还有空间）
                    if len(all_tasks) + len(direct_tasks) < max_tasks:
                        try:
                            variants = await self.variant_generator.generate_step_variants(step, max_variants=2)
                            
                            for variant in variants:
                                if len(all_tasks) + len(direct_tasks) + len(variant_tasks) >= max_tasks:
                                    break
                                
                                # 防重复检查
                                variant_signature = f"{variant['question']}_{variant['domain']}"
                                if variant_signature not in self.generated_tasks_cache:
                                    self.generated_tasks_cache.add(variant_signature)
                                    variant_tasks.append(variant)
                                    
                                    logger.debug(f"✨ 生成LLM变体: {variant['question'][:50]}...")
                                    
                        except Exception as e:
                            logger.warning(f"⚠️ 为步骤 {step.step_id} 生成变体失败: {e}")
                            continue
                
            except Exception as e:
                logger.error(f"❌ 处理轨迹 {trajectory.get('task_id', 'unknown')} 时出错: {e}")
                continue
        
        # 步骤4：合并任务（维持比例）
        target_direct = min(len(direct_tasks), max_tasks // 2)  # 直接任务占50%
        target_variant = min(len(variant_tasks), max_tasks - target_direct)  # 变体任务占剩余
        
        all_tasks.extend(direct_tasks[:target_direct])
        all_tasks.extend(variant_tasks[:target_variant])
        
        logger.info(f"🎉 基于轨迹证据生成了 {len(all_tasks)} 个任务 (直接任务: {target_direct}, LLM变体: {target_variant})")
        return all_tasks


# 保留原来的TrajectoryBasedTaskGenerator以维护向下兼容性
class TrajectoryBasedTaskGenerator:
    """基于轨迹的任务生成器（兼容性保留版本）"""
    
    def __init__(self):
        self.step_extractor = TrajectoryStepExtractor()
        self.generated_tasks_cache: Set[str] = set()  # 防重复
        logger.warning("⚠️ 使用了兼容性版本的TrajectoryBasedTaskGenerator，建议升级到EnhancedTrajectoryBasedTaskGenerator")
    
    def generate_evidence_based_tasks(self, trajectories: List[Dict], max_tasks: int = 10) -> List[Dict]:
        """生成基于证据的任务（简化版本）"""
        all_tasks = []
        tasks_generated = 0
        
        logger.info(f"🔄 开始基于 {len(trajectories)} 个轨迹生成有依据的任务（兼容性模式）")
        
        for trajectory in trajectories:
            if tasks_generated >= max_tasks:
                break
            
            try:
                # 1. 提取原子步骤
                atomic_steps = self.step_extractor.extract_atomic_steps(trajectory)
                
                # 2. 直接转换为任务（无LLM验证）
                for step in atomic_steps:
                    if tasks_generated >= max_tasks:
                        break
                    
                    # 简单转换
                    task_dict = {
                        "question": step.operation,
                        "expected_answer": f"基于{step.domain}领域的{step.content}",
                        "task_type": "tool_required",
                        "domain": step.domain,
                        "difficulty": step.complexity,
                        "required_tools": step.requires_tools,
                        "reasoning_steps": [f"执行{step.operation}"],
                        "relation_pattern": "simple_step_conversion",
                        "creativity_level": "1",
                        "creativity_explanation": f"简单转换：{step.operation}",
                        "reverse_reasoning": f"轨迹步骤：{step.step_id}",
                        "entity_generalization": f"步骤类型：{step.step_type}"
                    }
                    
                    # 防重复检查
                    task_signature = f"{task_dict['question']}_{task_dict['domain']}"
                    if task_signature not in self.generated_tasks_cache:
                        self.generated_tasks_cache.add(task_signature)
                        all_tasks.append(task_dict)
                        tasks_generated += 1
                        
                        logger.debug(f"✨ 生成简单任务: {task_dict['question'][:50]}...")
                
            except Exception as e:
                logger.error(f"❌ 处理轨迹 {trajectory.get('task_id', 'unknown')} 时出错: {e}")
                continue
        
        logger.info(f"🎉 基于轨迹证据生成了 {len(all_tasks)} 个任务（兼容性模式）")
        return all_tasks


class AtomicStepValidator:
    """原子步验证器 - 使用LLM验证和修改原子性"""
    
    def __init__(self, llm_client, validator):
        self.llm_client = llm_client
        self.validator = validator
        
        # 原子性修复的Prompt模板
        self.atomicity_fix_prompt = """你是一个任务原子性专家。以下原子步骤未通过原子性检查，请将其修改为符合原子性要求的任务。

原始步骤：{operation}
内容：{content}
原子性问题：{validation_issues}

原子性要求：
1. 任务只能包含一个明确的动作
2. 不能分解为多个独立的子任务
3. 可以一次性完成
4. 描述中不包含"然后"、"接着"、"同时"等连接词

请将原始步骤修改为符合原子性的任务：

返回JSON格式：
{{
    "fixed_question": "修改后的原子任务描述",
    "expected_answer": "预期答案",
    "reasoning_steps": ["执行步骤"],
    "required_tools": ["{tool_name}"],
    "fix_explanation": "修改说明",
    "domain": "{domain}",
    "difficulty": "{complexity}"
}}"""
    
    async def validate_and_fix_atomicity(self, step: AtomicStep) -> Tuple[bool, Dict[str, Any]]:
        """验证原子步的原子性，不符合则LLM修改"""
        try:
            # 使用TaskValidator检查原子性
            atomicity_check = await self.validator._check_atomicity(step.operation)
            
            if atomicity_check:
                # 直接转换为原子任务
                logger.debug(f"✅ 原子步 {step.step_id} 通过原子性检查")
                return True, self._convert_step_to_task(step)
            else:
                # LLM修改为符合原子性的任务
                logger.info(f"🔧 原子步 {step.step_id} 需要原子性修改")
                fixed_task = await self._llm_fix_atomicity(step, "未通过原子性检查")
                return False, fixed_task
                
        except Exception as e:
            logger.error(f"❌ 验证原子步 {step.step_id} 时出错: {e}")
            # 出错时直接转换
            return True, self._convert_step_to_task(step)
    
    def _convert_step_to_task(self, step: AtomicStep) -> Dict[str, Any]:
        """将原子步直接转换为任务格式"""
        return {
            "question": step.operation,
            "expected_answer": f"基于{step.domain}领域的{step.content}",
            "task_type": "tool_required",
            "domain": step.domain,
            "difficulty": step.complexity,
            "required_tools": step.requires_tools,
            "reasoning_steps": [f"执行{step.operation}"],
            "relation_pattern": "direct_atomic_step",
            "creativity_level": "1",  # 直接转换的创造性最低
            "creativity_explanation": f"直接从轨迹步骤转换：{step.operation}",
            "reverse_reasoning": f"原始轨迹步骤：{step.step_id}",
            "entity_generalization": f"原子步骤类型：{step.step_type}，工具：{step.tool_name}"
        }
    
    async def _llm_fix_atomicity(self, step: AtomicStep, validation_issues: str) -> Dict[str, Any]:
        """使用LLM修复原子性问题"""
        try:
            prompt = self.atomicity_fix_prompt.format(
                operation=step.operation,
                content=step.content,
                validation_issues=validation_issues,
                tool_name=step.tool_name or "通用工具",
                domain=step.domain,
                complexity=step.complexity
            )
            
            # 调用LLM - 使用系统标准的_call_api方法
            messages = [{"role": "user", "content": prompt}]
            response = await self.llm_client._call_api(messages, timeout=60)
            
            # 解析LLM响应
            try:
                # 提取JSON部分
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response[json_start:json_end]
                    fixed_data = json.loads(json_str)
                    
                    # 补充必要字段
                    result = {
                        "question": fixed_data.get("fixed_question", step.operation),
                        "expected_answer": fixed_data.get("expected_answer", f"修复后的{step.content}"),
                        "task_type": "tool_required",
                        "domain": fixed_data.get("domain", step.domain),
                        "difficulty": fixed_data.get("difficulty", step.complexity),
                        "required_tools": fixed_data.get("required_tools", step.requires_tools),
                        "reasoning_steps": fixed_data.get("reasoning_steps", [f"执行{step.operation}"]),
                        "relation_pattern": "llm_fixed_atomic_step",
                        "creativity_level": "2",  # LLM修复的创造性稍高
                        "creativity_explanation": f"LLM修复原子性：{fixed_data.get('fix_explanation', '修复原子性问题')}",
                        "reverse_reasoning": f"原始步骤：{step.operation} -> 修复后：{fixed_data.get('fixed_question', step.operation)}",
                        "entity_generalization": f"原子性修复：{validation_issues}"
                    }
                    
                    logger.info(f"🔧 LLM成功修复原子步 {step.step_id}")
                    return result
                    
                else:
                    raise ValueError("LLM响应中没有找到有效的JSON")
                    
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"⚠️ LLM响应解析失败: {e}, 使用回退方案")
                return self._create_fallback_fixed_task(step, validation_issues)
                
        except Exception as e:
            logger.error(f"❌ LLM修复原子性失败: {e}")
            return self._create_fallback_fixed_task(step, validation_issues)
    
    def _create_fallback_fixed_task(self, step: AtomicStep, validation_issues: str) -> Dict[str, Any]:
        """创建回退的修复任务"""
        # 简单的原子性修复：提取第一个动作词
        operation_words = step.operation.split()
        if operation_words:
            first_action = operation_words[0]
            simplified_operation = f"{first_action}相关信息"
        else:
            simplified_operation = step.operation
            
        return {
            "question": simplified_operation,
            "expected_answer": f"基于{step.domain}的{step.content}",
            "task_type": "tool_required",
            "domain": step.domain,
            "difficulty": step.complexity,
            "required_tools": step.requires_tools,
            "reasoning_steps": [f"执行{simplified_operation}"],
            "relation_pattern": "fallback_fixed_atomic_step",
            "creativity_level": "1",
            "creativity_explanation": f"回退修复原子性：{validation_issues}",
            "reverse_reasoning": f"简化原始步骤：{step.operation}",
            "entity_generalization": "回退原子性修复"
        }