# Synthesis 手动触发指南

## 🎯 概述

synthesis服务现在支持**手动触发**模式，不再自动处理所有轨迹。用户可以根据需要选择性地触发合成操作。

## 🚀 触发方式

### 1. 命令行工具触发（推荐）

使用`core.synthesiscore.cli`包中的命令行工具：

```bash
# 查看服务状态
python -m core.synthesiscore.cli.trigger status

# 处理所有轨迹（包括已处理的）
python -m core.synthesiscore.cli.trigger full

# 只处理新的（未处理的）轨迹
python -m core.synthesiscore.cli.trigger new

# 处理指定轨迹文件
python -m core.synthesiscore.cli.trigger specific trajectory_20241220_001.json

# 生成新任务（基于已有本质）
python -m core.synthesiscore.cli.trigger generate --count 5

# 列出所有轨迹文件
python -m core.synthesiscore.cli.trigger list

# 查看数据库内容
python -m core.synthesiscore.cli.view

# 初始化数据库
python -m core.synthesiscore.cli.init_db

# 生成新任务
python -m core.synthesiscore.cli.generate --count 3
```

### 2. Redis命令触发

直接向Redis发送命令：

```bash
# 处理所有轨迹
redis-cli XADD synthesis:commands command trigger_synthesis

# 只处理新轨迹
redis-cli XADD synthesis:commands command process_trajectories

# 处理指定轨迹
redis-cli XADD synthesis:commands command "process_specific trajectory_file.json"

# 生成任务
redis-cli XADD synthesis:commands command generate_tasks count 3

# 查看状态
redis-cli XADD synthesis:commands command status
```

### 3. HTTP API触发

启动API服务（可选）：

```bash
# 在容器内或本地启动API
python -m core.synthesiscore.synthesis_api
```

然后使用HTTP请求：

```bash
# 查看API文档
curl http://localhost:8080/

# 获取状态
curl http://localhost:8080/status

# 触发完整处理
curl -X POST http://localhost:8080/trigger/full

# 只处理新轨迹
curl -X POST http://localhost:8080/trigger/new

# 处理指定文件
curl -X POST http://localhost:8080/trigger/specific \
  -H "Content-Type: application/json" \
  -d '{"filename": "trajectory_20241220_001.json"}'

# 生成任务
curl -X POST http://localhost:8080/generate \
  -H "Content-Type: application/json" \
  -d '{"count": 3}'
```

## 📊 服务状态监控

### 查看详细状态

```bash
python -m core.synthesiscore.cli.trigger status
```

输出示例：
```
📊 Synthesis Service Status:
==================================================
  synthesis_enabled: True
  database_ready: True
  total_essences: 4
  generated_tasks: 0
  essence_distribution: {'code': 2, 'web': 2}
  processed_trajectories: 11
  total_trajectory_files: 11
  unprocessed_count: 0
==================================================
```

### 监控服务日志

```bash
# 查看synthesis容器日志
docker-compose -f docker-compose.synthesis.yml logs -f synthesis
```

## 🔧 工作流程示例

### 典型使用流程

1. **启动服务**
   ```bash
   docker-compose -f docker-compose.synthesis.yml up -d
   ```

2. **检查状态**
   ```bash
   python -m core.synthesiscore.cli.trigger status
   ```

3. **列出轨迹文件**
   ```bash
   python -m core.synthesiscore.cli.trigger list
   ```

4. **处理新轨迹**
   ```bash
   python -m core.synthesiscore.cli.trigger new
   ```

5. **生成新任务**
   ```bash
   python -m core.synthesiscore.cli.trigger generate --count 3
   ```

### 选择性处理

如果只想处理特定轨迹：

```bash
# 先列出文件
python -m core.synthesiscore.cli.trigger list

# 选择处理指定文件
python -m core.synthesiscore.cli.trigger specific trajectory_20241220_143855.json
```

## 🛡️ 安全特性

1. **防重复处理**：已处理的轨迹会被标记，避免重复处理
2. **数据库完整性**：支持事务和重试机制
3. **错误恢复**：处理失败时不会影响其他轨迹
4. **资源控制**：手动触发避免资源浪费

## 🎛️ 高级配置

### 环境变量

```bash
# synthesis功能开关
SYNTHESIS_ENABLED=true

# 数据库路径
SYNTHESIS_DB=/app/output/synthesis.db

# Redis连接
REDIS_URL=redis://redis:6379

# LLM配置
GEMINI_API_KEY=your_key_here
```

### 批量操作

处理多个指定文件：

```bash
# 使用脚本循环处理
for file in trajectory_001.json trajectory_002.json; do
    python -m core.synthesiscore.cli.trigger specific "$file"
done
```

## 📈 性能优化

1. **分批处理**：对于大量轨迹，建议分批处理
2. **监控资源**：处理过程中监控CPU和内存使用
3. **数据库维护**：定期检查数据库大小和性能

## 🔍 故障排除

### 常见问题

1. **连接Redis失败**
   ```bash
   # 检查Redis状态
   docker-compose -f docker-compose.synthesis.yml ps redis
   ```

2. **数据库锁定**
   ```bash
   # 重启synthesis服务
   docker-compose -f docker-compose.synthesis.yml restart synthesis
   ```

3. **轨迹文件不存在**
   ```bash
   # 检查文件路径
   ls -la output/trajectories/
   ```

### 日志分析

```bash
# 查看错误日志
docker-compose -f docker-compose.synthesis.yml logs synthesis | grep -i error

# 查看处理进度
docker-compose -f docker-compose.synthesis.yml logs synthesis | grep -i "processed"
```

## 🎉 总结

新的手动触发机制提供了：

- ✅ **精确控制**：按需处理轨迹
- ✅ **资源节省**：避免不必要的自动处理  
- ✅ **灵活操作**：支持多种触发方式
- ✅ **状态透明**：实时监控处理状态
- ✅ **错误恢复**：健壮的错误处理机制

现在你可以完全控制何时进行轨迹合成，让整个流程更加可控和高效！

---

## 📝 常用命令速查表

### Docker Compose 操作

```bash
# 构建镜像
docker-compose -f docker-compose.synthesis.yml build

# 启动服务
docker-compose -f docker-compose.synthesis.yml up -d

# 停止服务
docker-compose -f docker-compose.synthesis.yml down

# 查看服务日志
docker-compose -f docker-compose.synthesis.yml logs -f synthesis

# 进入容器
docker-compose -f docker-compose.synthesis.yml exec synthesis bash
```

### Synthesis CLI 工具

```bash
# 查看服务状态
python -m core.synthesiscore.cli.trigger status

# 列出所有轨迹文件
python -m core.synthesiscore.cli.trigger list

# 处理所有轨迹
python -m core.synthesiscore.cli.trigger full

# 只处理新轨迹
python -m core.synthesiscore.cli.trigger new

# 处理指定轨迹
python -m core.synthesiscore.cli.trigger specific <filename>

# 生成新任务
python -m core.synthesiscore.cli.generate --count 2

# 查看数据库内容
python -m core.synthesiscore.cli.view

# 初始化数据库
python -m core.synthesiscore.cli.init_db
```

---

如需更多帮助，请查阅本文件前述详细说明或联系开发者。 