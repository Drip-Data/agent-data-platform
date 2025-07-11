# Synthesis Prompt 模板系统

## 📖 概述

这是一个专门为 Synthesis 系统设计的模板化 Prompt 管理框架，旨在提高 Prompt 的可维护性、可读性和迭代效率。

## 🏗️ 架构设计

### 核心组件

```
prompts/
├── __init__.py              # 模块初始化和全局管理器
├── base.py                  # 基础框架和管理类
├── task_generation.py       # 任务生成相关模板
├── task_validation.py       # 任务验证相关模板
├── task_synthesis.py        # 任务合成相关模板
├── management.py            # 性能监控和管理工具
└── README.md               # 本文档
```

### 类层次结构

```
PromptTemplate           # 单个模板类
├── name: str           # 模板名称
├── template: str       # 模板内容
├── required_params     # 必需参数
├── optional_params     # 可选参数
└── render(**kwargs)    # 渲染方法

PromptModule (ABC)       # 模板模块抽象基类
└── get_templates()     # 返回模块中的所有模板

PromptManager           # 模板管理器
├── register_module()   # 注册模板模块
├── get_template()      # 获取模板
├── render_template()   # 渲染模板
└── get_usage_statistics() # 使用统计

EnhancedPromptManager   # 增强管理器（含性能监控）
├── render_template_with_monitoring()
├── render_and_call_llm()
└── get_performance_dashboard()
```

## 📝 模板类别

### 1. 任务生成模板 (TaskGenerationPrompts)

| 模板名称 | 功能描述 | 必需参数 | 可选参数 |
|---------|---------|---------|---------|
| `extract_conclusions` | 从轨迹数据提取结论 | `trajectory_data` | `max_conclusions=5` |
| `generate_atomic_tasks` | 基于结论生成原子任务 | `conclusion` | `max_tasks=3` |
| `generate_depth_extension` | 深度扩展任务 | `base_question`, `base_answer`, `task_type`, `domain` | - |
| `generate_width_extension` | 宽度扩展任务 | `atomic_tasks_list` | - |
| `optimize_task` | 优化任务质量 | `original_question`, `original_answer`, `task_type` | - |

### 2. 任务验证模板 (TaskValidationPrompts)

| 模板名称 | 功能描述 | 必需参数 | 可选参数 |
|---------|---------|---------|---------|
| `check_tool_necessity` | 检查工具必要性 | `question` | - |
| `check_reasoning_sufficiency` | 检查推理充分性 | `question` | - |
| `check_atomicity` | 检查任务原子性 | `question` | - |
| `validate_superset_relation` | 验证超集关系 | `base_input`, `superset_input` | - |
| `check_information_leakage` | 检查信息泄露 | `question`, `answer` | - |
| `comprehensive_quality_assessment` | 综合质量评估 | `question`, `answer`, `task_type`, `domain` | - |

### 3. 任务合成模板 (TaskSynthesisPrompts)

| 模板名称 | 功能描述 | 必需参数 | 可选参数 |
|---------|---------|---------|---------|
| `check_merge_reasonableness` | 检查合并合理性 | `component_questions`, `merged_question` | - |
| `validate_answer_combination` | 验证答案组合 | `component_answers`, `merged_answer` | - |
| `assess_task_complexity` | 评估任务复杂度 | `task_description` | - |
| `analyze_task_similarity` | 分析任务相似度 | `task_a`, `task_b` | - |
| `optimize_synthesis_strategy` | 优化合成策略 | `atomic_task_count`, `task_type_distribution`, etc. | 多个可选 |

## 🚀 使用指南

### 基础使用

```python
from core.synthesiscore.prompts import prompt_manager

# 渲染模板
result = prompt_manager.render_template(
    'check_tool_necessity',
    question='What is the current weather?'
)

# 使用完整名称（避免冲突）
result = prompt_manager.render_template(
    'task_validation.check_tool_necessity',
    question='What is the current weather?'
)
```

### 与 LLM 集成

```python
from core.synthesiscore.prompts.management import enhanced_prompt_manager

# 带性能监控的渲染
result, success, response_time = await enhanced_prompt_manager.render_template_with_monitoring(
    'extract_conclusions',
    trajectory_data=trajectory_data,
    max_conclusions=5
)

# 渲染并调用 LLM
response, success, response_time = await enhanced_prompt_manager.render_and_call_llm(
    'generate_atomic_tasks',
    llm_client,
    conclusion=conclusion_data
)
```

### 在 TaskValidator 中使用

```python
class TaskValidator:
    async def _check_tool_necessity(self, question: str) -> bool:
        prompt = prompt_manager.render_template(
            'task_validation.check_tool_necessity',
            question=question
        )
        
        messages = [{"role": "user", "content": prompt}]
        response = await self.llm_client._call_api(messages, timeout=30)
        
        # 解析响应...
```

### 在 SynthesisEngine 中使用

```python
class SynthesisEngine:
    async def _extract_conclusions_from_trajectories(self, trajectories_data):
        prompt = prompt_manager.render_template(
            'task_generation.extract_conclusions',
            trajectory_data=str(trajectories_data),
            max_conclusions=3
        )
        
        # 调用 LLM...
```

## 📊 性能监控

### 获取性能仪表板

```python
from core.synthesiscore.prompts.management import enhanced_prompt_manager

dashboard = enhanced_prompt_manager.get_performance_dashboard()

print(f"健康状态: {dashboard['health_status']}")
print(f"总体成功率: {dashboard['performance_metrics']['summary']['overall_success_rate']}")
```

### 性能指标

- **使用次数**: 每个模板的调用频率
- **成功率**: 模板渲染和 LLM 调用的成功率
- **响应时间**: 平均响应时间
- **错误统计**: 错误次数和类型
- **趋势分析**: 性能变化趋势

## 🔧 维护和扩展

### 添加新模板

1. 在对应的模块文件中添加模板定义
2. 更新 `_initialize_templates()` 方法
3. 更新模块信息中的类别列表

```python
templates["new_template"] = PromptTemplate(
    name="new_template",
    template="Your template content with {parameters}",
    description="Template description",
    prompt_type=PromptType.YOUR_TYPE,
    required_params=["param1"],
    optional_params={"param2": "default_value"}
)
```

### 添加新模块

1. 创建新的模块文件继承 `PromptModule`
2. 在 `__init__.py` 中注册模块
3. 实现 `get_templates()` 和 `get_module_info()` 方法

```python
class NewPromptModule(PromptModule):
    def get_templates(self) -> Dict[str, PromptTemplate]:
        # 返回模板字典
        
    def get_module_info(self) -> Dict[str, Any]:
        # 返回模块信息
```

### 模板最佳实践

1. **参数化**: 所有变量都应该参数化，避免硬编码
2. **描述清晰**: 提供详细的模板描述和参数说明
3. **JSON 格式**: 鼓励 LLM 返回结构化的 JSON 响应
4. **错误处理**: 考虑 LLM 响应格式不正确的情况
5. **版本控制**: 重要变更时更新版本号

## 📈 收益总结

### 1. 可维护性提升
- 集中管理所有 Prompt 模板
- 统一的参数验证和错误处理
- 版本控制和变更追踪

### 2. 开发效率提升
- 模板复用减少重复代码
- 参数化设计支持灵活定制
- 自动的使用统计和性能监控

### 3. 质量保证
- 模板验证确保参数完整性
- 性能监控识别问题模板
- A/B 测试支持（可扩展）

### 4. 团队协作
- 标准化的模板格式
- 清晰的文档和示例
- 模块化的组织结构

## 🔮 未来扩展

1. **A/B 测试框架**: 支持多版本模板对比测试
2. **自动优化**: 基于性能数据自动调优模板
3. **多语言支持**: 支持不同语言的模板版本
4. **缓存机制**: 缓存频繁使用的渲染结果
5. **实时监控**: 实时性能监控和告警

---

**注意**: 这是 Synthesis 系统的重要组成部分，任何模板变更都应该经过充分测试。