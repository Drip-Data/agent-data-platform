FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# 设置工作目录
WORKDIR /app

# 复制代码 包含 runtimes 和 core
COPY runtimes /app/runtimes
COPY core /app/core

# 安装Python依赖
RUN pip install --no-cache-dir -r /app/runtimes/web_navigator/requirements.txt

# 安装Playwright浏览器（仅Chromium）
RUN playwright install chromium && playwright install-deps chromium

# 创建输出目录
RUN mkdir -p /app/output/trajectories /app/output/logs

# 暴露metrics端口
EXPOSE 8002

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8002/metrics || exit 1

CMD ["python", "-m", "runtimes.web_navigator.runtime"]