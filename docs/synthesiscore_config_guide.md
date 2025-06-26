# SynthesisCore 配置系统使用指南

## 概述

SynthesisCore 现在使用 YAML 配置文件系统，替代了之前的硬编码参数。这使得工程师可以更轻松地调试和优化任务生成质量。

## 配置文件位置

配置文件位于：`agent-data-platform/config/synthesiscore_config.yaml`

## 配置结构

### 1. 原子任务生成配置 (`atomic_generation`)

关键参数：
- `atomicity_verification_threshold`: **最重要的参数**，控制任务通过验证的最低分数
  - `0.8`: 非常严格，可能导致0个任务生成
  - `0.2`: 当前设置，适合复杂分析任务
  - `0.1`: 非常宽松，几乎所有任务都能通过

### 2. 验证引擎配置 (`verification`)

- `overall_quality_threshold`: 任务通过验证的综合质量分数门槛
- `dimension_weights`: 各验证维度的权重分配（总和必须为1.0）

### 3. 扩展配置 (`depth_extension`, `width_extension`)

控制任务扩展的各种阈值和参数。

## 使用方式

### 1. 在代码中使用配置

```python
from core.synthesiscore.enhanced_interfaces import EnhancedSynthesisConfig

# 创建配置实例
config = EnhancedSynthesisConfig()

# 访问配置
atomic_config = config.ATOMIC_GENERATION_CONFIG
threshold = config.get_config_value("atomic_generation", "atomicity_verification_threshold")
```

### 2. 动态调整配置

```python
# 临时调整参数（仅在内存中）
config.update_config_value("atomic_generation", "atomicity_verification_threshold", 0.15)

# 打印当前配置
config.print_current_config()

# 重新加载配置文件
config.reload_config()
```

### 3. 直接使用配置加载器

```python
from core.synthesiscore.config_loader import get_synthesis_config

# 获取全局配置实例
config_loader = get_synthesis_config()

# 验证配置
is_valid = config_loader.validate_config()

# 保存配置到文件
config_loader.save_config_to_file()
```

## 调试指南

### 生成任务数量为0的解决方案：

1. **降低原子性验证阈值**
   ```yaml
   atomic_generation:
     atomicity_verification_threshold: 0.1  # 从0.2降到0.1
   ```

2. **降低结论提取置信度**
   ```yaml
   atomic_generation:
     conclusion_extraction_confidence: 0.5  # 从0.7降到0.5
   ```

3. **增加结论提取数量**
   ```yaml
   atomic_generation:
     max_conclusions_per_corpus: 30  # 从20增到30
   ```

### 任务质量过低的解决方案：

1. **提高验证阈值**
   ```yaml
   atomic_generation:
     atomicity_verification_threshold: 0.4  # 从0.2提高到0.4
   
   verification:
     overall_quality_threshold: 0.85  # 从0.75提高到0.85
   ```

2. **调整验证维度权重**
   ```yaml
   verification:
     dimension_weights:
       executability: 0.30  # 增加可执行性权重
       difficulty: 0.20     # 增加难度权重
       # ... 其他维度
   ```

### 处理速度过慢的解决方案：

1. **增加并行处理**
   ```yaml
   atomic_generation:
     parallel_workers: 8  # 从4增到8
   ```

2. **减少候选任务数**
   ```yaml
   atomic_generation:
     max_candidate_atomic_tasks: 5  # 从10减到5
   ```

## 最佳实践

1. **逐步调整**: 每次只调整一个参数，观察效果
2. **备份配置**: 重大调整前备份原配置文件
3. **验证配置**: 使用 `validate_config()` 确保配置有效
4. **监控指标**: 关注生成数量、质量分数和处理时间

## 配置验证

系统会自动验证：
- 必要配置段是否存在
- 阈值是否在合理范围 [0.0, 1.0]
- 权重总和是否等于1.0

## 故障排除

如果配置文件损坏或不存在，系统会：
1. 记录错误日志
2. 自动使用默认配置
3. 继续正常运行

查看日志中的配置加载信息：
```
✅ SynthesisCore配置加载成功: /path/to/config.yaml
⚠️ 使用默认配置作为后备
```