# Synthesis 模块统一容器化管理指南

## 📋 概述

Synthesis 模块是 Agent Data Platform 的智能任务合成器，用于分析轨迹数据并提取任务本质，存储到数据库中用于后续任务生成。本模块采用**完全容器化架构**，所有操作都通过统一的管理接口进行，确保环境一致性和操作简便性。

## 🏗️ 架构概览

### 🔧 核心组件

```
core/synthesiscore/
├── synthesis.py              # 核心合成引擎 - 轨迹分析与任务生成
├── synthesis_api.py          # HTTP API接口 - 提供REST API服务  
├── synthesis_manager.py      # 服务统一管理器 - 命令行控制接口
├── docker_manager.py         # Docker容器管理器 - 容器生命周期管理
├── init_synthesis_db.py      # 数据库初始化脚本
└── __init__.py              # 模块初始化
```

### 🐳 容器架构

```
Docker Compose 服务
├── synthesis                 # 主服务容器
│   ├── HTTP API (端口8081)  # REST API服务
│   ├── Redis Worker         # 队列任务处理
│   └── 数据库管理           # SQLite数据库操作
├── redis                    # Redis服务 (端口6379) 
└── agent-data-platform      # Docker网络
```

## 🚀 快速开始

### 1. 环境准备

确保系统已安装：
- Docker (推荐 20.10+)
- Docker Compose (推荐 2.0+)
- Python 3.9+ (用于管理工具)

### 2. 镜像构建与部署

#### 🎯 一键完整部署

```bash
# 完整部署流程 - 自动构建镜像、创建网络、启动服务
python core/synthesiscore/docker_manager.py deploy
```

这个命令会自动执行：
1. 检查Docker环境
2. 创建Docker网络
3. 构建synthesis镜像  
4. 启动所有服务
5. 等待服务健康检查
6. 显示部署状态

#### 🔧 分步部署（高级用户）

```bash
# 1. 检查Docker环境
python core/synthesiscore/docker_manager.py check

# 2. 创建Docker网络
python core/synthesiscore/docker_manager.py network

# 3. 构建Docker镜像  
python core/synthesiscore/docker_manager.py build

# 4. 启动服务
python core/synthesiscore/docker_manager.py start

# 5. 检查状态
python core/synthesiscore/docker_manager.py status
```

### 3. 验证部署

```bash
# 检查服务健康状态
python core/synthesiscore/synthesis_manager.py health

# 检查容器状态
python core/synthesiscore/docker_manager.py status
```

预期输出：
```
✅ Synthesis服务运行正常
   Redis状态: connected

📊 服务状态:
synthesis 容器: Running (healthy)
redis 容器: Running
```

## 🎮 功能操作指南

### 📦 Docker 容器管理

#### 基础容器操作

```bash
# 启动所有服务
python core/synthesiscore/docker_manager.py start

# 停止所有服务  
python core/synthesiscore/docker_manager.py stop

# 重启服务
python core/synthesiscore/docker_manager.py restart

# 查看服务状态
python core/synthesiscore/docker_manager.py status
```

#### 日志查看

```bash
# 查看所有服务日志
python core/synthesiscore/docker_manager.py logs

# 查看synthesis服务日志
python core/synthesiscore/docker_manager.py logs synthesis

# 实时跟踪日志
python core/synthesiscore/docker_manager.py logs synthesis -f

# 查看最近50行日志
python core/synthesiscore/docker_manager.py logs synthesis --tail 50
```

#### 容器内执行命令

```bash
# 进入synthesis容器Shell
python core/synthesiscore/docker_manager.py exec synthesis /bin/bash

# 在容器内执行Python命令
python core/synthesiscore/docker_manager.py exec synthesis python -c "import sqlite3; print('Database accessible')"

# 查看容器内文件
python core/synthesiscore/docker_manager.py exec synthesis ls -la /app/output/
```

#### 清理和维护

```bash
# 清理停止的容器、未使用的镜像和网络
python core/synthesiscore/docker_manager.py cleanup

# 重新构建镜像（代码更新后）
python core/synthesiscore/docker_manager.py build --no-cache
```

### 🧬 Synthesis 服务管理

#### 健康检查与状态

```bash
# 检查服务健康状态
python core/synthesiscore/synthesis_manager.py health

# 查看详细服务状态
python core/synthesiscore/synthesis_manager.py status

# 查看数据库统计信息
python core/synthesiscore/synthesis_manager.py stats
```

#### 数据库管理

```bash
# 初始化数据库（首次使用）
python core/synthesiscore/synthesis_manager.py init

# 查看所有任务和本质
python core/synthesiscore/synthesis_manager.py tasks

# 导出任务数据
python core/synthesiscore/synthesis_manager.py export

# 导出为JSON格式
python core/synthesiscore/synthesis_manager.py export --format jsonl

# 清空数据库（谨慎使用）
python core/synthesiscore/synthesis_manager.py clear
```

### 🎯 轨迹处理和任务生成

#### 轨迹分析

```bash
# 处理指定轨迹文件中的所有轨迹
python core/synthesiscore/synthesis_manager.py generate /path/to/trajectory_file.json

# 通过HTTP API触发处理所有轨迹文件
curl -X POST http://localhost:8081/trigger/full

# 只处理新的（未处理的）轨迹
curl -X POST http://localhost:8081/trigger/new  

# 处理指定轨迹文件
curl -X POST http://localhost:8081/trigger/specific \
  -H "Content-Type: application/json" \
  -d '{"filename": "trajectory_20241220_001.json"}'
```

#### 数据查看和分析

```bash
# 查看提取的任务本质统计
python core/synthesiscore/synthesis_manager.py stats

# 查看详细任务列表
python core/synthesiscore/synthesis_manager.py tasks

# 通过API获取详细数据
curl -s http://localhost:8081/db/tasks | python -m json.tool

# 获取数据库统计
curl -s http://localhost:8081/db/stats | python -m json.tool
```

## 📊 API 接口文档

### HTTP API 端点

synthesis服务提供完整的HTTP API接口（端口8081）：

```bash
# 查看所有可用端点
curl -s http://localhost:8081/ | python -m json.tool
```

#### 核心功能端点

| 端点 | 方法 | 功能 | 示例 |
|------|------|------|------|
| `/health` | GET | 健康检查 | `curl http://localhost:8081/health` |
| `/status` | GET | 服务状态 | `curl http://localhost:8081/status` |
| `/trigger/full` | POST | 处理所有轨迹 | `curl -X POST http://localhost:8081/trigger/full` |
| `/trigger/new` | POST | 处理新轨迹 | `curl -X POST http://localhost:8081/trigger/new` |
| `/trigger/specific` | POST | 处理指定轨迹 | `curl -X POST -H "Content-Type: application/json" -d '{"filename":"file.json"}' http://localhost:8081/trigger/specific` |

#### 数据库管理端点

| 端点 | 方法 | 功能 | 示例 |
|------|------|------|------|
| `/db/tasks` | GET | 获取所有任务 | `curl http://localhost:8081/db/tasks` |
| `/db/stats` | GET | 数据库统计 | `curl http://localhost:8081/db/stats` |
| `/db/export` | GET | 导出数据 | `curl http://localhost:8081/db/export` |
| `/db/clear` | POST | 清空数据库 | `curl -X POST http://localhost:8081/db/clear` |
| `/init-db` | POST | 初始化数据库 | `curl -X POST http://localhost:8081/init-db` |

## 🔧 配置说明

### 环境变量配置

在 `docker-compose.synthesis.yml` 中配置的关键环境变量：

```yaml
environment:
  # 核心配置
  SYNTHESIS_ENABLED: "true"           # 启用synthesis功能
  SYNTHESIS_DB: "/app/output/synthesis.db"  # 数据库路径
  REDIS_URL: "redis://redis:6379"     # Redis连接
  
  # LLM API配置
  GEMINI_API_KEY: "${GEMINI_API_KEY}" # Google Gemini API密钥
  DEEPSEEK_API_KEY: "${DEEPSEEK_API_KEY}" # DeepSeek API密钥
  OPENAI_API_KEY: "${OPENAI_API_KEY}" # OpenAI API密钥
  
  # 服务配置
  LOG_LEVEL: "INFO"                   # 日志级别
  API_HOST: "0.0.0.0"                # API监听地址
  API_PORT: "8081"                   # API端口
```

### 数据目录映射

```yaml
volumes:
  - ./output:/app/output              # 轨迹和数据库文件
  - ./core:/app/core                  # 源代码（开发模式）
```

## 🔍 故障排除

### 常见问题诊断

#### 1. 服务启动失败

```bash
# 检查Docker服务状态
python core/synthesiscore/docker_manager.py check

# 查看详细错误日志
python core/synthesiscore/docker_manager.py logs synthesis

# 检查端口占用
netstat -an | grep 8081
netstat -an | grep 6379
```

#### 2. API请求失败

```bash
# 检查服务健康状态
python core/synthesiscore/synthesis_manager.py health

# 查看API服务日志
python core/synthesiscore/docker_manager.py logs synthesis -f

# 测试网络连接
curl -v http://localhost:8081/health
```

#### 3. 数据库问题

```bash
# 检查数据库文件
ls -la output/synthesis.db

# 重新初始化数据库
python core/synthesiscore/synthesis_manager.py init

# 查看数据库统计
python core/synthesiscore/synthesis_manager.py stats
```

#### 4. Redis连接问题

```bash
# 检查Redis容器状态
python core/synthesiscore/docker_manager.py status

# 重启Redis服务
docker-compose -f docker-compose.synthesis.yml restart redis

# 测试Redis连接
docker-compose -f docker-compose.synthesis.yml exec redis redis-cli ping
```

### 重置和重新部署

```bash
# 完全重置环境
python core/synthesiscore/docker_manager.py stop
python core/synthesiscore/docker_manager.py cleanup
python core/synthesiscore/docker_manager.py deploy

# 重新构建镜像（代码更新后）
python core/synthesiscore/docker_manager.py build --no-cache
python core/synthesiscore/docker_manager.py restart
```

## 📈 性能监控

### 服务监控

```bash
# 查看容器资源使用
docker stats agent-data-platform-synthesis-1

# 查看服务状态
python core/synthesiscore/synthesis_manager.py status

# 监控日志输出
python core/synthesiscore/docker_manager.py logs synthesis -f
```

### 数据统计

```bash
# 查看处理统计
python core/synthesiscore/synthesis_manager.py stats

# 导出处理报告
python core/synthesiscore/synthesis_manager.py export --format jsonl > synthesis_report.jsonl
```

## 🚨 重要注意事项

### 数据安全

1. **数据备份**：定期备份 `output/synthesis.db` 数据库文件
2. **API密钥**：确保LLM API密钥安全存储，不要提交到代码仓库
3. **网络安全**：生产环境建议限制8081端口的外部访问

### 资源管理

1. **存储空间**：监控 `output/` 目录的磁盘使用情况
2. **内存使用**：synthesis服务可能消耗较多内存，建议分配至少2GB
3. **API限制**：注意LLM API的调用频率限制

### 版本兼容

1. **Docker版本**：推荐使用Docker 20.10+和Docker Compose 2.0+
2. **Python版本**：容器内使用Python 3.10，外部管理工具需要Python 3.9+
3. **数据格式**：确保轨迹文件符合预期的JSON格式

## 🔄 更新和维护

### 代码更新

```bash
# 拉取最新代码
git pull

# 重新构建镜像
python core/synthesiscore/docker_manager.py build

# 重启服务应用更新
python core/synthesiscore/docker_manager.py restart
```

### 数据库迁移

```bash
# 备份现有数据
cp output/synthesis.db output/synthesis.db.backup

# 查看当前数据统计
python core/synthesiscore/synthesis_manager.py stats

# 如需重置数据库
python core/synthesiscore/synthesis_manager.py clear
python core/synthesiscore/synthesis_manager.py init
```

---

## 📚 完整命令参考

### Docker管理器 (docker_manager.py)

```bash
python core/synthesiscore/docker_manager.py [命令]

可用命令:
  check      # 检查Docker环境
  network    # 创建Docker网络  
  build      # 构建镜像
  start      # 启动服务
  stop       # 停止服务
  restart    # 重启服务
  status     # 查看状态
  logs       # 查看日志
  exec       # 执行命令
  cleanup    # 清理资源
  deploy     # 完整部署
```

### Synthesis管理器 (synthesis_manager.py)

```bash
python core/synthesiscore/synthesis_manager.py [命令]

可用命令:
  health     # 健康检查
  init       # 初始化数据库
  tasks      # 查看所有任务
  stats      # 数据库统计
  export     # 导出数据
  clear      # 清空数据库
  generate   # 生成任务
  status     # 服务状态
```

通过这个统一的管理架构，你可以轻松地管理整个synthesis系统，从容器部署到功能操作，一切都通过标准化的命令接口完成！