#!/bin/bash

# TransTube 一键启动脚本

echo "🚀 启动 TransTube 服务..."

# 检查 Docker 和 Docker Compose
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose 未安装，请先安装 Docker Compose"
    exit 1
fi

# 检查 NVIDIA Docker 支持
if ! docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi &> /dev/null; then
    echo "⚠️  警告：NVIDIA Docker 支持未检测到，将使用 CPU 模式"
    export USE_GPU=false
else
    echo "✅ 检测到 NVIDIA GPU 支持"
    export USE_GPU=true
fi

# 创建环境文件
if [ ! -f .env ]; then
    echo "📝 创建环境配置文件..."
    cp env.example .env
    echo "⚠️  请编辑 .env 文件配置您的 API 密钥"
fi

# 创建必要的目录
echo "📁 创建必要的目录..."
mkdir -p backend/downloads backend/static/videos backend/static/subtitles backend/logs

# 启动服务
echo "🐳 启动 Docker 服务..."
docker-compose up -d

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 10

# 检查服务状态
echo "🔍 检查服务状态..."
docker-compose ps

# 下载 Ollama 模型（如果需要）
echo "📥 初始化 Ollama 模型..."
docker-compose exec -d ollama ollama pull gpt-oss:20b

echo "✅ TransTube 启动完成！"
echo ""
echo "🌐 访问地址："
echo "   前端: http://localhost:3001"
echo "   后端 API: http://localhost:8000"
echo "   Ollama: http://localhost:11434"
echo ""
echo "📚 使用说明："
echo "   1. 在前端页面输入 YouTube 视频链接"
echo "   2. 等待处理完成"
echo "   3. 下载带中文字幕的视频"
echo ""
echo "🛠️  管理命令："
echo "   停止服务: docker-compose down"
echo "   查看日志: docker-compose logs -f"
echo "   重启服务: docker-compose restart" 