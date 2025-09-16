import os
import yt_dlp
import json
import logging
import re
import contextlib
from typing import List, Dict, Optional
from .subtitle_extractor import SubtitleExtractor, check_youtube_subtitles

logger = logging.getLogger(__name__)

# Define DOWNLOAD_DIR as it's imported by main.py
# Assuming it's a subdirectory named 'downloads' in the parent directory of 'utils'
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")

# 如果项目根目录下提供了 youtube.cookies，则作为默认登录 Cookie
DEFAULT_COOKIES_FILE = os.path.join(BASE_DIR, "youtube.cookies")

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)
    os.chmod(DOWNLOAD_DIR, 0o777) # Ensure the directory is writable

# ---------------- Subtitle Helpers -----------------

def check_available_subtitles(url: str, cookies_path: str = None):
    """
    检查YouTube视频是否有可用的字幕（手动/自动），优先使用 youtube-transcript-api，回退到 yt-dlp。
    """
    try:
        logger.info(f"使用 youtube-transcript-api 检查字幕可用性: {url}")
        transcript_info = check_youtube_subtitles(url)

        if transcript_info['manual'] or transcript_info['generated']:
            manual_languages = [t['language_code'] for t in transcript_info['manual']]
            auto_languages = [t['language_code'] for t in transcript_info['generated']]

            has_manual_en = any(lang in ['en', 'en-US', 'en-GB'] for lang in manual_languages)
            has_auto_en   = any(lang in ['en', 'en-US', 'en-GB'] for lang in auto_languages)

            subtitle_info = {
                'has_manual_subtitles': bool(transcript_info['manual']),
                'has_auto_subtitles':  bool(transcript_info['generated']),
                'has_english_manual':  has_manual_en,
                'has_english_auto':    has_auto_en,
                'manual_languages':    manual_languages,
                'auto_languages':      auto_languages,
                'needs_whisper_fallback': not (has_manual_en or has_auto_en),
                'transcript_api_available': True,
                'translatable_languages': transcript_info.get('translatable_languages', [])
            }
            logger.info(f"youtube-transcript-api 字幕检查结果: {subtitle_info}")
            return subtitle_info
    except Exception as e:
        logger.warning(f"youtube-transcript-api 检查失败，回退到 yt-dlp: {e}")

    # 回退到 yt-dlp
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

            subtitles          = info_dict.get('subtitles', {})
            automatic_captions = info_dict.get('automatic_captions', {})

            has_manual_en = 'en' in subtitles
            has_auto_en   = 'en' in automatic_captions

            subtitle_info = {
                'has_manual_subtitles': bool(subtitles),
                'has_auto_subtitles':  bool(automatic_captions),
                'has_english_manual':  has_manual_en,
                'has_english_auto':    has_auto_en,
                'manual_languages':    list(subtitles.keys()) if subtitles else [],
                'auto_languages':      list(automatic_captions.keys()) if automatic_captions else [],
                'needs_whisper_fallback': not (has_manual_en or has_auto_en),
                'transcript_api_available': False
            }
            logger.info(f"yt-dlp 字幕检查结果: {subtitle_info}")
            return subtitle_info
    except Exception as e:
        logger.error(f"检查字幕时出错: {e}")
        return {
            'has_manual_subtitles': False,
            'has_auto_subtitles':   False,
            'has_english_manual':   False,
            'has_english_auto':     False,
            'manual_languages':     [],
            'auto_languages':       [],
            'needs_whisper_fallback': True,
            'transcript_api_available': False
        }

# ---------------- Video Download -----------------

def download_youtube_video(url: str, cookies_path: str = None, force_best: bool = False):
    """下载单个 YouTube 视频。

    参数:
    - force_best: True 时强制首选最高画质分离流 (bestvideo+bestaudio/best)，
                  False 时先尝试 progressive 流（若有）。"""
    # ---------------- 统一处理 cookies_path ----------------
    if cookies_path is None:
        env_cookie = os.getenv("YT_COOKIES_FILE")
        if env_cookie and os.path.exists(env_cookie):
            cookies_path = env_cookie
        elif os.path.exists(DEFAULT_COOKIES_FILE):
            cookies_path = DEFAULT_COOKIES_FILE

    # 强化默认清晰度偏好：可通过环境变量控制
    env_force_best = os.getenv("DOWNLOAD_FORCE_BEST", "1") == "1"
    env_prefer_h264 = os.getenv("DOWNLOAD_PREFER_H264", "1") == "1"

    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        'logger': logger,
        'writesubtitles': False,
        'writeautomaticsub': False,
        # 合并分离流时优先输出 mkv（兼容 VP9/AV1，不被迫回落低清 progressive）
        'merge_output_format': 'mkv',
        # 格式排序偏好：先分辨率、再帧率；如偏好 h264 则将 avc 排前
        'format_sort': [
            'res:1080', 'res', 'fps',
            'codec:h264' if env_prefer_h264 else 'codec'
        ],
    }
    if cookies_path:
        ydl_opts['cookiefile'] = cookies_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Getting video info for {url}")
            info_dict = ydl.extract_info(url, download=False)

            # Progressive mp4 list
            candidate_formats = [
                f for f in info_dict.get('formats', [])
                if f.get('ext') == 'mp4' and f.get('vcodec') != 'none' and f.get('acodec') != 'none'
            ]

            if candidate_formats:
                candidate_formats.sort(key=lambda x: abs(x.get('height', 0) - 1080))
                progressive_choice = candidate_formats[0]['format_id']
            else:
                progressive_choice = None

            # ------------------ 构建尝试顺序 ------------------
            format_attempts = []

            # 首先确定 progressive 的分辨率（如有）
            progressive_height = 0
            if candidate_formats:
                progressive_height = candidate_formats[0].get('height', 0) or 0

            HIGH_RES_THRESHOLD = 720  # 若 progressive 低于 720p，则认为清晰度不足

            if env_force_best or force_best or progressive_choice is None or progressive_height < HIGH_RES_THRESHOLD:
                # 1) 直接尝试最高画质分离流（不限编码/封装），由 yt-dlp + ffmpeg 合并
                format_attempts.append('bestvideo+bestaudio/best')
                # 可选：尽量选 avc/h264（若可用）
                if env_prefer_h264:
                    format_attempts.append('bestvideo[vcodec^=avc]+bestaudio/best[ext=mp4]/best')
                # 备选 progressive（如果存在）
                if progressive_choice:
                    format_attempts.append(progressive_choice)
            else:
                # progressive 已达 720p 及以上，先用它
                format_attempts.append(progressive_choice)
                # 然后再尝试 DASH 流
                format_attempts.append('bestvideo+bestaudio/best')

            # 其他兜底格式
            format_attempts.extend([
                'bestvideo+bestaudio/best',
                'best'
            ])

            last_exc = None
            for fmt in format_attempts:
                temp_opts = {**ydl_opts, 'format': fmt}
                logger.info(f"Attempting download with format: {fmt}")
                try:
                    with yt_dlp.YoutubeDL(temp_opts) as _ydl:
                        info_dict = _ydl.extract_info(url, download=True)
                    break  # success
                except yt_dlp.utils.DownloadError as e:
                    last_exc = e
                    logger.warning(f"Format {fmt} failed: {e}")
                    # 清理空文件
                    vid_match = re.search(r"[?&]v=([\w-]{11})", url)
                    if vid_match:
                        tmp_path = os.path.join(DOWNLOAD_DIR, f"{vid_match.group(1)}.mp4")
                        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) == 0:
                            with contextlib.suppress(Exception):
                                os.remove(tmp_path)
                    continue

            if not info_dict:
                raise last_exc or yt_dlp.utils.DownloadError("All format attempts failed")

            # 解析最终文件路径
            downloaded_path = None
            if info_dict.get('requested_downloads'):
                downloaded_path = info_dict['requested_downloads'][0]['filepath']
            elif info_dict.get('filename'):
                downloaded_path = info_dict['filename']
            elif info_dict.get('filepath'):
                downloaded_path = info_dict['filepath']
            else:
                vid = info_dict.get('id', 'unknown')
                # 可能选择了分离流并合并为 mkv
                guess_mp4 = os.path.join(DOWNLOAD_DIR, f"{vid}.mp4")
                guess_mkv = os.path.join(DOWNLOAD_DIR, f"{vid}.mkv")
                downloaded_path = guess_mp4 if os.path.exists(guess_mp4) else (guess_mkv if os.path.exists(guess_mkv) else None)

            if not downloaded_path or not os.path.exists(downloaded_path):
                raise yt_dlp.utils.DownloadError("无法确定已下载文件路径或文件不存在")

            # 保存 .info.json 元数据
            vid = info_dict.get('id')
            if vid:
                info_path = os.path.join(DOWNLOAD_DIR, f"{vid}.info.json")
                with open(info_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        'id': vid,
                        'title': info_dict.get('title'),
                        'duration': info_dict.get('duration', 0),
                        'uploader': info_dict.get('uploader'),
                        'upload_date': info_dict.get('upload_date'),
                        'thumbnail': info_dict.get('thumbnail'),
                        'description': info_dict.get('description'),
                        'webpage_url': info_dict.get('webpage_url'),
                    }, f, ensure_ascii=False, indent=2)

            return {
                'filepath': downloaded_path,
                'title': info_dict.get('title', 'Unknown Title'),
                'duration': info_dict.get('duration', 0),
                'filename': os.path.basename(downloaded_path),
                'id': vid,
                'uploader': info_dict.get('uploader'),
                'upload_date': info_dict.get('upload_date'),
                'thumbnail': info_dict.get('thumbnail'),
                'description': info_dict.get('description'),
                'webpage_url': info_dict.get('webpage_url'),
            }
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"yt-dlp download error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise

# ---------------- Listing -----------------

def list_downloaded_videos() -> List[Dict]:
    """列出下载目录下所有已下载文件及其 metadata"""
    videos = []
    try:
        for fname in os.listdir(DOWNLOAD_DIR):
            if fname.endswith(('.mp4', '.mkv', '.webm')):
                fpath = os.path.join(DOWNLOAD_DIR, fname)
                info_path = os.path.join(DOWNLOAD_DIR, f"{os.path.splitext(fname)[0]}.info.json")
                meta = {}
                if os.path.exists(info_path):
                    try:
                        with open(info_path, 'r', encoding='utf-8') as f:
                            meta = json.load(f)
                    except Exception:
                        pass
                videos.append({
                    'id': meta.get('id', os.path.splitext(fname)[0]),
                    'title': meta.get('title', fname),
                    'duration': meta.get('duration', 0),
                    'upload_date': meta.get('upload_date', ''),
                    'thumbnail': meta.get('thumbnail', ''),
                    'filename': fname,
                    'path': fpath,
                    'size': os.path.getsize(fpath)
                })
        videos.sort(key=lambda x: os.path.getctime(x['path']), reverse=True)
    except Exception as e:
        logger.error(f"列出已下载视频失败: {e}")
    return videos

# ---------------- Subtitle Download API -----------------

def download_youtube_subtitles(url: str, language_codes: List[str] | None = None, prefer_manual: bool = True) -> Optional[str]:
    language_codes = language_codes or ['en', 'en-US', 'en-GB']
    try:
        extractor = SubtitleExtractor()
        vid = extractor.extract_video_id(url)
        if not vid:
            logger.error("无法提取视频ID")
            return None
        logger.info(f"开始下载字幕 {vid}")
        return extractor.download_transcript(vid, language_codes, prefer_manual)
    except Exception as e:
        logger.error(f"下载字幕时出错: {e}")
        return None

def download_youtube_translated_subtitles(url: str, target_language: str = 'zh-Hans') -> Optional[str]:
    try:
        extractor = SubtitleExtractor()
        vid = extractor.extract_video_id(url)
        if not vid:
            logger.error("无法提取视频ID")
            return None
        logger.info(f"开始下载翻译字幕 {vid} → {target_language}")
        return extractor.download_translated_transcript(vid, target_language)
    except Exception as e:
        logger.error(f"下载翻译字幕时出错: {e}")
        return None

# ---------------- Playlist Info -----------------

def get_playlist_info(url: str, cookies_path: str = None) -> Optional[Dict]:
    """简单检测 URL 是否为播放列表并返回信息，用于兼容旧接口。"""
    if cookies_path is None:
        env_cookie = os.getenv("YT_COOKIES_FILE")
        if env_cookie and os.path.exists(env_cookie):
            cookies_path = env_cookie
        elif os.path.exists(DEFAULT_COOKIES_FILE):
            cookies_path = DEFAULT_COOKIES_FILE

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': 'in_playlist',
        'logger': logger,
        'playlistend': 1,
    }
    if cookies_path:
        ydl_opts['cookiefile'] = cookies_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if info.get('_type') == 'playlist' or 'entries' in info:
            # 播放列表
            return {
                'type': 'playlist',
                'playlist_id': info.get('id') or info.get('playlist_id', ''),
                'playlist_title': info.get('title', 'Unknown Playlist'),
                'uploader': info.get('uploader') or info.get('channel', ''),
                'video_count': len(info.get('entries', [])),
            }
        else:
            # 单个视频
            return {
                'type': 'single',
                'video_id': info.get('id', ''),
                'title': info.get('title', 'Unknown Video'),
                'url': info.get('webpage_url', url),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader') or info.get('channel', ''),
            }
    except Exception as e:
        logger.error(f"get_playlist_info error: {e}")
        return None

# ---------------- CLI Testing -----------------

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    info = download_youtube_video(test_url)
    print("Downloaded:", json.dumps(info, indent=2, ensure_ascii=False))
