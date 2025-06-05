import os
import yt_dlp
import json
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Define DOWNLOAD_DIR as it's imported by main.py
# Assuming it's a subdirectory named 'downloads' in the parent directory of 'utils'
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)
    os.chmod(DOWNLOAD_DIR, 0o777) # Ensure the directory is writable

def check_available_subtitles(url: str, cookies_path: str = None):
    """
    检查YouTube视频是否有可用的字幕
    返回字幕信息字典，包括自动生成和手动字幕
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'logger': logger,
    }
    if cookies_path:
        ydl_opts['cookiefile'] = cookies_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"检查字幕可用性: {url}")
            info_dict = ydl.extract_info(url, download=False)
        
            # 获取字幕信息
            subtitles = info_dict.get('subtitles', {})
            automatic_captions = info_dict.get('automatic_captions', {})
        
            # 检查是否有英文字幕（手动或自动）
            has_manual_en = 'en' in subtitles
            has_auto_en = 'en' in automatic_captions
            
            subtitle_info = {
                'has_manual_subtitles': bool(subtitles),
                'has_auto_subtitles': bool(automatic_captions),
                'has_english_manual': has_manual_en,
                'has_english_auto': has_auto_en,
                'manual_languages': list(subtitles.keys()) if subtitles else [],
                'auto_languages': list(automatic_captions.keys()) if automatic_captions else [],
                'needs_whisper_fallback': not (has_manual_en or has_auto_en)
            }
            
            logger.info(f"字幕检查结果: {subtitle_info}")
            return subtitle_info
            
    except Exception as e:
        logger.error(f"检查字幕时出错: {str(e)}")
        # 如果检查失败，假设需要使用 WhisperX
        return {
            'has_manual_subtitles': False,
            'has_auto_subtitles': False,
            'has_english_manual': False,
            'has_english_auto': False,
            'manual_languages': [],
            'auto_languages': [],
            'needs_whisper_fallback': True
        }

def download_youtube_video(url: str, cookies_path: str = None):
    """
    Downloads a YouTube video using yt-dlp.
    Returns a dictionary with video information.
    """
    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        'logger': logger,
        'writesubtitles': False,
        'writeautomaticsub': False,
        }
    if cookies_path:
        ydl_opts['cookiefile'] = cookies_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # First, get video info without downloading
            logger.info(f"Getting video info for {url}")
            info_dict = ydl.extract_info(url, download=False)
            
            # Try to find a suitable format that's 1080p or closest to it
            suitable_formats = []
            for f in info_dict.get('formats', []):
                if (f.get('ext') == 'mp4' and 
                    f.get('vcodec') != 'none' and 
                    f.get('acodec') != 'none'):
                    suitable_formats.append(f)
            
            if not suitable_formats:
                logger.warning("No suitable formats found, falling back to best format")
                ydl_opts['format'] = 'best'
            else:
                # Sort by resolution (height) and pick the closest to 1080p
                suitable_formats.sort(key=lambda x: abs(x.get('height', 0) - 1080))
                best_format = suitable_formats[0]
                format_id = best_format['format_id']
                logger.info(f"Selected format: {format_id} ({best_format.get('height')}p, {best_format.get('ext')}, {best_format.get('vcodec')}, {best_format.get('acodec')})")
                ydl_opts['format'] = format_id

            # Now download with the selected format
            logger.info(f"Downloading video with format: {ydl_opts['format']}")
            info_dict = ydl.extract_info(url, download=True)
                
            # Determine the final downloaded file path
            downloaded_file_path = None
            if 'requested_downloads' in info_dict and info_dict['requested_downloads']:
                downloaded_file_path = info_dict['requested_downloads'][0]['filepath']
            elif 'filename' in info_dict:
                downloaded_file_path = info_dict['filename']
            elif 'filepath' in info_dict:
                downloaded_file_path = info_dict['filepath']
            else:
                video_id = info_dict.get('id', 'unknown_video')
                guessed_path_mp4 = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp4")
                if os.path.exists(guessed_path_mp4):
                    downloaded_file_path = guessed_path_mp4
                else:
                    logger.error(f"Could not determine downloaded file path for {url}. Info: {info_dict}")
                    raise yt_dlp.utils.DownloadError("Could not determine downloaded file path.")

            if not downloaded_file_path or not os.path.exists(downloaded_file_path):
                logger.error(f"Downloaded file path not found or file does not exist: {downloaded_file_path} for URL {url}")
                raise yt_dlp.utils.DownloadError(f"Downloaded file path not found or file does not exist: {downloaded_file_path}")

            # 保存视频信息到单独的文件
            video_id = info_dict.get('id')
            if video_id:
                info_file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.info.json")
                with open(info_file_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        "id": video_id,
                        "title": info_dict.get('title', 'Unknown Title'),
                        "duration": info_dict.get('duration', 0),
                        "uploader": info_dict.get('uploader'),
                        "upload_date": info_dict.get('upload_date'),
                        "thumbnail": info_dict.get('thumbnail'),
                        "description": info_dict.get('description'),
                        "webpage_url": info_dict.get('webpage_url'),
                    }, f, ensure_ascii=False, indent=2)

            return {
                "filepath": downloaded_file_path,
                "title": info_dict.get('title', 'Unknown Title'),
                "duration": info_dict.get('duration', 0),
                "filename": os.path.basename(downloaded_file_path),
                "id": info_dict.get('id'),
                "uploader": info_dict.get('uploader'),
                "upload_date": info_dict.get('upload_date'),
                "thumbnail": info_dict.get('thumbnail'),
                "description": info_dict.get('description'),
                "webpage_url": info_dict.get('webpage_url'),
            }
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"yt-dlp download error for URL {url}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error downloading video {url}: {str(e)}")
        raise

def list_downloaded_videos() -> List[Dict]:
    """
    列出已下载视频的元数据
    """
    try:
        videos = []
        for filename in os.listdir(DOWNLOAD_DIR):
            if filename.endswith(('.mp4', '.mkv', '.webm')):
                video_path = os.path.join(DOWNLOAD_DIR, filename)
                info_path = os.path.join(DOWNLOAD_DIR, f"{os.path.splitext(filename)[0]}.info.json")
                
                # 尝试读取 .info.json 文件
                try:
                    with open(info_path, 'r', encoding='utf-8') as f:
                        info = json.load(f)
                        video_info = {
                            'id': info.get('id', ''),
                            'title': info.get('title', ''),
                            'duration': info.get('duration', 0),
                            'upload_date': info.get('upload_date', ''),
                            'thumbnail': info.get('thumbnail', ''),
                            'filename': filename,
                            'path': video_path,
                            'size': os.path.getsize(video_path)
                        }
                except (FileNotFoundError, json.JSONDecodeError):
                    # 如果 .info.json 文件不存在或损坏，使用基本信息
                    video_info = {
                        'id': os.path.splitext(filename)[0],
                        'title': filename,
                        'duration': 0,
                        'upload_date': '',
                        'thumbnail': '',
                        'filename': filename,
                        'path': video_path,
                        'size': os.path.getsize(video_path)
                    }
                
                videos.append(video_info)
        
        # 按下载时间排序
        videos.sort(key=lambda x: os.path.getctime(x['path']), reverse=True)
        return videos
        
    except Exception as e:
        logger.error(f"列出已下载视频失败: {str(e)}")
        return []

# Example usage (optional, for testing)
if __name__ == '__main__':
    # Configure logging for standalone testing
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ" # Example video
    print(f"Attempting to download: {test_url}")
    try:
        video_info = download_youtube_video(test_url)
        print("\nDownload successful!")
        print(json.dumps(video_info, indent=4))
    except Exception as e:
        print(f"\nDownload failed: {e}")

    print("\nListing downloaded videos:")
    downloaded_list = list_downloaded_videos()
    if downloaded_list:
        for video in downloaded_list:
            print(json.dumps(video, indent=2))
    else:
        print("No videos found in download directory.")