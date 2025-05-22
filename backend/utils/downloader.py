import os
import yt_dlp
import json
import logging

logger = logging.getLogger(__name__)

# Define DOWNLOAD_DIR as it's imported by main.py
# Assuming it's a subdirectory named 'downloads' in the parent directory of 'utils'
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)
    os.chmod(DOWNLOAD_DIR, 0o777) # Ensure the directory is writable

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
            
            # Try to find a suitable format that's less likely to use SABR
            # Prefer formats that are:
            # 1. MP4 container
            # 2. Have both video and audio
            # 3. Are 1080p or lower (to avoid SABR while maintaining good quality)
            suitable_formats = []
            for f in info_dict.get('formats', []):
                if (f.get('ext') == 'mp4' and 
                    f.get('vcodec') != 'none' and 
                    f.get('acodec') != 'none' and
                    f.get('height', 0) <= 1080):  # Changed to 1080p
                    suitable_formats.append(f)
            
            if not suitable_formats:
                logger.warning("No suitable formats found, falling back to best format")
                ydl_opts['format'] = 'best'
            else:
                # Sort by resolution (height) and pick the highest quality that's not too high
                suitable_formats.sort(key=lambda x: x.get('height', 0), reverse=True)
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

def list_downloaded_videos():
    """
    Lists metadata of downloaded videos.
    It tries to find a .info.json file for each video.
    """
    videos = []
    if not os.path.exists(DOWNLOAD_DIR):
        return videos

    for item in os.listdir(DOWNLOAD_DIR):
        if item.endswith(('.mp4', '.mkv', '.webm')) and not item.startswith('.'): # Common video extensions
            video_path = os.path.join(DOWNLOAD_DIR, item)
            info_path = os.path.splitext(video_path)[0] + '.info.json' # yt-dlp often saves a .info.json

            if os.path.exists(info_path):
                try:
                    with open(info_path, 'r', encoding='utf-8') as f:
                        info = json.load(f)
                    videos.append({
                        "filename": item,
                        "filepath": video_path,
                        "title": info.get('title', 'Unknown Title'),
                        "duration": info.get('duration', 0),
                        "id": info.get('id'),
                        "thumbnail": info.get('thumbnail'),
                        "webpage_url": info.get('webpage_url'),
                        "download_time": os.path.getmtime(video_path) # Add download time for sorting
                    })
                except Exception as e:
                    logger.warning(f"Could not parse info file {info_path}: {e}")
                    # Fallback if info.json is missing or corrupt
                    videos.append({
                        "filename": item,
                        "filepath": video_path,
                        "title": "Unknown Title (info missing)",
                        "duration": 0, # Could try to get with ffprobe if needed
                        "id": None,
                        "thumbnail": None,
                        "webpage_url": None,
                        "download_time": os.path.getmtime(video_path)
                    })
            else:
                 # Fallback if no .info.json, less metadata
                videos.append({
                    "filename": item,
                    "filepath": video_path,
                    "title": "Unknown Title (no info.json)",
                    "duration": 0, # Could try to get with ffprobe if needed
                    "id": None,
                    "thumbnail": None,
                    "webpage_url": None,
                    "download_time": os.path.getmtime(video_path)
                })
    
    # Sort by download time, newest first
    videos.sort(key=lambda x: x['download_time'], reverse=True)
    return videos

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