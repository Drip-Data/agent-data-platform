# Reasoning Runtime Dockerfile - 优化版本
FROM python:3.10-slim

# 安装基础系统依赖（移除浏览器相关依赖）
RUN apt-get update --fix-missing && apt-get install -y \
    curl \
    wget \
    ca-certificates \
    # matplotlib 和可视化所需的依赖
    libgl1-mesa-glx \
    libglib2.0-0 \
    libfontconfig1 \
    libxrender1 \
    libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY runtimes/reasoning/requirements.txt /app/reasoning_requirements.txt
COPY requirements.txt /app/base_requirements.txt

# 安装Python依赖
RUN pip install --no-cache-dir -r base_requirements.txt && \
    pip install --no-cache-dir -r reasoning_requirements.txt

# 验证关键依赖安装成功（移除playwright验证）
RUN python -c "import matplotlib; import pandas; import numpy; import langchain; import google.genai; print('深度研究依赖安装成功!')"

# 复制代码
COPY core/ /app/core/
COPY runtimes/reasoning/ /app/runtimes/reasoning/
COPY runtimes/sandbox/ /app/runtimes/sandbox/
COPY runtimes/web_navigator/ /app/runtimes/web_navigator/
COPY runtimes/__init__.py /app/runtimes/

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 8003

# 启动命令
CMD ["python", "-m", "runtimes.reasoning.runtime"]