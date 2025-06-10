FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖，包括Docker CLI
RUN apt-get update && apt-get install -y \
    curl \
    docker.io \
    git \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .
COPY runtimes/reasoning/requirements.txt ./runtimes/reasoning/

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r runtimes/reasoning/requirements.txt

# 复制源代码
COPY core/ ./core/
COPY runtimes/ ./runtimes/

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# MCP动态管理配置
ENV MCP_SEARCH_ENABLED=true
ENV MCP_SEARCH_TIMEOUT=30
ENV MCP_SEARCH_MAX_CANDIDATES=10
ENV MCP_SECURITY_LEVEL=high
ENV DOCKER_NETWORK=agent-data-platform_agent_network
ENV DOCKER_PORT_RANGE=8100-8200

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import asyncio; from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime; print('healthy')"

# 启动命令
CMD ["python", "-m", "runtimes.reasoning.enhanced_runtime"] 