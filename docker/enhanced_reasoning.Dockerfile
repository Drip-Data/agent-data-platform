FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
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

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import asyncio; from runtimes.reasoning.enhanced_runtime import EnhancedReasoningRuntime; print('healthy')"

# 启动命令
CMD ["python", "-m", "runtimes.reasoning.enhanced_runtime"] 