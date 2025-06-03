# Synthesis系统 - 基于JSON文件存储

## 概述

Synthesis系统已成功重构，完全移除SQLite数据库依赖，改为使用轻量级的JSON文件存储。这种设计更加简洁、易于维护，并且避免了数据库锁定等问题。

## 核心特性

### ✅ 已实现功能

1. **JSON文件存储架构**
   - 任务本质存储：`/app/output/task_essences.json`
   - 生成任务记录：`/app/output/generated_tasks.json`
   - 轨迹处理状态：`/app/output/processed_trajectories.json`
   - 种子任务导出：`/app/seed_tasks.jsonl`

2. **自动轨迹监控**
   - 实时监控轨迹目录变化
   - 自动处理新生成的轨迹文件
   - 支持多目录监控

3. **智能任务本质提取**
   - LLM驱动的轨迹分析
   - 任务类型分类（code/web/reasoning）
   - 领域识别和复杂度评估

4. **种子数据自动导出**
   - 从任务本质生成标准种子任务
   - 智能推断预期工具和执行步数
   - 支持JSONL格式导出

5. **线程安全的文件操作**
   - 原子写入机制
   - 文件锁保护并发访问
   - 错误恢复和重试机制

## 系统架构

### 数据流图

```
轨迹文件 → 文件监控器 → 轨迹处理器 → LLM分析 → 任务本质 → JSON存储 → 种子导出
    ↓           ↓            ↓          ↓         ↓         ↓         ↓
trajectory.json  FileHandler  _process_trajectory  _extract_essence  _store_essence  seed_tasks.jsonl
```

### 存储结构

```
/app/output/
├── task_essences.json          # 任务本质数据库
├── generated_tasks.json        # 生成任务记录
├── processed_trajectories.json # 轨迹处理状态
└── trajectories/               # 输入轨迹目录

/app/seed_tasks.jsonl           # 导出的种子任务
```

## 配置说明

### 环境变量

```bash
# 基础配置
SYNTHESIS_ENABLED=true                    # 启用合成器
AUTO_MONITOR_TRAJECTORIES=true           # 自动轨迹监控
AUTO_EXPORT_SEEDS=true                   # 自动种子导出

# LLM配置
GEMINI_API_KEY=your_key                  # Gemini API密钥
DEEPSEEK_API_KEY=your_key                # DeepSeek API密钥
OPENAI_API_KEY=your_key                  # OpenAI API密钥

# Redis配置
REDIS_URL=redis://redis:6379             # Redis连接URL
```

### JSON文件格式

#### 1. 任务本质格式 (`task_essences.json`)

```json
[
  {
    "essence_id": "essence_1640995200_task_001",
    "task_type": "code",
    "domain": "algorithm",
    "query": "实现高效的快速排序算法并进行性能测试",
    "complexity_level": "medium",
    "success_pattern": {
      "duration": 15.5,
      "steps_count": 4,
      "key_features": ["算法实现", "性能测试", "数据结构"],
      "confidence": 0.92,
      "tools_used": ["python", "matplotlib"]
    },
    "extracted_at": "2024-01-15T10:30:00Z",
    "source_trajectory_id": "task_001"
  }
]
```

#### 2. 种子任务格式 (`seed_tasks.jsonl`)

```json
{"task_id": "seed_code_a1b2c3d4", "task_type": "code", "description": "实现高效的快速排序算法并进行性能测试", "expected_tools": ["python_executor", "matplotlib"], "max_steps": 10, "domain": "algorithm", "complexity": "medium", "confidence": 0.92, "source_essence_id": "essence_1640995200_task_001", "source_trajectory": "task_001", "extracted_at": "2024-01-15T10:30:00Z"}
```

## 部署指南

### Docker部署

```bash
# 1. 构建和启动服务
docker-compose -f docker-compose.synthesis.yml up -d

# 2. 查看日志
docker-compose -f docker-compose.synthesis.yml logs -f synthesis

# 3. 检查健康状态
curl http://localhost:8081/health
```

### 本地开发

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 设置环境变量
export SYNTHESIS_ENABLED=true
export AUTO_MONITOR_TRAJECTORIES=true
export AUTO_EXPORT_SEEDS=true

# 3. 启动合成器
python -m core.synthesiscore.synthesis
```

## 操作指南

### 手动触发命令

通过Redis发送命令控制synthesis行为：

```bash
# 1. 触发完整轨迹处理和种子导出
redis-cli XADD synthesis:commands '*' command trigger_synthesis

# 2. 只处理未处理的轨迹
redis-cli XADD synthesis:commands '*' command process_trajectories

# 3. 处理指定轨迹文件
redis-cli XADD synthesis:commands '*' command process_specific trajectory_001.json

# 4. 手动导出种子任务
redis-cli XADD synthesis:commands '*' command export_seeds

# 5. 启动/停止轨迹监控
redis-cli XADD synthesis:commands '*' command start_monitoring
redis-cli XADD synthesis:commands '*' command stop_monitoring

# 6. 查看系统状态
redis-cli XADD synthesis:commands '*' command status
```

### 监控和调试

```bash
# 查看处理状态
cat /app/output/processed_trajectories.json

# 查看任务本质数量
wc -l /app/output/task_essences.json

# 查看种子任务统计
wc -l /app/seed_tasks.jsonl

# 实时监控种子导出
tail -f /app/seed_tasks.jsonl
```

## 性能优化

### 文件操作优化

1. **原子写入**：使用临时文件+原子替换避免数据损坏
2. **文件锁**：防止并发访问冲突
3. **错误重试**：自动重试失败的文件操作

### 内存管理

1. **流式处理**：使用aiofiles进行异步文件IO
2. **分批处理**：限制单次处理的轨迹数量（最多10个）
3. **及时释放**：处理完成后立即释放内存

## 故障排除

### 常见问题

#### 1. JSON文件损坏
```bash
# 检查JSON格式
python -m json.tool /app/output/task_essences.json > /dev/null
# 修复：删除损坏文件，系统会自动重建
rm /app/output/task_essences.json
```

#### 2. 种子导出失败
```bash
# 检查权限
ls -la /app/seed_tasks.jsonl
# 手动触发导出
redis-cli XADD synthesis:commands '*' command export_seeds
```

#### 3. 轨迹监控停止
```bash
# 重启监控
redis-cli XADD synthesis:commands '*' command start_monitoring
# 检查目录权限
ls -la /app/output/trajectories/
```

### 日志分析

```bash
# 查看关键日志
docker logs synthesis 2>&1 | grep -E "(ERROR|✅|❌|📤)"

# 统计处理成功率
docker logs synthesis 2>&1 | grep "✅.*处理" | wc -l
```

## 升级说明

### 从SQLite迁移

原有的SQLite数据不会自动迁移。如需保留数据，请：

1. 导出SQLite中的任务本质数据
2. 转换为JSON格式
3. 导入到新的JSON文件中

### 向后兼容性

- Redis命令接口保持不变
- 种子任务格式保持兼容
- 环境变量配置向后兼容

## 贡献指南

### 开发环境

```bash
# 1. 克隆项目
git clone <repository>

# 2. 安装开发依赖
pip install -r requirements.txt
pip install pytest pytest-asyncio

# 3. 运行测试
python test_json_synthesis.py
```

### 代码规范

- 使用类型提示
- 添加详细的日志记录
- 确保线程安全
- 编写单元测试

---

## 总结

新的基于JSON文件的Synthesis系统具有以下优势：

1. **简化架构**：移除数据库依赖，降低系统复杂度
2. **高可靠性**：原子操作和错误恢复机制
3. **易于维护**：JSON格式便于查看和调试
4. **高性能**：避免数据库锁定，支持高并发
5. **良好扩展性**：模块化设计，易于添加新功能

系统已通过完整测试验证，可以安全部署到生产环境。 