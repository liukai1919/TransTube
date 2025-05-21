# -*- coding: utf-8 -*-
"""
下载 YouTube 视频及其原字幕
"""
import os
import subprocess
import json
import tempfile
import uuid
import re
import logging
from yt_dlp import YoutubeDL
from youtube_transcript_api import YouTubeTranscriptApi, _errors
from youtube_transcript_api.formatters import SRTFormatter

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_video_id(url: str) -> str:
    """从 YouTube URL 中提取视频 ID"""
    # 匹配各种 YouTube URL 格式
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',  # 标准格式
        r'youtu\.be\/([0-9A-Za-z_-]{11})',   # 短链接
        r'youtube\.com\/embed\/([0-9A-Za-z_-]{11})',  # 嵌入格式
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    raise ValueError("无法从 URL 中提取视频 ID")

def validate_transcript(transcript):
    """
    验证字幕数据格式
    
    Args:
        transcript: 字幕数据
        
    Returns:
        bool: 验证是否通过
    """
    if not isinstance(transcript, list):
        raise ValueError(f"字幕数据格式错误：期望列表，得到 {type(transcript).__name__}")
        
    for i, item in enumerate(transcript):
        if not isinstance(item, dict):
            raise ValueError(f"字幕数据格式错误：第 {i+1} 项不是字典")
            
        required_fields = ['start', 'end', 'text']
        missing_fields = [field for field in required_fields if field not in item]
        if missing_fields:
            raise ValueError(f"字幕数据格式错误：第 {i+1} 项缺少必要字段 {missing_fields}")
            
        # 验证时间戳格式
        if not isinstance(item['start'], (int, float)) or not isinstance(item['end'], (int, float)):
            raise ValueError(f"字幕数据格式错误：第 {i+1} 项的时间戳不是数字")
            
        # 验证文本格式
        if not isinstance(item['text'], str):
            raise ValueError(f"字幕数据格式错误：第 {i+1} 项的文本不是字符串")
            
    return True

def download_video(url: str, download_dir: str):
    """
    下载视频和字幕
    返回: (视频路径, 字幕路径, 视频ID, 视频标题, 视频时长)
    """
    try:
        # 从URL中提取视频ID
        video_id = extract_video_id(url)
        logger.info(f"提取到视频ID: {video_id}")
        
        # 生成唯一ID
        vid = str(uuid.uuid4())
        
        # 设置下载选项
        ydl_opts = {
            # 下载最高质量的视频+音频并合并
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(download_dir, f'{vid}.%(ext)s'),
            'merge_output_format': 'mp4',  # 确保输出为mp4格式
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            # 可视化下载进度
            'quiet': False,
            'no_warnings': False,
            'progress': True,
            'skip_download': False,
            # 使用 cookies 文件
            'cookiefile': 'youtube.cookies',
        }
        
        # 下载视频
        with YoutubeDL(ydl_opts) as ydl:
            logger.info(f"开始下载视频: {url}")
            info = ydl.extract_info(url, download=True)
            video_path = os.path.join(download_dir, f'{vid}.mp4')
            title = info.get('title', 'video')
            duration = info.get('duration', 0)  # 获取视频时长（秒）
            logger.info(f"视频下载完成: {video_path}, 时长: {duration}秒")
            
        # 尝试获取字幕
        srt_path = None
        try:
            logger.info(f"尝试获取字幕，视频ID: {video_id}")
            
            # 尝试使用youtube_transcript_api获取字幕
            try:
                transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
                logger.info("成功获取英文字幕")
                
                # 验证字幕数据格式
                validate_transcript(transcript)
                
                # 转换为SRT格式
                formatter = SRTFormatter()
                srt_formatted = formatter.format_transcript(transcript)
                
                # 保存字幕文件
                srt_path = os.path.join(download_dir, f'{vid}.srt')
                with open(srt_path, 'w', encoding='utf-8') as f:
                    f.write(srt_formatted)
                
                logger.info(f"字幕保存到: {srt_path}")
            except _errors.TranscriptsDisabled:
                logger.warning("视频禁用了字幕")
                srt_path = None
            except _errors.NoTranscriptFound:
                logger.warning("未找到英文字幕，尝试自动生成的字幕")
                try:
                    # 获取自动生成的字幕
                    transcript = YouTubeTranscriptApi.get_transcript(
                        video_id,
                        languages=['en'],
                        preserve_formatting=True
                    )
                    
                    # 验证字幕数据格式
                    validate_transcript(transcript)
                    
                    # 转换为SRT格式
                    formatter = SRTFormatter()
                    srt_formatted = formatter.format_transcript(transcript)
                    
                    srt_path = os.path.join(download_dir, f'{vid}.srt')
                    with open(srt_path, 'w', encoding='utf-8') as f:
                        f.write(srt_formatted)
                    logger.info(f"自动生成的字幕保存到: {srt_path}")
                except Exception as inner_e:
                    logger.warning(f"获取自动生成字幕失败: {str(inner_e)}")
                    srt_path = None
            except Exception as general_e:
                logger.warning(f"获取字幕时出现一般错误: {str(general_e)}")
                srt_path = None
                
        except Exception as e:
            logger.error(f"字幕处理过程中出错: {str(e)}")
            srt_path = None
        
        # 验证字幕文件是否有效
        if srt_path and os.path.exists(srt_path):
            # 检查文件大小和内容
            if os.path.getsize(srt_path) < 10:  # 文件太小，可能是空的
                logger.warning(f"字幕文件太小，可能无效: {srt_path}")
                srt_path = None
        else:
            logger.warning("没有生成字幕文件或文件不存在")
            srt_path = None
            
        logger.info(f"下载完成。视频: {video_path}, 字幕: {srt_path if srt_path else '无'}")
        return video_path, srt_path, vid, title, duration
        
    except Exception as e:
        logger.error(f"视频下载过程中出错: {str(e)}")
        raise Exception(f"视频下载失败: {str(e)}")