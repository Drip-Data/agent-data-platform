# Synthesis 模块 - 智能任务合成引擎

## 📋 概述

Synthesis 模块是 Agent Data Platform 的核心组件，专门负责从Agent执行轨迹中提取任务本质并生成高质量的种子任务。该模块采用**基于JSON文件存储的轻量化架构**，通过LLM深度分析轨迹数据，实现智能化的任务合成和去重管理。

## 🎯 核心功能与特性

### 💡 主要能力

1. **轨迹智能分析**：深度解析Agent执行轨迹，提取任务本质特征
2. **去重检查机制**：基于轨迹ID的持久化去重，避免重复处理
3. **本质提取引擎**：使用LLM从轨迹中提取任务类型、领域、复杂度等关键特征
4. **种子任务生成**：将任务本质转换为可执行的种子任务
5. **文件自动监控**：实时监控轨迹文件变化，自动触发处理
6. **JSON文件存储**：轻量化存储方案，无数据库依赖
7. **HTTP API接口**：便捷的REST API管理界面
8. **Redis队列集成**：异步命令处理和状态通知

### 🔧 技术亮点

- **多工具协同识别**：智能识别reasoning/web/code三种任务类型
- **轨迹价值评估**：自动判断轨迹是否值得处理，优化资源利用
- **增强LLM提示**：完整轨迹信息输入，提升本质提取准确性
- **线程安全设计**：文件锁保护并发访问，确保数据一致性
- **容器化部署**：完整的Docker Compose部署方案

## 🏗️ 系统架构

### 🔧 核心组件架构

```
core/synthesiscore/
├── synthesis.py              # 核心合成引擎 - SimpleSynthesizer类
│   ├── TrajectoryHandler     # 文件监控处理器 (Watchdog)
│   ├── SimpleSynthesizer     # 主要合成引擎
│   ├── TaskEssence          # 任务本质数据结构
│   └── Redis队列处理器       # 异步命令处理
├── synthesis_api.py          # HTTP API接口 - FastAPI REST服务
│   ├── FastAPI应用           # Web API服务器
│   ├── Redis命令发送器       # 命令队列接口
│   └── 状态查询接口          # 服务状态监控
└── __init__.py              # 模块导入定义
```

### 🐳 容器化架构

```
Docker Compose 部署
├── synthesis容器 (端口8081)
│   ├── SimpleSynthesizer主进程    # 核心合成引擎
│   ├── FastAPI HTTP服务          # REST API接口
│   ├── Watchdog文件监控          # 轨迹文件变化监控
│   └── Redis Stream消费者        # 命令队列处理
├── redis容器 (端口6379)          # Redis队列和状态存储
└── agent_network网络            # 容器间通信网络
```

### 📊 数据流程图

```
轨迹输入 → 去重检查 → LLM分析 → 本质提取 → 种子生成 → JSON存储
    ↓
trajectories_collection.json
    ↓
去重检查 (processed_trajectories.json)
    ↓
LLM深度分析 (完整轨迹 + 智能提示)
    ↓
TaskEssence对象 (类型/领域/复杂度)
    ↓
种子任务转换 (工具推断 + 步数估算)
    ↓
文件输出 (task_essences.json + seed_tasks.jsonl)
```

### 📁 数据文件结构

```
/app/output/
├── trajectories/
│   └── trajectories_collection.json     # 轨迹集合输入文件
├── task_essences.json                   # 任务本质存储 (JSON数组)
├── seed_tasks.jsonl                     # 种子任务输出 (JSONL格式)
├── processed_trajectories.json          # 已处理轨迹记录 (去重用)
└── logs/
    └── synthesis.log                    # 详细运行日志
```

## 🧠 内部运转机制详解

### 1. 轨迹监控与触发机制

**文件监控器 (TrajectoryHandler)**
```python
# 基于Watchdog的文件变化监控
class TrajectoryHandler(FileSystemEventHandler):
    def on_modified(self, event):
        # 检测到trajectories_collection.json变化
        # → 发送Redis命令到队列
        # → 触发轨迹处理流程
```

**触发方式**：
- **自动触发**：文件监控器检测到轨迹文件变化
- **手动触发**：HTTP API或Redis命令手动启动
- **命令种类**：
  - `process_trajectories`：处理未处理轨迹
  - `trigger_synthesis`：完整轨迹处理  
  - `generate_seeds_from_essences`：从现有本质生成种子

### 2. 去重检查系统

**持久化去重机制**：
```python
# 基于轨迹ID的持久化去重
self.processed_trajectories = set()  # 内存缓存
# 持久化文件：processed_trajectories.json

def _is_trajectory_processed(self, trajectory_id: str) -> bool:
    return trajectory_id in self.processed_trajectories

def _mark_trajectory_processed(self, trajectory_id: str):
    self.processed_trajectories.add(trajectory_id)
    self._save_processed_trajectories()  # 立即保存到文件
```

**去重特点**：
- **基于轨迹ID**：每个轨迹的task_id作为唯一标识
- **容器重启保持**：去重记录持久化到JSON文件
- **线程安全**：文件锁保护并发访问
- **智能跳过**：已处理轨迹自动跳过，避免重复计算

### 3. 轨迹价值评估算法

**智能过滤机制**：
```python
def _should_process_trajectory(self, trajectory: TrajectoryResult) -> bool:
    # 1. 成功轨迹优先处理
    if trajectory.success:
        return True
    
    # 2. reasoning类型轨迹（即使失败也有价值）
    if 'reasoning' in trajectory.runtime_id.lower():
        return True
    
    # 3. 多步骤复杂任务
    if len(trajectory.steps) >= 2:
        return True
    
    # 4. 包含有价值关键词的任务
    valuable_keywords = ['reasoning', 'analysis', 'compare']
    if any(keyword in trajectory.task_description.lower() for keyword in valuable_keywords):
        return True
        
    return False
```

### 4. LLM本质提取引擎

**增强提示构建**：
```python
def _build_extraction_prompt(self, trajectory: TrajectoryResult) -> str:
    # 构建完整轨迹信息
    # 1. 基本信息：任务ID、描述、执行状态、运行时环境
    # 2. 详细步骤：每步的动作类型、参数、结果、思考过程
    # 3. 工具分析：使用的工具类型和模式
    # 4. 智能提示：根据runtime_id提供分析指导
    
    # 返回结构化JSON格式要求
    return f"""
    请分析以上完整轨迹信息，提取：
    1. task_type: reasoning/web/code
    2. domain: algorithm/data_analysis/web_automation/research等
    3. optimized_description: 优化后的任务描述
    4. complexity: simple/medium/complex
    5. key_features: 关键特征列表
    """
```

**智能类型推断**：
```python
def _infer_task_type(self, trajectory, llm_suggestion) -> str:
    # 1. 基于runtime_id的强规则
    if 'reasoning' in trajectory.runtime_id.lower():
        return "reasoning"
    
    # 2. 基于任务描述关键词
    # 3. 基于执行步骤分析（工具使用模式）
    # 4. LLM建议作为参考
    # 5. 默认推断
```

### 5. 种子任务生成流程

**本质到种子转换**：
```python
def _convert_essence_to_seed(self, essence: TaskEssence) -> Dict:
    # 1. 生成唯一任务ID
    task_id = f"seed_{essence.task_type}_{hash_suffix}"
    
    # 2. 推断预期工具
    expected_tools = self._infer_expected_tools(essence.task_type, essence.domain)
    
    # 3. 估算最大步数
    max_steps = self._infer_max_steps(essence.complexity_level, essence.task_type)
    
    # 4. 构建完整种子任务
    return {
        "task_id": task_id,
        "task_type": essence.task_type,
        "description": essence.query,
        "expected_tools": expected_tools,
        "max_steps": max_steps,
        "domain": essence.domain,
        "complexity": essence.complexity_level,
        "source_essence_id": essence.essence_id
    }
```

### 6. 文件存储管理

**线程安全的JSON操作**：
```python
def _save_json_file(self, filepath: str, data):
    with self._file_lock:  # 线程锁保护
        # 原子写入：临时文件 + 替换
        temp_filepath = filepath + '.tmp'
        with open(temp_filepath, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_filepath, filepath)  # 原子替换
```

**文件格式说明**：
- `task_essences.json`：JSON数组，存储所有任务本质
- `seed_tasks.jsonl`：JSONL格式，每行一个种子任务
- `processed_trajectories.json`：JSON数组，存储已处理轨迹ID列表

## 🚀 快速开始

### 1. 环境准备

**必需依赖**：
```bash
# Docker环境
Docker 20.10+
Docker Compose 2.0+

# API密钥配置（至少配置一个）
export GEMINI_API_KEY="your_gemini_api_key"     # Google Gemini（推荐）
export DEEPSEEK_API_KEY="your_deepseek_key"     # DeepSeek API
export OPENAI_API_KEY="your_openai_key"         # OpenAI API
```

### 2. 服务部署

```bash
# 启动synthesis服务
docker-compose up -d synthesis redis

# 验证服务状态
curl http://localhost:8081/health
# 输出: {"status": "healthy", "redis": "connected", "storage": "json_files"}

# 查看服务信息
curl http://localhost:8081/
```

### 3. 轨迹数据准备

```bash
# 创建轨迹集合文件
mkdir -p output/trajectories
cat > output/trajectories/trajectories_collection.json << 'EOF'
[
  {
    "task_id": "example_task_1",
    "task_name": "web_search_analysis",
    "task_description": "使用浏览器搜索并分析ChatGPT和Claude的优缺点对比",
    "runtime_id": "reasoning-runtime-v1",
    "success": true,
    "steps": [
      {
        "step_id": 1,
        "action_type": "browser_navigate",
        "tool_input": {"url": "https://google.com"},
        "tool_output": "Successfully loaded Google homepage",
        "success": true,
        "thinking": "需要搜索ChatGPT和Claude的对比信息",
        "duration": 2.5
      }
    ],
    "final_result": "成功完成AI模型对比分析",
    "total_duration": 45.0,
    "metadata": {"runtime_version": "v1.0"}
  }
]
EOF
```

## 🎮 使用指南

### 📦 HTTP API操作

#### 基础操作
```bash
# 健康检查
curl http://localhost:8081/health

# 获取服务状态
curl http://localhost:8081/status

# 查看API信息
curl http://localhost:8081/
```

#### 轨迹处理操作
```bash
# 处理所有未处理轨迹（推荐）
curl -X POST http://localhost:8081/trigger/new

# 完整轨迹处理（重新处理所有）
curl -X POST http://localhost:8081/trigger/full

# 处理指定轨迹文件
curl -X POST http://localhost:8081/trigger/specific \
  -H "Content-Type: application/json" \
  -d '{"filename": "specific_trajectory.json"}'

# 从现有本质生成种子任务（修复缺失种子任务）
curl -X POST http://localhost:8081/command \
  -H "Content-Type: application/json" \
  -d '{"command": "generate_seeds_from_essences"}'
```

#### 监控管理
```bash
# 启动自动轨迹监控
curl -X POST http://localhost:8081/monitoring/start

# 停止自动轨迹监控  
curl -X POST http://localhost:8081/monitoring/stop

# 导出种子任务统计
curl -X POST http://localhost:8081/export
```

### 📊 Redis命令操作

```bash
# 直接发送Redis命令
docker exec agent-data-platform-redis-1 redis-cli XADD synthesis:commands "*" command process_trajectories

# 查看命令队列
docker exec agent-data-platform-redis-1 redis-cli XLEN synthesis:commands

# 查看状态队列
docker exec agent-data-platform-redis-1 redis-cli XREVRANGE synthesis:status + - COUNT 1
```

### 📁 文件管理

#### 查看处理结果
```bash
# 查看任务本质
cat output/task_essences.json | jq '.[] | {essence_id, task_type, domain, query}'

# 查看种子任务
head -5 output/seed_tasks.jsonl | jq .

# 统计处理结果
echo "任务本质数量: $(cat output/task_essences.json | jq length)"
echo "种子任务数量: $(wc -l < output/seed_tasks.jsonl)"
echo "已处理轨迹数量: $(cat output/processed_trajectories.json | jq length)"
```

#### 数据清理
```bash
# 清空所有处理记录（重新开始）
rm -f output/task_essences.json output/seed_tasks.jsonl output/processed_trajectories.json

# 重启服务让其重新初始化
docker-compose restart synthesis
```

## 🔧 高级配置

### 环境变量配置

```bash
# 核心功能开关
SYNTHESIS_ENABLED=true                    # 启用synthesis功能
AUTO_MONITOR_TRAJECTORIES=true           # 自动监控轨迹文件
AUTO_EXPORT_SEEDS=true                   # 自动导出种子任务

# LLM API配置（按检测优先级）
GEMINI_API_KEY=your_gemini_key          # Google Gemini API（优先级1）
DEEPSEEK_API_KEY=your_deepseek_key      # DeepSeek API（优先级2）
OPENAI_API_KEY=your_openai_key          # OpenAI API（优先级3）
OPENAI_API_BASE=custom_endpoint         # 自定义OpenAI兼容端点

# 服务配置  
API_PORT=8081                           # HTTP API端口
REDIS_URL=redis://redis:6379            # Redis连接URL
LOG_LEVEL=INFO                          # 日志级别（DEBUG/INFO/WARNING/ERROR）
```

### 容器配置

```yaml
# docker-compose.yml示例配置
services:
  synthesis:
    build: .
    ports:
      - "8081:8081"
    volumes:
      - ./output:/app/output    # 数据持久化
      - ./core:/app/core        # 代码映射
    environment:
      - SYNTHESIS_ENABLED=true
      - AUTO_MONITOR_TRAJECTORIES=true
      - GEMINI_API_KEY=${GEMINI_API_KEY}
    depends_on:
      - redis
    networks:
      - agent_network
```

## 📊 监控与运维

### 🔍 日志监控

```bash
# 查看实时日志
docker-compose logs -f synthesis

# 查看特定类型日志
docker-compose logs synthesis | grep "✅"  # 成功处理日志
docker-compose logs synthesis | grep "❌"  # 错误日志
docker-compose logs synthesis | grep "🧠"  # LLM分析日志

# 查看文件级别日志
docker exec synthesis-1 tail -f /app/output/logs/synthesis.log
```

### 📈 性能监控

```bash
# 容器资源使用
docker stats synthesis-1

# 文件大小监控
ls -lh output/*.json output/*.jsonl

# Redis队列监控
docker exec redis-1 redis-cli INFO memory
docker exec redis-1 redis-cli XLEN synthesis:commands
```

### 🚨 常见问题排查

#### 1. 种子任务文件为空
```bash
# 检查是否有任务本质
cat output/task_essences.json | jq length

# 手动触发种子生成
curl -X POST http://localhost:8081/command \
  -H "Content-Type: application/json" \
  -d '{"command": "generate_seeds_from_essences"}'

# 检查LLM API配置
docker exec synthesis-1 env | grep API_KEY
```

#### 2. 轨迹重复处理
```bash
# 检查去重记录
cat output/processed_trajectories.json | jq .

# 清空去重记录（谨慎操作）
echo "[]" > output/processed_trajectories.json
```

#### 3. LLM API调用失败
```bash
# 检查API密钥配置
docker exec synthesis-1 python -c "
import os
print('Gemini:', 'SET' if os.getenv('GEMINI_API_KEY') else 'NOT SET')
print('DeepSeek:', 'SET' if os.getenv('DEEPSEEK_API_KEY') else 'NOT SET')
print('OpenAI:', 'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET')
"

# 测试LLM连接
docker exec synthesis-1 python -c "
from core.llm_client import LLMClient
client = LLMClient({'provider': 'auto'})
print('Selected provider:', client.provider.value)
"
```

## 🎯 最佳实践

### 1. 数据管理
- **定期备份**：备份`task_essences.json`和`seed_tasks.jsonl`文件
- **监控文件大小**：单文件过大时考虑分片存储
- **清理日志**：定期清理过期的日志文件

### 2. 轨迹质量
- **确保格式正确**：轨迹文件符合`TrajectoryResult`结构
- **提供完整信息**：包含步骤详情、思考过程等
- **区分任务类型**：通过runtime_id明确标识任务类型

### 3. 性能优化
- **合理设置API调用频率**：避免超过LLM API限制
- **监控内存使用**：大量轨迹处理时关注内存消耗
- **使用去重功能**：避免重复处理相同轨迹

### 4. 运维监控
- **健康检查**：定期检查`/health`端点
- **日志监控**：关注错误日志和LLM调用状态
- **数据一致性**：确保去重记录和本质记录的一致性

## 📝 更新日志

### v2.1.0 - 去重功能完善版
- ✅ **去重系统重构**：基于轨迹ID的持久化去重机制
- ✅ **种子任务生成修复**：修复缺失的`aiofiles`导入和生成流程
- ✅ **轨迹价值评估**：智能判断轨迹处理价值，优化资源利用
- ✅ **增强LLM提示**：提供完整轨迹信息，提升分析准确性
- ✅ **Redis命令扩展**：新增`generate_seeds_from_essences`命令
- ✅ **日志系统优化**：详细的处理状态和错误信息记录
- ✅ **文件安全性**：原子写入和线程锁保护

### 主要技术特性
- **轻量化存储**：纯JSON文件存储，无数据库依赖
- **异步处理架构**：Redis Stream + asyncio事件循环
- **智能分析引擎**：多维度轨迹特征提取
- **容器化部署**：完整的Docker Compose部署方案
- **RESTful API**：标准化的HTTP接口设计
- **实时监控**：基于Watchdog的文件变化监控
- **多LLM支持**：统一接口支持Gemini/DeepSeek/OpenAI

### 数据统计示例
```
处理结果（成功运行）：
- 输入：23个原始轨迹
- 去重后：13个有效轨迹  
- 输出：23个任务本质 + 26个种子任务
- 比例：1个轨迹 → 1个本质 → 1个种子任务（1:1:1）