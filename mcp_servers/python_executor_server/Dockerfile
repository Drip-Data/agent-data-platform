# 使用官方Python运行时作为父镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 复制当前目录下的所有文件到容器的/app目录
COPY . /app

# 安装所需的Python包
# 注意：这里需要根据实际的依赖来安装，例如 websockets, uvicorn, pandas, matplotlib 等
# 假设所有依赖都在 requirements.txt 中
COPY requirements.txt .
RUN pip install --default-timeout=100 --upgrade pip && pip install --no-cache-dir -r requirements.txt

# 暴露MCP Server运行的端口
EXPOSE 8001

# 定义环境变量
ENV TOOLSCORE_URL="ws://toolscore:8000/websocket"
ENV PYTHONUNBUFFERED=1

# 启动MCP Server
# 使用 uvicorn 启动 FastAPI 应用
CMD ["uvicorn", "mcp_servers.python_executor_server.main:app", "--host", "0.0.0.0", "--port", "8001"]