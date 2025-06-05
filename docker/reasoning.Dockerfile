# Reasoning Runtime Dockerfile
FROM python:3.10-slim


# 安装基础系统依赖，包括网络工具
RUN apt-get update --fix-missing && apt-get install -y \
    curl \
    wget \
    gnupg \
    software-properties-common \
    dnsutils \
    iputils-ping \
    ca-certificates \
    # matplotlib 和可视化所需的依赖
    libgl1-mesa-glx \
    libglib2.0-0 \
    libfontconfig1 \
    libxrender1 \
    libdbus-1-3 \
    libfreetype6 \
    # playwright 浏览器所需的额外依赖
    libnss3 \
    libnspr4 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libxss1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# 安装Node.js (使用官方二进制包作为备选方案，包含校验和验证)
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs || \
    (echo "使用备选Node.js二进制包安装方案..." && \
     NODE_VERSION="18.19.0" && \
     NODE_CHECKSUM="1d749fe613950a4900cdcf2fcd96939c8773b2a85aa9ff6cc24c1e0e5b0be9c4" && \
     curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" -o node.tar.xz && \
     echo "${NODE_CHECKSUM} node.tar.xz" | sha256sum -c - && \
     tar -xJ -C /usr/local --strip-components=1 -f node.tar.xz && \
     rm node.tar.xz && \
     node --version && npm --version)

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY runtimes/reasoning/requirements.txt /app/reasoning_requirements.txt
COPY requirements.txt /app/base_requirements.txt

# 安装Python依赖
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r base_requirements.txt && \
    pip install --no-cache-dir -r reasoning_requirements.txt

# 验证关键依赖安装成功
RUN python -c "import matplotlib; import pandas; import numpy; import playwright; print('依赖安装成功!')"

# 安装playwright浏览器 - 使用更健壮的方法
RUN python -m playwright install chromium --with-deps || \
    (echo "第一次安装失败，尝试手动安装依赖..." && \
     apt-get update && \
     apt-get install -y \
        libnss3-dev \
        libatk-bridge2.0-dev \
        libdrm-dev \
        libxcomposite-dev \
        libxdamage-dev \
        libxrandr-dev \
        libgbm-dev \
        libxss-dev \
        libasound2-dev \
        libatspi2.0-0 \
        libgtk-3-0 \
     && python -m playwright install chromium)

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