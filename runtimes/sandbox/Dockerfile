FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖和nsjail
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    pkg-config \
    libnl-route-3-dev \
    libprotobuf-dev \
    protobuf-compiler \
    && git clone https://github.com/google/nsjail.git \
    && cd nsjail \
    && make \
    && cp nsjail /usr/local/bin/ \
    && cd .. \
    && rm -rf nsjail \
    && apt-get remove -y build-essential git pkg-config \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# 安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制运行时代码
COPY runtime.py .
COPY ../core/ ./core/

# 创建输出目录
RUN mkdir -p /app/output/{trajectories,logs}

# 暴露metrics端口
EXPOSE 8001

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8001/metrics || exit 1

CMD ["python", "runtime.py"]