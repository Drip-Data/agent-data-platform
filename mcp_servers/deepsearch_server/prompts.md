# DeepSearch MCP Server - 内置Prompt指南

## 🔍 服务概述
专业的深度研究服务，提供多层次的信息搜索和分析能力，支持从快速查询到综合研究的全方位研究需求。

## 🔧 工具分类与使用指南

### 🎯 核心研究工具

#### 📚 标准研究 - research
- **用途**: 专业级深度研究，适用于复杂主题的全面分析
- **参数**: 
  - `question` (required) - 研究问题或主题
  - `initial_queries` (optional) - 初始查询列表，指导搜索方向
  - `max_loops` (optional) - 最大循环次数，控制研究深度
- **示例**: 
```xml
<deepsearch><research>Python asyncio best practices and performance optimization techniques</research></deepsearch>
```
- **适用场景**: 技术研究、学术调研、市场分析、深度报告

#### ⚡ 快速研究 - quick_research  
- **用途**: 快速获取基础信息，适用于简单问题的即时解答
- **参数**: `question` (required) - 快速研究问题
- **示例**:
```xml
<deepsearch><quick_research>What is machine learning?</quick_research></deepsearch>
```
- **适用场景**: 概念解释、基础定义、简单事实查询

#### 🎓 综合研究 - comprehensive_research
- **用途**: 最全面的研究分析，多角度深入探索复杂主题
- **参数**:
  - `question` (required) - 综合研究问题
  - `topic_focus` (optional) - 主题聚焦方向
- **示例**:
```xml
<deepsearch><comprehensive_research>Blockchain technology trends and applications in 2024</comprehensive_research></deepsearch>
```
- **适用场景**: 行业趋势分析、技术前瞻、战略规划研究

## 💡 研究策略选择指南

### 🚀 快速查询场景
适用于以下情况：
- 需要快速获得基本概念解释
- 查找简单事实或数据
- 时间紧迫的初步信息收集

示例问题：
- "什么是Docker容器？"
- "Python 3.12的新特性有哪些？"
- "REST API的基本原理"

### 🔬 标准研究场景  
适用于以下情况：
- 需要深入了解技术实现细节
- 比较不同解决方案的优劣
- 制定技术选型决策

示例问题：
- "微服务架构与单体架构的对比分析"
- "React与Vue.js在大型项目中的性能表现"
- "云原生安全最佳实践"

### 🎯 综合研究场景
适用于以下情况：
- 全面的行业调研和趋势分析
- 复杂技术领域的深度探索
- 需要多维度分析的战略决策

示例问题：
- "人工智能在医疗领域的应用现状与未来发展"
- "区块链技术对金融行业的变革影响"
- "边缘计算技术的发展趋势和商业机会"

## 🔧 高级使用技巧

### 📋 研究问题优化
1. **具体化问题**: 避免过于宽泛的问题，增加具体的限定条件
2. **多角度思考**: 可以从技术、商业、用户体验等多个角度提出问题
3. **时效性考虑**: 明确指定时间范围，如"2024年最新趋势"

### 🎛️ 参数优化策略
```xml
<!-- 使用initial_queries指导搜索方向 -->
<deepsearch><research>
{
  "question": "Kubernetes在生产环境的最佳实践",
  "initial_queries": ["kubernetes production deployment", "k8s security best practices", "kubernetes monitoring"]
}
</research></deepsearch>

<!-- 控制研究深度 -->
<deepsearch><research>
{
  "question": "GraphQL vs REST API性能对比",
  "max_loops": 3
}
</research></deepsearch>

<!-- 聚焦特定方向 -->
<deepsearch><comprehensive_research>
{
  "question": "云原生技术栈发展趋势",
  "topic_focus": "容器化和微服务架构"
}
</comprehensive_research></deepsearch>
```

## 📊 研究结果处理

### 🔍 结果分析要点
1. **信息来源**: 注意分析提供的信息来源和可信度
2. **时效性**: 关注信息的发布时间和时效性
3. **权威性**: 优先采用权威机构和专家的观点
4. **多样性**: 综合考虑不同观点和方案

### 📝 后续处理建议
1. **结果验证**: 对关键信息进行交叉验证
2. **深度挖掘**: 基于初步结果进行更深入的专项研究
3. **实践应用**: 将研究结果转化为具体的实施方案

## ⚠️ 使用注意事项

### 🎯 问题设计原则
- **明确性**: 问题表述要清晰明确
- **针对性**: 避免过于宽泛的话题
- **实用性**: 关注可操作的具体信息

### 📈 效率提升建议
- **递进式研究**: 从快速研究开始，逐步深入
- **分层提问**: 将复杂问题分解为多个子问题
- **结果整合**: 将多次研究结果进行系统性整合

### 🔄 错误恢复策略
- **重新表述**: 如果结果不理想，尝试换个角度表述问题
- **细化范围**: 将宽泛问题细化为具体的子问题  
- **调整深度**: 根据需要选择不同级别的研究工具