# 参数映射迁移计划

## 分析总结

基于对现有代码的深入分析，我发现了以下关键的参数处理组件：

### 现有参数映射架构

#### 1. **核心组件**

**UnifiedToolManager** (`core/unified_tool_manager.py`)
- 管理工具ID映射和动作验证
- 从YAML配置文件加载工具定义
- 提供工具调用验证方法 `validate_tool_call()`
- 处理旧版ID到新版ID的转换

**UnifiedMappingManager** (`core/config/unified_mapping_manager.py`)
- 专门处理工具ID、动作和参数映射
- 缓存映射表以提高性能
- 提供自动修正和错误建议功能
- 支持动态配置重载

**Enhanced Runtime** (`runtimes/reasoning/enhanced_runtime.py`)
- 解析LLM响应中的XML工具调用
- 硬编码参数映射：
  ```python
  param_mapping = {
      "browser_use": "query",
      "microsandbox": "code", 
      "deepsearch": "question"
  }
  ```
- 特殊工具参数映射：
  ```python
  special_tool_mapping = {
      ("browser_use", "browser_use_execute_task"): "task",
      ("browser_use", "browser_extract_content"): "goal"
  }
  ```

#### 2. **配置文件**
- `config/unified_tool_mappings.yaml`: 工具映射配置
- `config/unified_tool_definitions.yaml`: 工具定义配置

#### 3. **问题识别**

**硬编码问题**：
- Enhanced Runtime中有硬编码的参数映射
- 无法灵活处理复杂的多参数工具
- 简单的一对一映射无法满足JSON格式需求

**配置复杂性**：
- 多个配置文件管理不同层面的映射
- 参数映射逻辑分散在多个文件中
- 缺乏统一的JSON格式参数解析

## 迁移计划

### 阶段一：分析和设计 (✅ 已完成)
- [x] 分析现有参数映射架构
- [x] 识别硬编码问题
- [x] 制定JSON统一格式方案

### 阶段二：准备工作 
**预计时间**: 1-2小时

#### 2.1 备份现有代码
```bash
# 创建迁移分支
git checkout -b feature/json-parameter-unification

# 备份关键文件
cp runtimes/reasoning/enhanced_runtime.py runtimes/reasoning/enhanced_runtime.py.backup
cp core/unified_tool_manager.py core/unified_tool_manager.py.backup
cp core/config/unified_mapping_manager.py core/config/unified_mapping_manager.py.backup
```

#### 2.2 创建新的JSON参数解析器
**新文件**: `core/json_parameter_parser.py`
- 解析JSON格式的工具参数
- 验证参数完整性
- 提供参数映射功能

#### 2.3 更新配置文件
- 简化 `config/unified_tool_mappings.yaml`
- 移除复杂的参数别名映射（因为将使用JSON格式）

### 阶段三：核心功能实现
**预计时间**: 2-3小时

#### 3.1 实现JSON参数解析器
**功能**:
```python
class JSONParameterParser:
    def parse_tool_parameters(self, tool_name: str, action: str, json_params: str | dict) -> dict
    def validate_parameters(self, tool_name: str, action: str, params: dict) -> ValidationResult
    def get_required_parameters(self, tool_name: str, action: str) -> List[str]
```

#### 3.2 修改Enhanced Runtime
**目标**: 替换硬编码的参数映射
- 移除 `param_mapping` 和 `special_tool_mapping` 硬编码
- 集成新的JSON参数解析器
- 修改XML解析逻辑支持JSON格式

#### 3.3 更新Prompt Builder
**文件**: `core/llm/prompt_builders/reasoning_prompt_builder.py`
- 修改工具使用指导
- 添加JSON格式示例
- 更新工具参数说明

### 阶段四：清理旧代码
**预计时间**: 1小时

#### 4.1 需要清理的硬编码
**Enhanced Runtime**:
```python
# 删除这些硬编码映射
param_mapping = {
    "browser_use": "query",
    "microsandbox": "code",
    "deepsearch": "question"
}

special_tool_mapping = {
    ("browser_use", "browser_use_execute_task"): "task",
    ("browser_use", "browser_extract_content"): "goal"
}
```

#### 4.2 简化配置文件
**unified_tool_mappings.yaml**:
- 移除复杂的 `parameter_mappings` 部分
- 保留工具ID和动作映射
- 清理 `error_corrections` 中的参数相关部分

#### 4.3 更新UnifiedToolManager
- 移除参数映射相关方法
- 简化 `validate_tool_call()` 方法
- 集成新的JSON参数验证

### 阶段五：测试和验证
**预计时间**: 1-2小时

#### 5.1 单元测试
创建测试文件：
- `tests/test_json_parameter_parser.py`
- `tests/test_parameter_migration.py`

#### 5.2 集成测试
- 测试所有40个工具的JSON参数格式
- 验证向后兼容性
- 测试错误处理

#### 5.3 性能测试
- 比较新旧参数解析性能
- 验证内存使用情况

### 阶段六：文档更新
**预计时间**: 30分钟

#### 6.1 更新现有文档
- 更新 `docs/tool-parameter-unification-proposal.md`
- 添加迁移说明

#### 6.2 创建使用指南
- 新建 `docs/json-parameter-usage-guide.md`
- 提供工具使用示例

## 实施策略

### 渐进式迁移
1. **并行支持**: 同时支持旧格式和新JSON格式
2. **逐步替换**: 先实现新功能，再移除旧代码
3. **向后兼容**: 确保现有功能不受影响

### 风险控制
1. **代码备份**: 所有修改前先备份
2. **分支开发**: 在独立分支进行开发
3. **测试优先**: 每个阶段都进行充分测试

### 回滚计划
如果迁移出现问题：
1. 立即切回备份分支
2. 恢复备份的配置文件
3. 重新评估迁移策略

## 需要清理/修改的具体文件

### 高优先级 (必须修改)
1. **`runtimes/reasoning/enhanced_runtime.py`**
   - 移除硬编码的 `param_mapping`
   - 移除 `special_tool_mapping` 
   - 集成JSON参数解析器

2. **`core/llm/prompt_builders/reasoning_prompt_builder.py`**
   - 更新工具使用指导
   - 添加JSON格式说明

### 中优先级 (建议修改)
3. **`core/unified_tool_manager.py`**
   - 简化参数验证逻辑
   - 集成JSON参数解析

4. **`config/unified_tool_mappings.yaml`**
   - 简化参数映射配置
   - 移除复杂的别名映射

### 低优先级 (可选修改)
5. **`core/config/unified_mapping_manager.py`**
   - 简化参数映射功能
   - 优化缓存机制

## 成功标准

### 功能标准
- [ ] 所有40个工具支持JSON参数格式
- [ ] 参数验证功能正常
- [ ] 错误提示清晰明确
- [ ] 向后兼容现有功能

### 质量标准
- [ ] 代码覆盖率 > 90%
- [ ] 无性能回归
- [ ] 文档完整更新

### 用户体验标准
- [ ] 工具调用错误减少
- [ ] 参数格式统一
- [ ] 错误信息有用

---

**总预计时间**: 6-8小时  
**建议实施时间**: 1-2个工作日  
**风险等级**: 中等 (有完整回滚计划)

## 下一步行动

1. **立即行动**: 创建迁移分支并备份代码
2. **优先实现**: JSON参数解析器核心功能
3. **渐进测试**: 每个阶段完成后立即测试
4. **文档同步**: 代码修改的同时更新文档

这个计划确保了迁移的安全性和可控性，同时最大程度地减少对现有功能的影响。