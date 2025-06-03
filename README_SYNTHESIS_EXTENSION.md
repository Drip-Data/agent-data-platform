# 任务合成器扩展模块文档

## 📋 概述

本扩展模块为 [agent-data-platform](https://github.com/Drip-Data/agent-data-platform) 项目添加了智能任务合成功能，实现了轨迹分析与任务生成的能力。该模块设计为**独立可插拔**，可以选择性部署，不影响原有系统的正常运行。

## 🏗️ 架构设计

### 模块化架构
```
agent-data-platform/
├── 🟦 原始项目文件
│   ├── core/dispatcher.py          # 原项目调度器
│   ├── runtimes/                   # 原项目运行时
│   ├── docker-compose.yml          # 原项目编排文件
│   └── ...
│
├── 🟩 扩展模块（独立）
│   ├── core/synthesis.py           # 🆕 智能合成器
│   ├── core/synthesis_plugin.py    # 🆕 插件入口
│   ├── core/llm_client.py          # 🆕 统一LLM客户端
│   ├── scripts/generate_tasks.py   # 🆕 手动生成脚本
│   ├── scripts/deploy_synthesis.sh # 🆕 独立部署脚本
│   └── docker-compose.synthesis.yml # 🆕 扩展编排文件
│
└── 📚 文档和配置
    ├── README_SYNTHESIS_EXTENSION.md
    ├── CLEANUP_SUMMARY.md
    └── PROJECT_STRUCTURE.md
```

## 🚀 快速开始

### 1. 部署选项

#### 选项A: 仅部署扩展模块
```bash
# 仅启动合成器，不影响原有系统
./scripts/deploy_synthesis.sh synthesis
```

#### 选项B: 集成部署（推荐）
```bash
# 同时运行原系统和扩展模块
./scripts/deploy_synthesis.sh integrated
```

#### 选项C: 分别部署
```bash
# 先启动原系统
docker-compose up -d

# 再启动扩展模块
docker-compose -f docker-compose.synthesis.yml up -d
```

### 2. 环境配置

创建 `.env` 文件：
```bash
# ============================================================================
# 任务合成器环境配置
# ============================================================================

# 基础配置
LOG_LEVEL=INFO
REDIS_URL=redis://redis:6379

# 合成器配置
SYNTHESIS_ENABLED=true
SYNTHESIS_DB=/app/output/synthesis.db

# LLM API配置（根据需要配置）
GEMINI_API_KEY=your_gemini_key
DEEPSEEK_API_KEY=your_deepseek_key
OPENAI_API_KEY=your_openai_key

# VLLM配置（本地模型）
VLLM_URL=http://vllm:8000
```

## 🔧 核心功能

### 1. 智能任务合成器 (`core/synthesis.py`)

**功能特点：**
- 🧠 基于轨迹数据的智能分析
- 🔄 自动生成新的测试任务
- 📊 多维度质量评估
- 🎯 任务多样性保证

**主要方法：**
```python
class SimpleSynthesizer:
    async def analyze_trajectory(self, trajectory_data)  # 轨迹分析
    async def generate_tasks_manually(self, count=3)     # 手动生成
    async def evaluate_task_quality(self, task)         # 质量评估
    async def start()                                   # 启动服务
```

### 2. 插件化架构 (`core/synthesis_plugin.py`)

**特点：**
- 🔌 可插拔设计，独立运行
- ⚙️ 配置驱动，灵活控制
- 🔄 热插拔支持
- 📈 状态监控

**使用方式：**
```python
from core.synthesis_plugin import SynthesisPlugin

# 初始化插件
plugin = SynthesisPlugin()
await plugin.initialize()

# 启动服务
await plugin.start()

# 获取状态
status = plugin.get_status()
```

### 3. 统一LLM客户端 (`core/llm_client.py`)

**支持的模型：**
- 🟡 Gemini (Google)
- 🔵 DeepSeek
- 🟢 OpenAI GPT
- 🟣 本地VLLM

**特点：**
- 🔄 自动重试机制
- ⚡ 异步处理
- 🛡️ 错误处理
- 📊 统一接口

## 📂 文件清单

### 🆕 新增的独立文件（不修改原项目）

| 文件路径 | 描述 | 状态 |
|---------|------|------|
| `core/synthesis.py` | 智能任务合成器核心 | ✅ 独立 |
| `core/synthesis_plugin.py` | 插件化入口 | ✅ 独立 |
| `core/llm_client.py` | 统一LLM客户端 | ✅ 独立 |
| `core/cache.py` | 缓存管理 | ✅ 独立 |
| `core/metrics.py` | 指标监控 | ✅ 独立 |
| `core/router.py` | 路由管理 | ✅ 独立 |
| `core/task_manager.py` | 任务管理 | ✅ 独立 |
| `scripts/generate_tasks.py` | 手动任务生成 | ✅ 独立 |
| `scripts/deploy_synthesis.sh` | 独立部署脚本 | ✅ 独立 |
| `docker-compose.synthesis.yml` | 扩展编排配置 | ✅ 独立 |

### 🔄 修改了原项目的文件

| 文件路径 | 修改类型 | 建议处理 |
|---------|----------|----------|
| `docker-compose.yml` | 添加了synthesis服务 | 🔄 移至独立配置 |
| `core/interfaces.py` | 扩展了接口 | 🔄 提取为插件接口 |
| `core/dispatcher.py` | 集成了合成器 | 🔄 改为可选集成 |
| `runtimes/web_navigator/runtime.py` | 修复了执行问题 | ✅ 保留（bug修复） |

## 🔧 重构建议

### 1. 恢复原始docker-compose.yml

将synthesis服务移到独立配置文件：
```bash
# 备份当前配置
cp docker-compose.yml docker-compose.backup.yml

# 从原项目恢复干净的配置
git checkout origin/main -- docker-compose.yml
```

### 2. 创建集成钩子

在原项目中添加可选的合成器集成：
```python
# core/dispatcher.py 中添加
def load_synthesis_plugin(self):
    """可选加载合成器插件"""
    try:
        from .synthesis_plugin import SynthesisPlugin
        return SynthesisPlugin()
    except ImportError:
        logger.info("Synthesis plugin not available")
        return None
```

### 3. 使用环境变量控制

通过环境变量控制功能启用：
```bash
# 启用合成器
SYNTHESIS_ENABLED=true

# 禁用合成器（默认）
SYNTHESIS_ENABLED=false
```

## 🚀 使用指南

### 启动服务

```bash
# 方式1: 使用部署脚本（推荐）
./scripts/deploy_synthesis.sh integrated

# 方式2: 手动启动
docker-compose -f docker-compose.yml -f docker-compose.synthesis.yml up -d

# 方式3: 仅启动扩展
docker-compose -f docker-compose.synthesis.yml up -d
```

### 手动生成任务

```bash
# 生成3个任务
python scripts/generate_tasks.py --count 3

# 生成特定类型任务
python scripts/generate_tasks.py --type web --count 5
```

### 监控状态

```bash
# 查看部署状态
./scripts/deploy_synthesis.sh status

# 查看日志
./scripts/deploy_synthesis.sh logs

# 查看容器状态
docker-compose -f docker-compose.synthesis.yml ps
```

## 🔍 质量保证

### 测试覆盖

- ✅ 单元测试：合成器核心逻辑
- ✅ 集成测试：LLM客户端
- ✅ 端到端测试：任务生成流程
- ✅ 性能测试：并发处理能力

### 监控指标

- 📊 任务生成速率
- 📈 质量评分分布
- ⏱️ 处理延迟
- 🔧 错误率统计

## 🛠️ 开发指南

### 扩展新的LLM

```python
# 在 core/llm_client.py 中添加
class NewLLMClient(BaseLLMClient):
    async def generate_text(self, prompt: str) -> str:
        # 实现新的LLM调用
        pass
```

### 添加新的合成策略

```python
# 在 core/synthesis.py 中扩展
class AdvancedSynthesizer(SimpleSynthesizer):
    async def advanced_generation_strategy(self):
        # 实现新的生成策略
        pass
```

## 📞 支持和维护

### 常见问题

**Q: 合成器启动失败？**
A: 检查环境变量配置，确保LLM API密钥正确设置

**Q: 原系统无法启动？**
A: 使用独立部署模式：`./scripts/deploy_synthesis.sh synthesis`

**Q: 任务生成质量差？**
A: 调整模型参数，增加轨迹数据样本

### 故障排查

```bash
# 1. 检查容器状态
docker-compose -f docker-compose.synthesis.yml ps

# 2. 查看详细日志
docker-compose -f docker-compose.synthesis.yml logs synthesis

# 3. 检查网络连接
docker network inspect agent-data-platform_default

# 4. 验证数据库
sqlite3 output/synthesis.db ".tables"
```

### 性能优化

- 🚀 启用Redis缓存
- 📊 调整批处理大小
- ⚡ 使用本地VLLM模型
- 🔧 优化数据库索引

## 📝 版本历史

- **v1.0.0** - 初始版本，基础合成功能
- **v1.1.0** - 添加插件化架构
- **v1.2.0** - 支持多种LLM模型
- **v1.3.0** - 独立部署支持

## 📄 许可证

本扩展模块遵循原项目的许可证要求。

---

## 🔗 相关链接

- [原项目仓库](https://github.com/Drip-Data/agent-data-platform)
- [项目文档](./PROJECT_STRUCTURE.md)
- [清理总结](./CLEANUP_SUMMARY.md)
- [部署指南](./scripts/deploy_synthesis.sh) 