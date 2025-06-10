FROM python:3.11-slim

# 安装依赖
RUN pip install --no-cache-dir mcp fastapi uvicorn Pillow

# 创建工作目录
WORKDIR /app

# 复制服务器代码
COPY simple_image_server.py .

# 暴露端口
EXPOSE 8080

# 设置环境变量
ENV DOCKER_CONTAINER=true
ENV MCP_SERVER_PORT=8080

# 启动命令
CMD ["python", "simple_image_server.py"] 