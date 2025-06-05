FROM python:3.10-slim

WORKDIR /app

# 暂时跳过NSJail安装，使用基础Python环境
# TODO: 后续添加NSJail支持
RUN echo 'NSJail installation skipped for now'

# 安装Python依赖
COPY requirements.txt /tmp/base_requirements.txt
COPY runtimes/sandbox/requirements.txt /tmp/sandbox_requirements.txt
RUN pip install --upgrade pip --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org && \
    pip install --no-cache-dir -r /tmp/base_requirements.txt --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org && \
    pip install --no-cache-dir -r /tmp/sandbox_requirements.txt --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org

# 复制运行时代码
COPY runtimes/sandbox/runtime.py .
COPY core/ ./core/

# 创建输出目录和沙盒目录
RUN mkdir -p /app/output/{trajectories,logs} \
    && mkdir -p /tmp/sandbox \
    && chmod 755 /tmp/sandbox

# 暴露metrics端口
EXPOSE 8001

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8001/metrics || exit 1

CMD ["python", "runtime.py"]