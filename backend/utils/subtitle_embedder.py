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

def get_video_dimensions(video_path):
    """获取视频尺寸"""
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height',
        '-of', 'json',
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"获取视频尺寸失败: {result.stderr}")
    
    import json
    data = json.loads(result.stdout)
    width = int(data['streams'][0]['width'])
    height = int(data['streams'][0]['height'])
    return width, height

def calculate_subtitle_style(width, height):
    """根据视频尺寸和宽高比智能计算字幕样式"""
    
    # 计算宽高比
    aspect_ratio = width / height
    
    # 判断视频类型
    if aspect_ratio > 1.7:  # 超宽屏 (21:9 等)
        video_type = "ultrawide"
    elif aspect_ratio > 1.5:  # 标准宽屏 (16:9, 16:10 等)
        video_type = "widescreen" 
    elif aspect_ratio > 1.2:  # 传统宽屏 (4:3 等)
        video_type = "standard"
    else:  # 竖屏或方形
        video_type = "portrait"
    
    # 根据分辨率类别调整参数
    if height >= 2160:  # 4K
        resolution_class = "4k"
        base_font_ratio = 0.010  # 进一步减少到1.0%（之前是1.2%）
        margin_ratio = 0.015
    elif height >= 1440:  # 2K/1440p
        resolution_class = "2k"
        base_font_ratio = 0.012  # 进一步减少到1.2%（之前是1.4%）
        margin_ratio = 0.018
    elif height >= 1080:  # 1080p
        resolution_class = "1080p"
        base_font_ratio = 0.013  # 进一步减少到1.3%（之前是1.5%）
        margin_ratio = 0.02
    elif height >= 720:  # 720p
        resolution_class = "720p"
        base_font_ratio = 0.015  # 进一步减少到1.5%（之前是1.8%）
        margin_ratio = 0.025
    else:  # 480p及以下
        resolution_class = "sd"
        base_font_ratio = 0.018  # 进一步减少到1.8%（之前是2.2%）
        margin_ratio = 0.03
    
    # 根据视频类型调整
    if video_type == "portrait":
        # 竖屏视频需要调整
        base_font_ratio *= 1.2  # 竖屏字体稍大
        margin_ratio *= 0.8     # 竖屏边距稍小
        alignment = 2           # 居中
        margin_l = int(width * 0.05)  # 左右边距按宽度比例
        margin_r = int(width * 0.05)
    elif video_type == "ultrawide":
        # 超宽屏视频
        base_font_ratio *= 0.9  # 超宽屏字体稍小
        margin_ratio *= 1.1     # 边距稍大
        alignment = 2           # 居中
        margin_l = int(width * 0.1)   # 超宽屏左右边距更大
        margin_r = int(width * 0.1)
    else:
        # 标准宽屏
        alignment = 2
        margin_l = 20
        margin_r = 20
    
    # 计算最终参数
    base_font_size = int(height * base_font_ratio)
    
    # 字体大小限制
    if resolution_class == "4k":
        font_size = max(12, min(base_font_size, 24))  # 减少到12-24px（之前是14-28px）
    elif resolution_class == "2k":
        font_size = max(10, min(base_font_size, 20))  # 减少到10-20px（之前是12-24px）
    elif resolution_class == "1080p":
        font_size = max(8, min(base_font_size, 16))   # 减少到8-16px（之前是10-20px）
    elif resolution_class == "720p":
        font_size = max(6, min(base_font_size, 12))   # 减少到6-12px（之前是8-16px）
    else:  # SD
        font_size = max(5, min(base_font_size, 10))   # 减少到5-10px（之前是6-12px）
    
    margin_v = int(height * margin_ratio)
    
    # 根据分辨率调整描边和阴影
    if height >= 1440:
        outline_width = 1.5
        shadow_depth = 2
    elif height >= 720:
        outline_width = 1
        shadow_depth = 1
    else:
        outline_width = 0.8
        shadow_depth = 1
    
    # 构建样式字符串
    style = (
        f"FontName=Noto Sans SC,"
        f"FontSize={font_size},"
        f"PrimaryColour=&HFFFFFF&,"
        f"OutlineColour=&H000000&,"
        f"Outline={outline_width},"
        f"ShadowColour=&H000000&,"
        f"ShadowDepth={shadow_depth},"
        f"BorderStyle=1,"
        f"Alignment={alignment},"
        f"MarginV={margin_v},"
        f"MarginL={margin_l},"
        f"MarginR={margin_r}"
    )
    
    logger.info(f"视频类型: {video_type}, 分辨率等级: {resolution_class}, "
                f"宽高比: {aspect_ratio:.2f}, 字体大小: {font_size}, "
                f"边距: V={margin_v} L={margin_l} R={margin_r}")
    
    return style

def burn_subtitle(video_path: str, srt_path: str, output_file_path: str) -> str:
    """
    将字幕烧录到视频中，使用 GPU 加速，失败时回退到 CPU
    output_file_path: 指定的最终输出文件路径
    """
    temp_video_dir = None
    temp_srt_dir = None
    temp_output_dir = None
    try:
        # 验证输入文件
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        if not os.path.exists(srt_path):
            raise FileNotFoundError(f"字幕文件不存在: {srt_path}")
        
        logger.info(f"开始烧录字幕，视频: {video_path}, 字幕: {srt_path}")

        # 获取视频尺寸
        width, height = get_video_dimensions(video_path)
        logger.info(f"视频尺寸: {width}x{height}")
        
        # 计算字幕样式
        subtitle_style = calculate_subtitle_style(width, height)
        logger.info(f"字幕样式: {subtitle_style}")

        # 创建临时目录
        temp_video_dir = tempfile.mkdtemp()
        temp_srt_dir = tempfile.mkdtemp()
        temp_output_dir = tempfile.mkdtemp()
        
        # 复制视频和字幕到临时目录
        temp_video_filename = "input_video" + os.path.splitext(video_path)[1]
        temp_video_path = os.path.join(temp_video_dir, temp_video_filename)
        temp_srt_internal_path = os.path.join(temp_srt_dir, "subtitles.srt")

        shutil.copy2(video_path, temp_video_path)
        shutil.copy2(srt_path, temp_srt_internal_path)
        
        # 设置输出路径
        output_path = os.path.join(temp_output_dir, "output.mp4")
        
        # 构建字幕滤镜
        subtitle_filter_value = f"subtitles={temp_srt_internal_path}:force_style='{subtitle_style}'"
        logger.info(f"FFmpeg subtitles filter: {subtitle_filter_value}")

        # 首先尝试GPU编码
        gpu_success = False
        try:
            logger.info("尝试使用GPU编码...")
            cmd_gpu = [
                'ffmpeg',
                '-i', temp_video_path,
                '-vf', subtitle_filter_value,
                '-c:v', 'h264_nvenc',
                '-preset', 'p4',
                '-rc', 'vbr',
                '-cq', '19',
                '-b:v', '0',
                '-c:a', 'copy',
                '-y',
                output_path
            ]
            
            logger.info(f"Executing GPU command: {' '.join(cmd_gpu)}")
            result = subprocess.run(cmd_gpu, check=True, capture_output=True, text=True)
            gpu_success = True
            logger.info("GPU编码成功")
            
        except subprocess.CalledProcessError as e:
            logger.warning(f"GPU编码失败，回退到CPU编码. FFmpeg stderr: {e.stderr}")
            
            # 回退到CPU编码
            cmd_cpu = [
                'ffmpeg',
                '-i', temp_video_path,
                '-vf', subtitle_filter_value,
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                '-c:a', 'copy',
                '-y',
                output_path
            ]
            
            logger.info(f"Executing CPU command: {' '.join(cmd_cpu)}")
            result = subprocess.run(cmd_cpu, check=True, capture_output=True, text=True)
            logger.info("CPU编码成功")
        
        # 验证输出文件
        if not os.path.exists(output_path):
            raise FileNotFoundError("FFmpeg 输出文件不存在")
            
        file_size = os.path.getsize(output_path)
        logger.info(f"输出文件大小: {file_size / (1024*1024):.2f} MB")
        
        if file_size < 100000:  # 小于100KB可能有问题
            logger.warning(f"输出文件太小 ({file_size} bytes)，可能有问题")
        
        # 确保目标目录存在
        Path(output_file_path).parent.mkdir(parents=True, exist_ok=True)
        
        # 复制文件到指定的 output_file_path
        shutil.copy2(output_path, output_file_path)
        logger.info(f"成功将输出文件复制到: {output_file_path}")
        
        return output_file_path
    
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg 错误: {e.stderr}")
        raise Exception(f"字幕烧录失败: {str(e)}") 
    
    finally:
        # 清理临时文件和目录
        try:
            if temp_video_dir and os.path.exists(temp_video_dir):
                shutil.rmtree(temp_video_dir)
                logger.info(f"已清理临时视频目录: {temp_video_dir}")
            if temp_srt_dir and os.path.exists(temp_srt_dir):
                shutil.rmtree(temp_srt_dir)
                logger.info(f"已清理临时字幕目录: {temp_srt_dir}")
            if temp_output_dir and os.path.exists(temp_output_dir):
                shutil.rmtree(temp_output_dir)
                logger.info(f"已清理临时输出目录: {temp_output_dir}")
        except Exception as e:
            logger.warning(f"清理临时文件时出错: {str(e)}") 