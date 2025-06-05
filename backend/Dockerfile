# 使用 NVIDIA CUDA 基础镜像
FROM nvidia/cuda:12.1-devel-ubuntu22.04

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV CUDA_VISIBLE_DEVICES=0
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility,video

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    ffmpeg \
    git \
    wget \
    curl \
    software-properties-common \
    fonts-dejavu \
    fonts-liberation \
    fonts-noto-cjk \
    fonts-wqy-zenhei \
    fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

# 创建工作目录
WORKDIR /app

# 复制依赖文件
COPY requeirements.txt .

# 安装 Python 依赖
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 && \
    pip3 install --no-cache-dir -r requeirements.txt

# 安装 WhisperX
RUN pip3 install --no-cache-dir git+https://github.com/m-bain/whisperx.git

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p downloads static/videos static/subtitles logs && \
    chmod 777 downloads static/videos static/subtitles logs

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/videos || exit 1

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"] 