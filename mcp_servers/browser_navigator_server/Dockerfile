FROM python:3.10-slim

WORKDIR /app

COPY . /app

COPY requirements.txt .

RUN pip install --default-timeout=100 --upgrade pip && pip install --no-cache-dir -r requirements.txt

EXPOSE 8082

ENV TOOLSCORE_URL="ws://toolscore:8080/websocket"
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "mcp_servers.browser_navigator_server.main:app", "--host", "0.0.0.0", "--port", "8082"]