# -*- coding: utf-8 -*-
"""
使用 Whisper Timestamped 为没有原字幕的视频生成 SRT 文件
"""
import os
import whisper_timestamped as whisper
import srt
import datetime
import tempfile
import torch
import logging
import subprocess
import ffmpeg

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

def init_whisper():
    """初始化 Whisper 模型"""
    try:
        # 检查 CUDA 是否可用
        if torch.cuda.is_available():
            logger.info("CUDA 可用，将使用 GPU 加速")
            # 获取当前 CUDA 版本
            cuda_version = torch.version.cuda
            logger.info(f"CUDA 版本: {cuda_version}")
            
            # 获取 GPU 信息
            gpu_name = torch.cuda.get_device_name(0)
            logger.info(f"GPU 型号: {gpu_name}")
            
            # 获取 GPU 内存信息
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024 / 1024
            logger.info(f"GPU 总内存: {gpu_memory:.1f}MB")
            
            # 设置设备
            device = "cuda"
            # 设置 CUDA 内存分配器
            torch.cuda.set_per_process_memory_fraction(0.8)  # 使用 80% 的 GPU 内存
            torch.cuda.empty_cache()  # 清空 GPU 缓存
        else:
            logger.info("CUDA 不可用，将使用 CPU")
            device = "cpu"
        
        # 加载模型
        logger.info("正在加载 Whisper 模型...")
        model = whisper.load_model("large-v3", device=device)
        logger.info("Whisper 模型加载完成")
        return model
        
    except Exception as e:
        logger.error(f"初始化 Whisper 失败: {str(e)}", exc_info=True)
        raise Exception(f"初始化语音识别失败: {str(e)}")

def transcribe_to_srt(video_path: str, lang="en") -> str:
    """
    将视频转录为 SRT 字幕文件
    
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
            
        # 初始化 Whisper
        model = init_whisper()
        
        # 转录音频
        logger.info("开始转录音频...")
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
            for i, segment in enumerate(result["segments"], start=1):
                start = format_timestamp(segment["start"])
                end = format_timestamp(segment["end"])
                text = segment["text"].strip()
                f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
                
        logger.info(f"转录完成，SRT 文件已保存到: {srt_path}")
        return srt_path
        
    except Exception as e:
        logger.error(f"转录失败: {str(e)}", exc_info=True)
        raise Exception(f"转录失败: {str(e)}") 