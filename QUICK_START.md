# 🚀 Agent Data Platform 快速启动指南

## 📋 前置要求

### 必需环境
- **Docker** (version 20.0+) 
- **Docker Compose** (version 2.0+)
- **Git**
- **至少 8GB 内存** 和 **20GB 磁盘空间**

### API 密钥配置
需要配置至少一个大语言模型 API：

```bash
# Google Gemini（推荐）
export GEMINI_API_KEY="your_gemini_api_key"
export GEMINI_API_URL="https://generativelanguage.googleapis.com"

# 或 DeepSeek（备用）
export DEEPSEEK_API_KEY="your_deepseek_api_key" 
export DEEPSEEK_API_URL="https://api.deepseek.com"

# 或其他 OpenAI 兼容 API（备用）
export OPENAI_API_KEY="your_openai_api_key"
export OPENAI_API_BASE="https://api.openai.com/v1"
```

## 🎯 一键启动

### 方法一：使用启动脚本（推荐）

```bash
# 克隆项目
git clone <your-repo-url>
cd agent-data-platform

# 设置环境变量
export GEMINI_API_KEY="your_api_key"

# 一键启动整个平台
./scripts/start_platform.sh start
```

### 方法二：使用 Docker Compose

```bash
# 克隆项目
git clone <your-repo-url>
cd agent-data-platform

# 设置环境变量
export GEMINI_API_KEY="your_api_key"

# 启动平台
docker-compose up -d
```

## 📊 服务访问地址

启动完成后，可以通过以下地址访问各个服务：

| 服务 | 地址 | 说明 |
|------|------|------|
| 🌐 **任务分发 API** | http://localhost:8000 | 提交和管理任务 |
| 🔧 **ToolScore MCP** | ws://localhost:8080/websocket | 工具管理中心 |
| 🐍 **Python执行器** | ws://localhost:8081/mcp | Python代码执行 |
| 🌍 **浏览器导航器** | ws://localhost:8082/mcp | Web自动化操作 |
| 📊 **任务合成服务** | http://localhost:9000 | 任务学习和生成 |
| 📈 **监控面板** | http://localhost:9090 | Prometheus监控 |
| 📊 **仪表板** | http://localhost:3000 | Grafana仪表板 (admin/admin) |

## 🧪 快速测试

### 1. 检查服务状态

```bash
# 查看所有服务状态
./scripts/start_platform.sh status

# 或使用docker-compose
docker-compose ps
```

### 2. 提交测试任务

```bash
# Python代码执行任务
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "reasoning",
    "description": "请计算斐波那契数列的前10项",
    "requirements": ["使用Python代码计算", "输出结果列表"],
    "metadata": {"priority": "normal"}
  }'

# Web搜索任务
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "reasoning", 
    "description": "搜索最新的Python开发趋势",
    "requirements": ["访问搜索引擎", "获取相关信息", "总结要点"],
    "metadata": {"priority": "normal"}
  }'
```

### 3. 查看任务结果

```bash
# 查看任务状态（将TASK_ID替换为实际的任务ID）
curl http://localhost:8000/api/tasks/TASK_ID

# 查看执行轨迹
ls output/trajectories/
```

## 🔧 常用操作

### 查看日志

```bash
# 查看所有服务日志
./scripts/start_platform.sh logs

# 查看特定服务日志
./scripts/start_platform.sh logs toolscore
./scripts/start_platform.sh logs enhanced-reasoning-runtime
./scripts/start_platform.sh logs python-executor-server
```

### 停止服务

```bash
# 停止所有服务
./scripts/start_platform.sh stop

# 或使用docker-compose
docker-compose down
```

### 重启服务

```bash
# 重启整个平台
./scripts/start_platform.sh restart

# 重启特定服务
docker-compose restart enhanced-reasoning-runtime
```

### 清理环境

```bash
# 完全清理（删除所有容器、镜像、数据）
./scripts/start_platform.sh clean
```

## 🏗️ 系统架构

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   用户请求      │───▶│  任务分发器     │───▶│  Enhanced       │
│                 │    │  (8000)         │    │  Runtime        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                       │
                       ┌─────────────────┐            │
                       │   ToolScore     │◀───────────┘
                       │   MCP Server    │
                       │   (8080)        │
                       └─────────────────┘
                                │
                   ┌────────────┼────────────┐
                   │            │            │
         ┌─────────▼───┐ ┌──────▼──────┐ ┌──▼──────────┐
         │ Python      │ │ Browser     │ │ 其他        │
         │ Executor    │ │ Navigator   │ │ MCP Server  │
         │ (8081)      │ │ (8082)      │ │ ...         │
         └─────────────┘ └─────────────┘ └─────────────┘
```

## ❗ 故障排除

### 常见问题

1. **端口被占用**
   ```bash
   # 检查端口使用情况
   lsof -i :8000
   lsof -i :8080
   
   # 修改docker-compose.yml中的端口映射
   ```

2. **内存不足**
   ```bash
   # 检查Docker内存设置
   docker system info | grep Memory
   
   # 增加Docker Desktop内存限制
   ```

3. **API密钥未设置**
   ```bash
   # 确认环境变量已设置
   echo $GEMINI_API_KEY
   
   # 或创建.env文件
   echo "GEMINI_API_KEY=your_key" > .env
   ```

4. **服务启动失败**
   ```bash
   # 查看详细日志
   ./scripts/start_platform.sh logs [service_name]
   
   # 重新构建镜像
   docker-compose build --no-cache [service_name]
   ```

### 服务依赖关系

- `Redis` ← 所有服务依赖
- `ToolScore` ← MCP Servers 和 Runtime 依赖
- `MCP Servers` ← Runtime 依赖
- `Enhanced Runtime` ← Task Dispatcher 依赖

确保按顺序启动，或使用启动脚本自动处理依赖关系。

## 📚 进阶使用

- **API文档**: 访问 http://localhost:8000/docs 查看完整API文档
- **架构分析**: 查看 `ARCHITECTURE_ANALYSIS.md` 了解详细架构
- **自定义配置**: 编辑 `docker-compose.yml` 调整服务配置
- **添加工具**: 创建新的MCP Server扩展工具能力

## 🎉 成功！

如果所有服务都显示为 "✅ 运行中"，恭喜您已成功启动了完整的智能Agent平台！现在可以开始提交任务，体验AI驱动的自动化工作流程。 