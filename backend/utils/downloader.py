import os
import yt_dlp
import json
import logging
from typing import List, Dict, Optional
from .subtitle_extractor import SubtitleExtractor, check_youtube_subtitles

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
    使用youtube-transcript-api优先检查，回退到yt-dlp
    返回字幕信息字典，包括自动生成和手动字幕
    """
    try:
        # 优先使用 youtube-transcript-api 检查字幕
        logger.info(f"使用 youtube-transcript-api 检查字幕可用性: {url}")
        transcript_info = check_youtube_subtitles(url)
        
        if transcript_info['manual'] or transcript_info['generated']:
            # 转换为兼容格式
            manual_languages = [t['language_code'] for t in transcript_info['manual']]
            auto_languages = [t['language_code'] for t in transcript_info['generated']]
            
            has_manual_en = any(lang in ['en', 'en-US', 'en-GB'] for lang in manual_languages)
            has_auto_en = any(lang in ['en', 'en-US', 'en-GB'] for lang in auto_languages)
            
            subtitle_info = {
                'has_manual_subtitles': bool(transcript_info['manual']),
                'has_auto_subtitles': bool(transcript_info['generated']),
                'has_english_manual': has_manual_en,
                'has_english_auto': has_auto_en,
                'manual_languages': manual_languages,
                'auto_languages': auto_languages,
                'needs_whisper_fallback': not (has_manual_en or has_auto_en),
                'transcript_api_available': True,
                'translatable_languages': transcript_info.get('translatable_languages', [])
            }
            
            logger.info(f"youtube-transcript-api 字幕检查结果: {subtitle_info}")
            return subtitle_info
        
    except Exception as e:
        logger.warning(f"youtube-transcript-api 检查失败，回退到 yt-dlp: {str(e)}")
    
    # 回退到原有的 yt-dlp 方法
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'logger': logger,
    }
    if cookies_path:
        ydl_opts['cookiefile'] = cookies_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"使用 yt-dlp 检查字幕可用性: {url}")
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
                'needs_whisper_fallback': not (has_manual_en or has_auto_en),
                'transcript_api_available': False
            }
            
            logger.info(f"yt-dlp 字幕检查结果: {subtitle_info}")
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
            'needs_whisper_fallback': True,
            'transcript_api_available': False
        }

def download_youtube_video(url: str, cookies_path: str = None):
    """
    Downloads a YouTube video using yt-dlp.
    Returns a dictionary with video information.
    """
    # 如果未显式传入，尝试从环境变量读取 cookies 路径
    if cookies_path is None:
        cookies_path = os.getenv("YT_COOKIES_FILE")

    # 如果环境变量为空或文件不存在，尝试使用项目默认路径
    if not cookies_path or not os.path.exists(cookies_path):
        default_cookie_path = os.path.join(BASE_DIR, "youtube.cookies")
        if os.path.exists(default_cookie_path):
            logger.info(f"Using fallback cookies file: {default_cookie_path}")
            cookies_path = default_cookie_path

    logger.info(f"YT_COOKIES_FILE effective path: {cookies_path}")

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
    if cookies_path and os.path.exists(cookies_path):
        ydl_opts['cookiefile'] = cookies_path
    elif cookies_path:
        logger.warning(f"Cookies file not found: {cookies_path}, proceeding without cookies")

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

def download_youtube_subtitles(url: str, language_codes: List[str] = None, 
                             prefer_manual: bool = True) -> Optional[str]:
    """
    使用youtube-transcript-api下载YouTube字幕
    
    Args:
        url: YouTube视频URL
        language_codes: 优先语言代码列表，默认['en', 'en-US', 'en-GB']
        prefer_manual: 是否优先选择手动字幕
        
    Returns:
        str: SRT文件路径，失败返回None
    """
    try:
        extractor = SubtitleExtractor()
        video_id = extractor.extract_video_id(url)
        
        if not video_id:
            logger.error(f"无法从URL提取视频ID: {url}")
            return None
        
        logger.info(f"开始下载字幕: {video_id}")
        srt_path = extractor.download_transcript(video_id, language_codes, prefer_manual)
        
        if srt_path:
            logger.info(f"字幕下载成功: {srt_path}")
        else:
            logger.warning(f"字幕下载失败: {video_id}")
            
        return srt_path
        
    except Exception as e:
        logger.error(f"下载字幕时出错: {str(e)}")
        return None

def download_youtube_translated_subtitles(url: str, target_language: str = 'zh-Hans') -> Optional[str]:
    """
    下载YouTube的翻译字幕
    
    Args:
        url: YouTube视频URL
        target_language: 目标语言代码，默认'zh-Hans'（简体中文）
        
    Returns:
        str: SRT文件路径，失败返回None
    """
    try:
        extractor = SubtitleExtractor()
        video_id = extractor.extract_video_id(url)
        
        if not video_id:
            logger.error(f"无法从URL提取视频ID: {url}")
            return None
        
        logger.info(f"开始下载翻译字幕: {video_id} -> {target_language}")
        srt_path = extractor.download_translated_transcript(video_id, target_language)
        
        if srt_path:
            logger.info(f"翻译字幕下载成功: {srt_path}")
        else:
            logger.warning(f"翻译字幕下载失败: {video_id}")
            
        return srt_path
        
    except Exception as e:
        logger.error(f"下载翻译字幕时出错: {str(e)}")
        return None

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