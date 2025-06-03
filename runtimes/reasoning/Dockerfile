FROM python:3.8-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt /app/requirements.txt
COPY runtimes/reasoning/requirements.txt /app/reasoning_requirements.txt

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r reasoning_requirements.txt

# 复制文件
COPY core /app/core
COPY runtimes/reasoning /app/runtimes/reasoning
COPY runtimes /app/runtimes

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 8003

# 启动命令
CMD ["python", "-m", "runtimes.reasoning.runtime"]