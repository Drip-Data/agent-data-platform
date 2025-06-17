# 🚀 Quick Start Guide

Agent Data Platform 快速启动指南

## ⚡ 30秒启动

```bash
# 1. 确保 Redis 运行
brew services start redis  # macOS
# 或 sudo systemctl start redis-server  # Ubuntu

# 2. 设置 API Key
export GEMINI_API_KEY=your_gemini_api_key_here

# 3. 启动平台
python main.py

# 4. 等待启动完成 (看到 "All services started successfully" 消息)

# 5. 测试任务提交
curl -X POST "http://localhost:8000/api/v1/tasks" \
     -H "Content-Type: application/json" \
     -d '{"input": "计算1+1", "description": "测试任务"}'

# 6. 查看结果 (使用返回的 task_id)
curl "http://localhost:8000/api/v1/tasks/{task_id}"
```

## 🔍 验证系统状态

```bash
# 运行系统验证
python test_system_validation.py

# 期望输出:
# 🎉 SYSTEM VALIDATION: SUCCESS
# Total: 7/7 components validated
```

## 🧪 运行测试

```bash
# 快速测试
python -m pytest tests/test_synthesis_focus.py -v

# 完整测试套件
python -m pytest tests/ -v
```

## 📊 查看轨迹学习

```bash
# 查看执行轨迹
cat output/trajectories/trajectories_collection.json

# 查看生成的种子任务
cat output/seed_tasks.jsonl
```

---

详细文档请参考 [README.md](README.md)