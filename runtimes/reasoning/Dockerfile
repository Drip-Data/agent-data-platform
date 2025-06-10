FROM python:3.8-slim

# 配置APT使用国内镜像源
RUN sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list && \
    sed -i 's/security.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list

# 配置pip使用国内镜像源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

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