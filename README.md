# 🚀 Agent数据构建基础设施平台

一个高性能、生产就绪的Agent数据收集和处理平台，支持推理、代码执行和Web导航任务的大规模并行处理。

## ✨ 核心特性

- 🏗️ **一键部署** - 3条命令启动完整系统
- 🔒 **轻量沙盒** - nsjail安全隔离，镜像仅80MB
- 🧠 **智能缓存** - 重复任务缓存，减少50%资源消耗
- 📊 **完整监控** - Prometheus + Grafana实时监控
- 🔄 **自动恢复** - 任务失败自动重试和恢复
- 📈 **水平扩展** - 支持多实例负载均衡
- 🎯 **分类处理** - 推理、代码和Web任务分流处理
- 🤖 **推理运行时** - 集成LLM的智能推理和工具调用
- 📈 **状态管理** - 完整的浏览器状态跟踪和错误恢复

## 🏗️ 系统架构

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────────┐
│   Task Queue    │    │   Dispatcher    │    │      Runtimes           │
│   (Redis)       │◄──►│   (Core)        │◄──►│ Reasoning/Sandbox/Web   │
└─────────────────┘    └─────────────────┘    └─────────────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Monitoring    │    │   Load Balancer │    │   Output Store  │
│ (Prometheus)    │    │   (Auto-scale)  │    │ (Trajectories)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🚀 快速开始

### 前置要求

- Docker >= 20.0
- Docker Compose >= 1.28
- 8GB+ RAM (推荐)
- 20GB+ 磁盘空间

### 一键部署

```bash
# 1. 克隆项目
git clone <repository-url>
cd agent-data-platform

# 2. 构建镜像
./build.sh

# 3. 启动服务
./deploy.sh

# 4. 监控进度
watch -n5 'echo "完成任务数: $(ls output/trajectories 2>/dev/null | wc -l)"'
```

### 验证部署

```bash
# 检查服务状态
docker-compose ps

# 检查健康状态
curl http://localhost:8001/health

# 查看实时指标
curl http://localhost:8001/metrics

# 执行冒烟测试
./smoke_test.sh
```

## 📋 任务配置

### 任务文件格式 (tasks.jsonl)

```json
{"task_id": "reasoning_001", "task_type": "reasoning", "description": "研究PyTorch和TensorFlow的差异", "expected_tools": ["browser", "python_executor"], "max_steps": 10}
{"task_id": "code_001", "task_type": "code", "description": "计算斐波那契数列", "expected_tools": ["python_executor"], "max_steps": 5}
{"task_id": "web_001", "task_type": "web", "description": "搜索技术文档", "expected_tools": ["browser"], "max_steps": 8}
```

### 支持的任务类型

#### 推理任务 ⭐ NEW
- **类型**: `reasoning`
- **工具**: `browser`, `python_executor`, `complete_task`
- **特点**: LLM驱动的智能推理，支持多工具组合调用
- **用例**: 研究分析、数据收集与处理、复杂问题解决
- **状态管理**: 完整的浏览器状态跟踪和错误恢复

#### 代码执行任务
- **类型**: `code`
- **工具**: `python_executor`
- **特点**: 安全沙盒环境，支持Python代码执行
- **用例**: 数据处理、算法验证、API调用

#### Web导航任务
- **类型**: `web`
- **工具**: `browser`
- **特点**: Playwright驱动，支持现代Web应用
- **用例**: 数据抓取、表单填写、页面交互

## 🔧 配置选项

### 环境变量

```bash
# Redis配置
REDIS_URL=redis://redis:6379
REDIS_MAX_CONNECTIONS=20

# 任务配置
TASK_FILE=/app/tasks.jsonl
MAX_CONCURRENT_TASKS=10
TASK_TIMEOUT=300

# 缓存配置
ENABLE_CACHE=true
CACHE_TTL=3600

# 监控配置
METRICS_PORT=8001
HEALTH_CHECK_INTERVAL=30
```

### 性能调优

```bash
# 扩展运行时实例
docker-compose up -d --scale sandbox-runtime=4 --scale reasoning-runtime=2

# 调整并发限制
export MAX_CONCURRENT_TASKS=20

# 优化内存使用
export MEMORY_LIMIT=2g
```

## 📊 监控和运维

### 监控面板

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)
- **Metrics API**: http://localhost:8001/metrics

### 关键指标

```bash
# 任务完成数
tasks_completed_total

# 任务失败数
tasks_failed_total

# 队列大小
queue_size{queue="code"}
queue_size{queue="web"}
queue_size{queue="reasoning"}

# 缓存命中率
cache_hits_total / (cache_hits_total + cache_misses_total)

# 平均处理时间
task_duration_seconds
```

### 日常运维命令

```bash
# 查看服务状态
docker-compose ps

# 查看实时日志
docker-compose logs -f sandbox-runtime

# 检查队列状态
docker exec $(docker-compose ps -q redis) redis-cli xlen tasks:code

# 重启服务
docker-compose restart sandbox-runtime

# 清理资源
docker system prune -f
```

## 🧪 测试和验证

### 冒烟测试

```bash
# 执行完整冒烟测试
./smoke_test.sh

# 快速健康检查
curl http://localhost:8001/health
```

### 负载测试

```bash
# 执行负载测试 (50个代码任务 + 20个Web任务)
./load_test.sh

# 自定义负载测试
CODE_TASKS=100 WEB_TASKS=50 ./load_test.sh
```

### 性能基准

| 配置 | 吞吐量 | 内存使用 | CPU使用 |
|------|--------|----------|----------|
| 单实例 | 10-15 任务/分钟 | 2-4GB | 50-70% |
| 4实例 | 40-60 任务/分钟 | 6-8GB | 80-90% |
| 8实例 | 80-120 任务/分钟 | 12-16GB | 90-95% |

## 🔍 故障排查

### 常见问题

#### 1. 服务启动失败
```bash
# 检查端口占用
netstat -tulpn | grep -E ":(6379|8001|8002)"

# 检查磁盘空间
df -h

# 重建容器
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

#### 2. 任务执行卡住
```bash
# 检查挂起任务
docker exec $(docker-compose ps -q redis) redis-cli xpending tasks:code workers

# 重启运行时
docker-compose restart sandbox-runtime web-runtime
```

#### 3. 内存溢出
```bash
# 检查内存使用
docker stats --no-stream

# 限制内存使用
docker-compose down
export MEMORY_LIMIT=4g
docker-compose up -d
```

#### 4. Redis连接失败
```bash
# 测试连接
docker exec $(docker-compose ps -q redis) redis-cli ping

# 重启Redis
docker-compose restart redis
```

### 自动修复

```bash
# 执行自动修复脚本
./scripts/auto_fix.sh
```

## 📁 项目结构

```
agent-data-platform/
├── core/                    # 核心调度逻辑
│   ├── __init__.py
│   ├── interfaces.py        # 接口定义和数据结构
│   ├── dispatcher.py        # 任务分发器
│   ├── task_manager.py      # 任务管理
│   ├── llm_client.py        # LLM客户端集成
│   ├── browser_state_manager.py  # 浏览器状态管理
│   ├── cache.py            # 缓存管理
│   ├── metrics.py          # 指标收集
│   ├── router.py           # 路由管理
│   └── utils.py            # 工具函数
├── runtimes/               # 运行时实现
│   ├── reasoning/          # 智能推理运行时 ⭐ NEW
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── runtime.py      # 主运行时逻辑
│   │   └── tools/          # 工具集合
│   │       ├── __init__.py # 延迟加载管理
│   │       ├── browser_tool.py     # 浏览器工具
│   │       └── python_executor_tool.py  # Python执行器
│   ├── sandbox/            # 代码执行沙盒
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── runtime.py
│   └── web_navigator/      # Web导航运行时
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── runtime.py
│       └── browser_manager.py  # 浏览器管理
├── config/                 # 配置文件
│   ├── prometheus.yml
│   └── grafana/
│       └── dashboards/
├── scripts/               # 部署和验证脚本
│   ├── build.sh
│   ├── deploy.sh
│   ├── smoke_test.sh
│   ├── load_test.sh
│   └── validate_imports.py  # 导入验证脚本 ⭐ NEW
├── docs/                  # 文档目录
│   ├── 用户使用指南.md
│   ├── AGENT_IMPROVEMENT_PLAN.md
│   ├── BROWSER_TOOL_GUIDE.md
│   └── 外部API配置指南.md
├── output/                # 输出目录
│   └── trajectories/      # 任务轨迹
├── docker/                # Docker文件
│   └── reasoning.Dockerfile.fixed
├── docker-compose.yml     # 完整服务编排
├── docker-compose.minimal.yml  # 最小配置
├── Dockerfile            # 主服务镜像
├── requirements.txt      # Python依赖
├── tasks.jsonl          # 任务定义文件
└── README.md           # 项目文档
```

## 🔧 开发指南

### 添加新的运行时

1. 在 `runtimes/` 下创建新目录
2. 实现 `RuntimeInterface` 接口
3. 创建对应的 Dockerfile
4. 更新 docker-compose.yml

### 自定义任务类型

1. 在 `core/interfaces.py` 中定义新的任务类型
2. 在对应运行时中实现处理逻辑
3. 更新任务路由规则

### 扩展监控指标

1. 在运行时中添加新的 Prometheus 指标
2. 更新 Grafana 仪表板配置
3. 添加相应的告警规则

## 🤝 贡献指南

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- [Redis](https://redis.io/) - 高性能内存数据库
- [Playwright](https://playwright.dev/) - 现代Web自动化
- [nsjail](https://nsjail.dev/) - 轻量级沙盒
- [Prometheus](https://prometheus.io/) - 监控和告警
- [Grafana](https://grafana.com/) - 可视化仪表板

## 📞 支持

如有问题或建议，请：

1. 查看 [FAQ](docs/FAQ.md)
2. 搜索 [Issues](../../issues)
3. 创建新的 [Issue](../../issues/new)
4. 联系维护团队

---

**一句话总结**：复制代码，执行3条命令，即可获得一个完整的、生产级的Agent数据构建平台！ 🚀
