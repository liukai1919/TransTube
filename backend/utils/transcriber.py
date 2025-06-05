# -*- coding: utf-8 -*-
"""
使用 WhisperX 为没有原字幕的视频生成高质量 SRT 文件
WhisperX 提供更准确的单词级时间戳和更好的语音识别效果
"""
import os
import tempfile
import torch
import logging
import subprocess
import ffmpeg
import gc
from typing import Optional, Dict, Any

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 尝试导入 WhisperX，如果失败则回退到 whisper-timestamped
try:
    import whisperx
    WHISPERX_AVAILABLE = True
    logger.info("WhisperX 可用，将使用 WhisperX 进行转录")
except ImportError:
    WHISPERX_AVAILABLE = False
    logger.warning("WhisperX 不可用，回退到 whisper-timestamped")
    try:
        import whisper_timestamped as whisper
        WHISPER_TIMESTAMPED_AVAILABLE = True
    except ImportError:
        WHISPER_TIMESTAMPED_AVAILABLE = False
        logger.error("whisper-timestamped 也不可用，转录功能将不可用")

def check_audio_stream(video_path: str) -> bool:
    """检查视频文件是否包含有效的音频流"""
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'a',
            '-show_entries', 'stream=codec_type',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return 'audio' in result.stdout
    except Exception as e:
        logger.error(f"检查音频流时出错: {str(e)}")
        return False

def get_optimal_device_and_compute_type():
    """获取最优的设备和计算类型配置"""
    if torch.cuda.is_available():
        device = "cuda"
        # 检查 GPU 架构
        gpu_name = torch.cuda.get_device_name(0)
        logger.info(f"检测到 GPU: {gpu_name}")
        
        # 根据 GPU 选择最优计算类型
        if "RTX" in gpu_name or "A100" in gpu_name or "V100" in gpu_name:
            compute_type = "float16"  # 现代 GPU 支持 FP16
        else:
            compute_type = "int8"     # 较老的 GPU 使用 INT8
            
        # 获取 GPU 内存
        gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024 / 1024 / 1024
        logger.info(f"GPU 内存: {gpu_memory:.1f}GB")
        
        # 根据内存选择批处理大小
        if gpu_memory >= 16:
            batch_size = 16
        elif gpu_memory >= 8:
            batch_size = 8
        else:
            batch_size = 4
            
    else:
        device = "cpu"
        compute_type = "int8"
        batch_size = 1
        logger.info("使用 CPU 进行转录")
    
    return device, compute_type, batch_size

def init_whisperx_model(model_size: str = "medium", language: str = "en"):
    """初始化 WhisperX 模型"""
    try:
        device, compute_type, batch_size = get_optimal_device_and_compute_type()
        
        logger.info(f"正在加载 WhisperX {model_size} 模型...")
        logger.info(f"设备: {device}, 计算类型: {compute_type}, 批处理大小: {batch_size}")
        
        # 加载 Whisper 模型
        model = whisperx.load_model(
            model_size, 
            device, 
            compute_type=compute_type,
            language=language
        )
        
        logger.info("WhisperX 模型加载完成")
        return model, device, batch_size
        
    except Exception as e:
        logger.error(f"初始化 WhisperX 失败: {str(e)}", exc_info=True)
        raise Exception(f"初始化 WhisperX 失败: {str(e)}")

def init_whisper_timestamped():
    """初始化 whisper-timestamped 模型（fallback）"""
    try:
        # 设置 PyTorch CUDA 内存分配器配置
        os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'
        
        # 检查 CUDA 是否可用
        if torch.cuda.is_available():
            logger.info("CUDA 可用，将使用 GPU 加速")
            device = "cuda"
            torch.cuda.set_per_process_memory_fraction(0.5)
            torch.cuda.empty_cache()
        else:
            logger.info("CUDA 不可用，将使用 CPU")
            device = "cpu"
        
        # 加载模型
        logger.info("正在加载 whisper-timestamped medium 模型...")
        model = whisper.load_model("medium", device=device)
        logger.info("whisper-timestamped 模型加载完成")
        return model
        
    except Exception as e:
        logger.error(f"初始化 whisper-timestamped 失败: {str(e)}", exc_info=True)
        raise Exception(f"初始化语音识别失败: {str(e)}")

def format_timestamp(seconds: float) -> str:
    """
    将秒数格式化为 SRT 时间戳格式 (HH:MM:SS,mmm)
    
    Args:
        seconds: 秒数
        
    Returns:
        str: 格式化的时间戳
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = seconds % 60
    milliseconds = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"

def transcribe_with_whisperx(video_path: str, lang: str = "en") -> str:
    """使用 WhisperX 进行转录"""
    try:
        # 初始化模型
        model, device, batch_size = init_whisperx_model("base", lang)
        
        # 加载音频
        logger.info("正在加载音频...")
        audio = whisperx.load_audio(video_path)
        
        # 转录
        logger.info("开始 WhisperX 转录...")
        result = model.transcribe(audio, batch_size=batch_size)
        
        # 加载对齐模型
        logger.info("正在加载对齐模型...")
        model_a, metadata = whisperx.load_align_model(
            language_code=result["language"], 
            device=device
        )
        
        # 对齐转录结果
        logger.info("正在对齐转录结果...")
        result = whisperx.align(
            result["segments"], 
            model_a, 
            metadata, 
            audio, 
            device, 
            return_char_alignments=False
        )
        
        # 生成 SRT 文件
        logger.info("生成 SRT 文件...")
        srt_path = tempfile.mktemp(suffix=".srt")
        with open(srt_path, "w", encoding="utf-8") as f:
            previous_end_time = 0.0
            for i, segment in enumerate(result["segments"], start=1):
                start_time = segment["start"]
                end_time = segment["end"]

                # Ensure minimum duration and prevent overlap
                if end_time - start_time < 0.5:
                    end_time = start_time + 0.5
                
                if start_time < previous_end_time:
                    start_time = previous_end_time
                    if end_time <= start_time: # Ensure end is after start
                        end_time = start_time + 0.5

                # Update previous_end_time for the next iteration
                previous_end_time = end_time

                start_formatted = format_timestamp(start_time)
                end_formatted = format_timestamp(end_time)
                text = segment["text"].strip()
                if text:
                    f.write(f"{i}\n{start_formatted} --> {end_formatted}\n{text}\n\n")
        
        # 清理内存
        del model, model_a, audio, result
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
        
        logger.info(f"WhisperX 转录完成，SRT 文件已保存到: {srt_path}")
        return srt_path
        
    except Exception as e:
        logger.error(f"WhisperX 转录失败: {str(e)}", exc_info=True)
        raise

def transcribe_with_whisper_timestamped(video_path: str, lang: str = "en") -> str:
    """使用 whisper-timestamped 进行转录（fallback）"""
    try:
        # 初始化模型
        model = init_whisper_timestamped()
        
        # 转录音频
        logger.info("开始 whisper-timestamped 转录...")
        result = model.transcribe(
            video_path,
            language=lang,
            task="transcribe",
            fp16=True if torch.cuda.is_available() else False,
            verbose=True
        )
        
        # 生成 SRT 文件
        logger.info("生成 SRT 文件...")
        srt_path = tempfile.mktemp(suffix=".srt")
        with open(srt_path, "w", encoding="utf-8") as f:
            previous_end_time = 0.0
            for i, segment in enumerate(result["segments"], start=1):
                start_time = segment["start"]
                end_time = segment["end"]

                # Ensure minimum duration and prevent overlap
                if end_time - start_time < 0.5:
                    end_time = start_time + 0.5
                
                if start_time < previous_end_time:
                    start_time = previous_end_time
                    if end_time <= start_time: # Ensure end is after start
                        end_time = start_time + 0.5

                # Update previous_end_time for the next iteration
                previous_end_time = end_time

                start_formatted = format_timestamp(start_time)
                end_formatted = format_timestamp(end_time)
                text = segment["text"].strip()
                if text:
                    f.write(f"{i}\n{start_formatted} --> {end_formatted}\n{text}\n\n")
        
        # 清理内存
        del model, result
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
                
        logger.info(f"whisper-timestamped 转录完成，SRT 文件已保存到: {srt_path}")
        return srt_path 
        
    except Exception as e:
        logger.error(f"whisper-timestamped 转录失败: {str(e)}", exc_info=True)
        raise

def transcribe_to_srt(video_path: str, lang: str = "en") -> str:
    """
    将视频转录为 SRT 字幕文件
    优先使用 WhisperX，如果不可用则回退到 whisper-timestamped
    
    Args:
        video_path: 视频文件路径
        lang: 语言代码，默认英语
        
    Returns:
        str: 生成的 SRT 文件路径
    """
    try:
        # 检查视频文件
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
            
        # 检查音频流
        logger.info(f"检查视频音频流: {video_path}")
        probe = ffmpeg.probe(video_path)
        audio_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'audio'), None)
        if not audio_stream:
            raise ValueError("视频文件没有音频流")
        
        # 选择转录方法
        if WHISPERX_AVAILABLE:
            logger.info("使用 WhisperX 进行转录")
            return transcribe_with_whisperx(video_path, lang)
        elif WHISPER_TIMESTAMPED_AVAILABLE:
            logger.info("使用 whisper-timestamped 进行转录")
            return transcribe_with_whisper_timestamped(video_path, lang)
        else:
            raise Exception("没有可用的转录引擎，请安装 WhisperX 或 whisper-timestamped")
        
    except Exception as e:
        logger.error(f"转录失败: {str(e)}", exc_info=True)
        raise Exception(f"转录失败: {str(e)}")