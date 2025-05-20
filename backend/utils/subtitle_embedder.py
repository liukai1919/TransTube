# -*- coding: utf-8 -*-
"""
调用 FFmpeg 将中文字幕烧录进视频
"""
import os, subprocess, tempfile, shutil

# For Linux, use NotoSansSC
FONT = "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.otf"

def burn_subtitle(video_path: str, srt_path: str) -> str:
    """
    将字幕烧录到视频中
    """
    # 创建临时输出文件
    output_path = video_path.replace('.mp4', '.sub.mp4')
    
    # 构建 FFmpeg 命令
    command = [
        'ffmpeg',
        '-i', video_path,
        '-vf', f"subtitles={srt_path}:force_style='FontName=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf,FontSize=20,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,Outline=1,BorderStyle=3,MarginV=25'",
        '-c:v', 'libx264',  # 使用 H.264 编码
        '-preset', 'medium',  # 编码速度预设
        '-crf', '23',  # 视频质量参数
        '-c:a', 'aac',  # 音频编码
        '-b:a', '128k',  # 音频比特率
        '-vsync', '0',  # 视频同步模式
        '-async', '1',  # 音频同步模式
        '-y',  # 覆盖已存在的文件
        output_path
    ]
    
    try:
        # 执行命令
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        print(f"FFmpeg 输出: {result.stdout}")
        if result.stderr:
            print(f"FFmpeg 警告: {result.stderr}")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg 错误: {e.stderr}")
        raise Exception(f"字幕烧录失败: {str(e)}") 
