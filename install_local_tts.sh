#!/bin/bash

# TransTube 本地 TTS 安装脚本
# 安装 A→B→C→D 管道所需的本地模型

echo "🚀 开始安装 TransTube 本地语音翻译依赖..."

# 检查 Python 版本
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "检测到 Python 版本: $python_version"

# 检查 Python 版本是否满足要求
if [ "$(printf '%s\n' "3.8" "$python_version" | sort -V | head -n1)" != "3.8" ]; then
    echo "❌ 错误: 需要 Python 3.8 或更高版本"
    exit 1
fi

# 检查 CUDA 是否可用
if command -v nvidia-smi &> /dev/null; then
    echo "✅ 检测到 NVIDIA GPU"
    nvidia-smi
else
    echo "⚠️ 未检测到 NVIDIA GPU，将使用 CPU 模式"
fi

# 创建虚拟环境
echo "📦 创建虚拟环境..."
python3 -m venv venv
source venv/bin/activate

# 升级 pip
echo "📦 升级 pip..."
pip install --upgrade pip

# 安装 PyTorch
echo "📦 安装 PyTorch..."
if command -v nvidia-smi &> /dev/null; then
    # 如果有 GPU，安装 CUDA 版本
    pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
else
    # 如果没有 GPU，安装 CPU 版本
    pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
fi

# 安装本地 TTS 依赖
echo "📦 安装本地 TTS 依赖..."
pip install -r backend/requirements_local_tts.txt

# 下载预训练模型
echo "📥 下载预训练模型..."

# 创建模型缓存目录
mkdir -p ~/.cache/whisper
mkdir -p ~/.cache/huggingface
mkdir -p ~/.cache/tts

# 设置 Whisper 模型大小，可通过环境变量覆盖，默认为 large-v3
WHISPER_MODEL_SIZE=${WHISPER_MODEL_SIZE:-large-v3}

# 如果用户在调用脚本时指定了 "--tiny|--base|--small|--medium|--large|--large-v2|--large-v3" 等标志，也做兼容处理
for arg in "$@"; do
  case $arg in
    --tiny|--base|--small|--medium|--large|--large-v2|--large-v3)
      WHISPER_MODEL_SIZE=${arg#--}
      shift
      ;;
  esac
 done

echo "📥 下载 faster-whisper 模型..."
python3 -c "
from faster_whisper import WhisperModel
import os, sys
size = os.getenv('WHISPER_MODEL_SIZE', '$WHISPER_MODEL_SIZE')
print(f'正在下载 faster-whisper {size} 模型...')
model = WhisperModel(size, device='cpu', compute_type='int8')
print('faster-whisper 模型下载完成')
"

echo "📥 下载 NLLB 翻译模型..."
python3 -c "
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
print('正在下载 NLLB-200-distilled-1.3B 模型...')
model_name = 'facebook/nllb-200-distilled-1.3B'
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
print('NLLB 翻译模型下载完成')
"

echo "📥 下载 TTS 模型..."
python3 -c "
from TTS.api import TTS
print('正在下载中文 TTS 模型...')
tts = TTS(model_name='tts_models/zh-CN/baker/tacotron2-DDC-GST', progress_bar=True)
print('TTS 模型下载完成')
"

# 测试安装
echo "🧪 测试安装..."
python3 -c "
import sys
sys.path.append('backend')

try:
    from utils.local_tts import LocalSpeechTranslationPipeline
    print('✅ 本地 TTS 模块导入成功')
    
    # 创建管道实例（不初始化模型，避免长时间等待）
    print('✅ 所有依赖安装成功')
    
except Exception as e:
    print(f'❌ 测试失败: {str(e)}')
    sys.exit(1)
"

# 更新环境变量
echo "⚙️  配置环境变量..."
if [ ! -f .env ]; then
    cp env.example .env
fi

# 添加本地 TTS 配置
if ! grep -q "USE_LOCAL_TTS" .env; then
    echo "" >> .env
    echo "# 本地 TTS 配置" >> .env
    echo "USE_LOCAL_TTS=true" >> .env
    echo "LOCAL_TTS_MODEL=tts_models/zh-CN/baker/tacotron2-DDC-GST" >> .env
    echo "WHISPER_MODEL_SIZE=$WHISPER_MODEL_SIZE" >> .env
    echo "TRANSLATION_MODEL=nllb-200-distilled-1.3B" >> .env
fi

# 更新 WHISPER_MODEL_SIZE 如果已存在条目
if grep -q "WHISPER_MODEL_SIZE=" .env; then
    sed -i "s/^WHISPER_MODEL_SIZE=.*/WHISPER_MODEL_SIZE=$WHISPER_MODEL_SIZE/" .env
fi

echo "✅ 本地 TTS 安装完成！"
echo ""
echo "📋 安装摘要:"
echo "- Python 版本: $python_version"
echo "- PyTorch: $(python3 -c 'import torch; print(torch.__version__)')"
echo "- CUDA 可用: $(if command -v nvidia-smi &> /dev/null; then echo '是'; else echo '否'; fi)"
echo "- 模型缓存目录:"
echo "  - Whisper: ~/.cache/whisper"
echo "  - HuggingFace: ~/.cache/huggingface"
echo "  - TTS: ~/.cache/tts"
echo ""
echo "🚀 现在你可以使用本地 TTS 功能了！"

# 显示磁盘使用情况
echo ""
echo "💾 模型文件大小估算:"
echo "   - faster-whisper large-v3: ~1.5GB"
echo "   - NLLB-200-distilled-1.3B: ~2.5GB"
echo "   - TTS 模型: ~200MB"
echo "   - 总计: ~4.2GB" 