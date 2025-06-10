#!/bin/bash
# scripts/build.sh

set -e

echo "🔨 Building Agent Data Platform..."

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose not found. Please install Docker Compose first."
    exit 1
fi

# 创建必要目录
echo "📁 Creating directories..."
mkdir -p output/{trajectories,logs}
mkdir -p config/{grafana/dashboards}

# 构建镜像
echo "🐳 Building Docker images..."
docker-compose build --parallel

echo "✅ Build completed successfully!"
echo ""
echo "Next steps:"
echo "1. Create tasks.jsonl with your tasks"
echo "2. Run: ./scripts/deploy.sh"