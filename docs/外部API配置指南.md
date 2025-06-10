# 外部API配置指南

本指南详细说明如何配置Agent数据平台使用外部LLM API服务，包括Google Gemini、DeepSeek、OpenAI等。

## 🚀 快速开始

### 1. 复制环境变量模板

```bash
cp .env.example .env
```

### 2. 编辑 `.env` 文件，填入API密钥

```bash
notepad .env  # Windows
# 或
vim .env     # Linux/Mac
```

### 3. 重启服务使配置生效

```bash
docker-compose down
docker-compose up -d
```

## 📋 支持的API提供商

### 1. Google Gemini API

**优势**: 性价比高，响应速度快，支持多模态

**获取API密钥**:
1. 访问 [Google AI Studio](https://makersuite.google.com/app/apikey)
2. 登录Google账号
3. 点击「Create API Key」
4. 复制生成的API密钥

**配置方法**:
```bash
# 在 .env 文件中添加
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_API_URL=https://generativelanguage.googleapis.com/v1beta
```

**或者在docker-compose.yml中配置**:
```yaml
sandbox-runtime:
  environment:
    - GEMINI_API_KEY=your_gemini_api_key_here
    - GEMINI_API_URL=https://generativelanguage.googleapis.com/v1beta
```

### 2. DeepSeek API

**优势**: 专门优化的代码生成模型，代码质量高

**获取API密钥**:
1. 访问 [DeepSeek Platform](https://platform.deepseek.com/api_keys)
2. 注册并登录账号
3. 创建新的API密钥
4. 复制API密钥

**配置方法**:
```bash
# 在 .env 文件中添加
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_API_URL=https://api.deepseek.com/v1
```

### 3. OpenAI API

**优势**: 模型质量高，生态完善

**获取API密钥**:
1. 访问 [OpenAI Platform](https://platform.openai.com/api-keys)
2. 登录OpenAI账号
3. 点击「Create new secret key」
4. 复制生成的API密钥

**配置方法**:
```bash
# 在 .env 文件中添加
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_API_BASE=https://api.openai.com/v1
```

### 4. 其他OpenAI兼容服务

支持任何兼容OpenAI API格式的服务，如:
- Azure OpenAI Service
- 本地部署的开源模型 (如Ollama)
- 第三方API代理服务

**配置方法**:
```bash
OPENAI_API_KEY=your_api_key
OPENAI_API_BASE=https://your-service-endpoint.com/v1
```

## ⚙️ 高级配置

### API优先级

系统会按以下优先级自动选择API提供商:
1. **Google Gemini** (如果设置了 `GEMINI_API_KEY`)
2. **DeepSeek** (如果设置了 `DEEPSEEK_API_KEY`)
3. **OpenAI** (如果设置了 `OPENAI_API_KEY`)
4. **本地vLLM服务** (默认回退选项)

### 混合使用策略

可以同时配置多个API，系统会智能选择:

```bash
# 同时配置多个API
GEMINI_API_KEY=your_gemini_key
DEEPSEEK_API_KEY=your_deepseek_key
OPENAI_API_KEY=your_openai_key
```

### 任务类型优化建议

| 任务类型 | 推荐API | 原因 |
|---------|---------|------|
| 代码生成 | DeepSeek | 专门优化的代码模型 |
| 网页操作 | Google Gemini | 多模态能力，理解页面结构 |
| 数据分析 | OpenAI GPT-4 | 逻辑推理能力强 |
| 批量处理 | 本地vLLM | 成本低，无API限制 |

## 🔧 故障排除

### 常见问题

**1. API密钥无效**
```
Error: Invalid API key
```
**解决方案**: 检查API密钥是否正确，是否有足够的配额

**2. 网络连接问题**
```
Error: Connection timeout
```
**解决方案**: 检查网络连接，考虑使用代理

**3. 配额超限**
```
Error: Rate limit exceeded
```
**解决方案**: 等待配额重置，或升级API计划

### 调试方法

**1. 查看日志**
```bash
docker-compose logs -f sandbox-runtime
docker-compose logs -f web-runtime
```

**2. 测试API连接**
```bash
# 测试Gemini API
curl -H "Content-Type: application/json" \
     -d '{"contents":[{"parts":[{"text":"Hello"}]}]}' \
     "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key=YOUR_API_KEY"

# 测试DeepSeek API
curl -H "Content-Type: application/json" \
     -H "Authorization: Bearer YOUR_API_KEY" \
     -d '{"model":"deepseek-coder","messages":[{"role":"user","content":"Hello"}]}' \
     "https://api.deepseek.com/v1/chat/completions"
```

**3. 启用详细日志**
```yaml
# 在docker-compose.yml中设置
environment:
  - LOG_LEVEL=DEBUG
```

## 💰 成本优化

### API成本对比 (大致参考)

| 提供商 | 输入成本 | 输出成本 | 特点 |
|--------|----------|----------|------|
| Google Gemini | 低 | 低 | 性价比最高 |
| DeepSeek | 中 | 中 | 代码质量高 |
| OpenAI GPT-3.5 | 中 | 中 | 平衡性好 |
| OpenAI GPT-4 | 高 | 高 | 质量最高 |
| 本地vLLM | 免费 | 免费 | 需要GPU资源 |

### 成本控制策略

1. **使用缓存**: 系统自动缓存相似任务的结果
2. **混合策略**: 简单任务用便宜API，复杂任务用高质量API
3. **批量处理**: 减少API调用次数
4. **本地回退**: API失败时使用本地模型

## 🔒 安全最佳实践

### 1. API密钥管理

- ✅ 使用环境变量存储API密钥
- ✅ 不要将API密钥提交到代码仓库
- ✅ 定期轮换API密钥
- ✅ 为不同环境使用不同的API密钥

### 2. 网络安全

- ✅ 使用HTTPS连接
- ✅ 配置防火墙规则
- ✅ 监控API使用情况
- ✅ 设置使用配额限制

### 3. 数据隐私

- ✅ 不要发送敏感数据到外部API
- ✅ 了解各API提供商的数据处理政策
- ✅ 对于敏感任务使用本地模型

## 📊 监控和指标

### 查看API使用情况

访问监控面板:
- Sandbox Runtime: http://localhost:8001/metrics
- Web Runtime: http://localhost:8002/metrics
- Grafana Dashboard: http://localhost:3000

### 关键指标

- API调用次数
- 响应时间
- 成功率
- 错误类型分布
- 成本统计

## 🆘 获取帮助

如果遇到问题，可以:

1. 查看系统日志: `docker-compose logs`
2. 检查API提供商的状态页面
3. 参考各API提供商的官方文档
4. 在项目Issues中提问

---

**注意**: 请妥善保管您的API密钥，不要在公开场合分享。建议定期检查API使用情况和账单。