FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# 安装Python依赖
COPY runtimes/web_navigator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装Playwright浏览器（仅Chromium）
RUN playwright install chromium && \
    playwright install-deps chromium

# 复制运行时代码
COPY runtimes/web_navigator/runtime.py .
COPY runtimes/web_navigator/browser_manager.py .
COPY core/ ./core/

# 创建输出目录
RUN mkdir -p /app/output/{trajectories,logs}

# 暴露metrics端口
EXPOSE 8002

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8002/metrics || exit 1

CMD ["python", "runtime.py"]