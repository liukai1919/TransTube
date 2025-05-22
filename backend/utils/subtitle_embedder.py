# -*- coding: utf-8 -*-
"""
调用 FFmpeg 将中文字幕烧录进视频
"""
import os, subprocess, tempfile, shutil, logging, shlex, re
from pathlib import Path

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 可能的字体路径列表
FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.otf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-Regular.ttf"
]

def check_gpu_support():
    """检查是否支持 GPU 加速"""
    try:
        # 检查 NVIDIA GPU 是否可用
        nvidia_smi = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
        if nvidia_smi.returncode == 0:
            # 检查 FFmpeg 是否支持 NVENC
            ffmpeg_encoders = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True)
            if 'h264_nvenc' in ffmpeg_encoders.stdout:
                logger.info("检测到 NVIDIA GPU 和 NVENC 支持，将使用 GPU 加速")
                return True
            else:
                logger.warning("FFmpeg 未编译 NVENC 支持，将使用 CPU 编码")
        else:
            logger.info("未检测到 NVIDIA GPU，将使用 CPU 编码")
    except Exception as e:
        logger.error(f"检查 GPU 支持时出错: {e}")
    return False

def find_available_font():
    """查找可用的字体文件"""
    for font_path in FONT_PATHS:
        if os.path.exists(font_path):
            return font_path
    return None

def sanitize_path_for_ffmpeg(file_path):
    """处理文件路径，确保FFmpeg能正确处理特殊字符"""
    # 使用Path对象确保路径是绝对路径并转换为字符串
    path_str = str(Path(file_path).resolve())
    # 将文件路径复制到临时文件夹，使用随机文件名避免特殊字符
    temp_dir = tempfile.mkdtemp()
    
    # 确定文件扩展名
    ext = os.path.splitext(path_str)[1]
    temp_file = os.path.join(temp_dir, f"temp_file{ext}")
    
    # 复制文件
    shutil.copy2(path_str, temp_file)
    logger.info(f"将文件 '{path_str}' 复制到临时位置 '{temp_file}'")
    
    return temp_file, temp_dir

def burn_subtitle(video_path: str, srt_path: str) -> str:
    """
    将字幕烧录到视频中
    """
    logger.info(f"开始烧录字幕: 视频={video_path}, 字幕={srt_path}")
    
    # 检查文件是否存在
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")
    if not os.path.exists(srt_path):
        raise FileNotFoundError(f"字幕文件不存在: {srt_path}")
    
    # 处理文件路径中的特殊字符
    temp_video_path, temp_video_dir = sanitize_path_for_ffmpeg(video_path)
    temp_srt_path, temp_srt_dir = sanitize_path_for_ffmpeg(srt_path)

    try:
        # 创建临时输出文件 (使用临时目录确保无特殊字符)
        temp_output_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_output_dir, "output.mp4")
        
        # 查找可用字体并构建 filter 字符串
        font_path = find_available_font()
        if font_path:
            force_style = f"FontName={os.path.basename(font_path)},FontSize=18"
            filter_str = f"subtitles={temp_srt_path}:fontsdir={os.path.dirname(font_path)}:force_style='{force_style}'"
        else:
            filter_str = f"subtitles={temp_srt_path}:force_style=FontSize=18"
        
        # 检查是否支持 GPU
        use_gpu = check_gpu_support()
        
        # 构建基础命令
        command = [
            'ffmpeg', '-hide_banner',
            '-i', temp_video_path,
            '-vf', filter_str,
        ]
        
        # 根据是否支持 GPU 添加编码器参数
        if use_gpu:
            command.extend([
                '-c:v', 'h264_nvenc',  # 使用 NVIDIA 硬件编码器
                '-preset', 'p4',  # NVENC 预设
                '-tune', 'hq',  # 高质量调优
                '-rc', 'vbr',  # 可变比特率
                '-cq', '23',  # 质量参数
                '-b:v', '0',  # 自动比特率
                '-spatial-aq', '1',  # 空间自适应量化
                '-temporal-aq', '1',  # 时间自适应量化
            ])
        else:
            command.extend([
                '-c:v', 'libx264',  # 使用 CPU 编码器
                '-preset', 'medium',
                '-crf', '23',
                '-profile:v', 'high',
                '-level', '4.0',
            ])
        
        # 添加通用参数
        command.extend([
            '-pix_fmt', 'yuv420p',  # 像素格式，确保兼容性
            '-movflags', '+faststart',  # 优化网络播放
            '-c:a', 'copy',  # 复制音频流
            '-y',  # 覆盖已存在的文件
            '-threads', '0',  # 自动选择线程数
            output_path
        ])
        
        # 打印完整命令以便调试
        logger.info("Running: " + " ".join(command))
        
        # 执行命令
        result = subprocess.run(command, capture_output=True, text=True)
        if result.stderr:
            logger.warning(f"FFmpeg 警告: {result.stderr}")
        result.check_returncode()  # 这会抛出异常并包含完整的 stderr
        
        # 验证输出文件
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"FFmpeg 未能生成输出文件: {output_path}")
        
        file_size = os.path.getsize(output_path)
        logger.info(f"FFmpeg 生成的文件大小: {file_size / (1024*1024):.2f} MB")
        
        if file_size < 100000:  # 小于100KB可能有问题
            logger.warning(f"输出文件太小 ({file_size} bytes)，可能有问题")
        
        # 将输出文件复制到原始视频所在目录，并命名为"原文件名.sub.mp4"
        original_dir = os.path.dirname(video_path)
        original_name = os.path.basename(video_path).rsplit('.', 1)[0]
        final_output_path = os.path.join(original_dir, f"{original_name}.sub.mp4")
        
        # 复制文件
        shutil.copy2(output_path, final_output_path)
        logger.info(f"成功将输出文件复制到: {final_output_path}")
        
        return final_output_path
    
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg 错误: {e.stderr}")
        raise Exception(f"字幕烧录失败: {str(e)}")
    
    finally:
        # 清理临时文件和目录
        try:
            if os.path.exists(temp_video_dir):
                shutil.rmtree(temp_video_dir)
            if os.path.exists(temp_srt_dir):
                shutil.rmtree(temp_srt_dir)
            if os.path.exists(temp_output_dir):
                shutil.rmtree(temp_output_dir)
        except Exception as e:
            logger.warning(f"清理临时文件时出错: {str(e)}") 