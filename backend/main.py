from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
import os, json, shutil, socket, re, logging
from utils.downloader import download_youtube_video, list_downloaded_videos, DOWNLOAD_DIR
from utils.transcriber import transcribe_to_srt
from utils.translator import translate_srt_to_zh
from utils.subtitle_embedder import burn_subtitle
from utils.processor import VideoProcessor
import ffmpeg
from pathlib import Path
from starlette.responses import Response
from starlette.types import Scope, Receive, Send

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CORSStaticFiles(StaticFiles):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"].extend([
                    (b"Access-Control-Allow-Origin", b"*"),
                    (b"Access-Control-Allow-Methods", b"GET, OPTIONS"),
                    (b"Access-Control-Allow-Headers", b"*"),
                    (b"Access-Control-Allow-Credentials", b"true"),
                ])
            await send(message)
        await super().__call__(scope, receive, wrapped_send)

app = FastAPI()

# 找到 backend 目录
BASE_DIR = Path(__file__).resolve().parent

# 把 backend/static 挂到 /static，使用自定义的 CORSStaticFiles
app.mount(
    "/static",
    CORSStaticFiles(directory=BASE_DIR / "static"),
    name="static"
)

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建必要的目录（使用绝对路径，避免工作目录变化导致错误）
DOWNLOAD_DIR = BASE_DIR / "downloads"
STATIC_VIDEOS_DIR = BASE_DIR / "static" / "videos"
STATIC_SUBS_DIR = BASE_DIR / "static" / "subtitles"

for path in [DOWNLOAD_DIR, STATIC_VIDEOS_DIR, STATIC_SUBS_DIR]:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o777)

# 全局任务状态
tasks = {}

# 获取服务器地址
def get_server_url(request: Request | None = None) -> str:
    """
    Return the base URL to use when constructing absolute links.

    Priority:
    1. SERVER_URL environment variable (e.g. "https://videotrans.joeboy.org")
    2. request.base_url from the incoming FastAPI Request (includes scheme/host/port)
    3. Fallback to "http://127.0.0.1:8000"
    """
    env_url = os.getenv("SERVER_URL")
    if env_url:
        return env_url.rstrip("/")

    if request is not None:
        return str(request.base_url).rstrip("/")

    return "http://127.0.0.1:8000"

class VideoURL(BaseModel):
    url: str

class TaskStatus(BaseModel):
    task_id: str

@app.post("/api/process")
async def process_video(request: Request, background_tasks: BackgroundTasks):
    try:
        # 解析请求体
        data = await request.json()
        url = data.get("url")
        
        if not url:
            raise HTTPException(status_code=400, detail="URL is required")

        # Validate YouTube URL format
        youtube_regex = r"^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})$"
        if not re.match(youtube_regex, url):
            raise HTTPException(
                status_code=400, 
                detail="Invalid YouTube URL format. Please provide a valid YouTube video URL (e.g., https://www.youtube.com/watch?v=VIDEO_ID or https://youtu.be/VIDEO_ID)."
            )
        
        # 生成任务ID
        import uuid
        task_id = str(uuid.uuid4())
        
        # 初始化任务状态
        tasks[task_id] = {
            "status": "pending",
            "message": "任务初始化中...",
            "progress": 0,
            "result": None,
            "error": None
        }
        
        # 添加后台任务
        background_tasks.add_task(
            process_video_task,
            task_id,
            url
        )
        
        return {"task_id": task_id}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/task/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状态"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]

def update_task_progress(task_id: str, message: str, progress: float):
    """更新任务进度"""
    if task_id in tasks:
        tasks[task_id]["message"] = message
        tasks[task_id]["progress"] = min(100, max(0, progress))  # 确保进度在0-100之间
        print(f"任务 {task_id}: {message} - {progress:.1f}%")

async def process_video_task(task_id: str, url: str):
    """后台处理视频任务"""
    try:
        # 更新任务状态
        tasks[task_id]["status"] = "processing"
        
        # 1. 下载视频 (0-20%)
        update_task_progress(task_id, "正在下载视频...", 0)
        video_info = download_youtube_video(url)
        video_path = video_info['filepath']
        title = video_info['title']
        duration = video_info['duration']
        vid = os.path.splitext(video_info['filename'])[0]
        safe_title = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fa5-]', '_', title)
        srt_path = None  # 初始化为 None，因为下载时还没有字幕
        
        # 验证视频文件
        # Check if the video path is the placeholder, indicating a download failure
        if "placeholder_video.mp4" in video_path:
            error_message = "Video download failed: The downloader returned a placeholder path, indicating an issue with the download process."
            logger.error(f"Task {task_id}: {error_message}")
            raise FileNotFoundError(error_message)

        if not os.path.exists(video_path):
            error_message = f"下载的视频文件不存在: {video_path}"
            logger.error(f"Task {task_id}: {error_message}")
            raise FileNotFoundError(error_message)
        
        video_size = os.path.getsize(video_path)
        logger.info(f"Task {task_id}: 下载的视频大小: {video_size / (1024*1024):.2f} MB")
        if video_size < 100000:  # 小于100KB可能有问题
            warning_message = f"视频文件太小 ({video_size} bytes)，可能下载不完整: {video_path}"
            logger.warning(f"Task {task_id}: {warning_message}")
            # Optionally, raise an error if the file size is too small
            # raise ValueError(warning_message) 
        
        update_task_progress(task_id, "视频下载完成", 20)
        
        # 2. 创建视频处理器
        processor = VideoProcessor(
            chunk_duration=300,  # 5分钟一个切片
            max_workers=4,  # 4个并行工作线程
            progress_callback=lambda msg, prog: update_task_progress(
                task_id, 
                msg, 
                20 + (prog * 0.7)  # 20-90% 用于处理
            )
        )
        
        # 3. 处理视频
        update_task_progress(task_id, "开始处理视频...", 20)
        output_paths = processor.process_video(
            video_path,
            transcribe_to_srt,
            translate_srt_to_zh
        )
        
        # 解析返回的结果 (现在返回两个路径)
        if isinstance(output_paths, tuple) and len(output_paths) == 2:
            output_video, optimized_srt = output_paths
        else:
            # 兼容旧版本
            output_video = output_paths
            optimized_srt = None
        
        logger.info(f"视频处理完成：视频={output_video}，字幕={optimized_srt}")
        
        # 4. 移动文件到静态目录 (90-100%)
        update_task_progress(task_id, "正在保存结果...", 90)
        
        video_filename = f"{vid}_sub.mp4"
        srt_filename = f"{vid}_zh.srt"
        
        final_video_path = STATIC_VIDEOS_DIR / video_filename
        final_srt_path = STATIC_SUBS_DIR / srt_filename
        
        # 验证输出文件
        if not os.path.exists(output_video):
            raise FileNotFoundError(f"处理后的视频文件不存在: {output_video}")
        
        output_video_size = os.path.getsize(output_video)
        logger.info(f"处理后的视频文件大小: {output_video_size / (1024*1024):.2f} MB")
        
        if output_video_size < 100000:  # 小于100KB可能有问题
            logger.warning(f"处理后的视频文件太小 ({output_video_size} 字节)，可能有问题")
        
        # 使用 shutil.copy2 保留文件权限
        shutil.copy2(output_video, final_video_path)
        update_task_progress(task_id, "正在保存视频...", 95)
        
        if optimized_srt and os.path.exists(optimized_srt):
            shutil.copy2(optimized_srt, final_srt_path)
        else:
            # 如果没有字幕文件，创建一个空的
            with open(final_srt_path, 'w', encoding='utf-8') as f:
                f.write("")
            logger.warning(f"未找到字幕文件，创建了空字幕文件: {final_srt_path}")
            
        update_task_progress(task_id, "正在保存字幕...", 98)
        
        # 设置文件权限
        final_video_path.chmod(0o644)
        final_srt_path.chmod(0o644)
        
        # 清理临时文件
        try:
            # 使用 os.path.exists 检查文件是否存在，防止因文件不存在而报错
            if os.path.exists(output_video):
                os.remove(output_video)
            if optimized_srt and os.path.exists(optimized_srt):
                os.remove(optimized_srt)
            # 不删除原始视频，保留以备调试
            # if os.path.exists(video_path):
            #     os.remove(video_path)
            if srt_path and os.path.exists(srt_path):
                os.remove(srt_path)
                
            # 清理处理器的临时目录
            if hasattr(processor, 'temp_dir') and os.path.exists(processor.temp_dir):
                try:
                    shutil.rmtree(processor.temp_dir)
                except Exception as e:
                    print(f"清理临时目录失败: {str(e)}")
        except Exception as e:
            print(f"清理临时文件时出错: {str(e)}")
            # 继续执行，不影响主流程
        
        # 更新任务结果
        server_url = get_server_url()
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["message"] = "处理完成"
        
        # 根据视频时长决定是否提供在线播放
        if duration > 1800:  # 30分钟以上
            tasks[task_id]["result"] = {
                "video_url": None,  # 不提供在线播放
                "srt_url": f"{server_url}/static/subtitles/{srt_filename}",
                "download_url": f"{server_url}/static/videos/{video_filename}",
                "duration": duration,
                "title": title
            }
        else:
            tasks[task_id]["result"] = {
                "video_url": f"{server_url}/static/videos/{video_filename}",
                "srt_url": f"{server_url}/static/subtitles/{srt_filename}",
                "duration": duration,
                "title": title
            }
        
    except Exception as e:
        # 更新任务错误
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["message"] = f"处理失败: {str(e)}"
        tasks[task_id]["error"] = str(e)
        print(f"任务 {task_id} 失败: {str(e)}")

@app.get("/api/videos")
async def get_videos(request: Request):
    """获取已处理的视频列表"""
    try:
        videos = []
        video_dir = STATIC_VIDEOS_DIR
        subtitle_dir = STATIC_SUBS_DIR
        server_url = get_server_url(request)
        
        # 确保目录存在
        video_dir.mkdir(parents=True, exist_ok=True)
        subtitle_dir.mkdir(parents=True, exist_ok=True)
        
        # 遍历视频文件
        for filename in os.listdir(video_dir):
            if filename.endswith("_sub.mp4"):
                # 提取视频ID
                vid = filename.replace("_sub.mp4", "")
                
                # 构建文件路径
                video_path = video_dir / filename
                srt_path = subtitle_dir / f"{vid}_zh.srt"
                
                # 获取视频信息
                try:
                    probe = ffmpeg.probe(video_path)
                    duration = float(probe['format']['duration'])
                    title = probe['format'].get('tags', {}).get('title', '未命名视频')
                except:
                    duration = 0
                    title = '未命名视频'
                
                # 构建视频信息（绝对地址）
                video_info = {
                    "video_url": f"{server_url}/static/videos/{filename}",
                    "srt_url": f"{server_url}/static/subtitles/{vid}_zh.srt",
                    "duration": duration,
                    "title": title
                }
                
                # 对于长视频，添加下载链接
                if duration > 1800:  # 30分钟以上
                    video_info["video_url"] = None
                    video_info["download_url"] = f"{server_url}/static/videos/{filename}"
                else:
                    video_info["download_url"] = f"{server_url}/static/videos/{filename}"
                
                videos.append(video_info)
        
        # 按处理时间倒序排序
        videos.sort(key=lambda x: (video_dir / x["download_url"].split("/")[-1]).stat().st_mtime, reverse=True)
        
        return videos
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/download")
def api_download(url: str, cookies: str = None):
    """
    下载 YouTube 视频
    """
    try:
        cookies_path = cookies if cookies else None
        info = download_youtube_video(url, cookies_path)
        return {"success": True, "info": info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/videos")
def api_list_videos():
    """
    获取已下载视频列表
    """
    return list_downloaded_videos()

@app.get("/api/video/{filename}")
def api_get_video(filename: str):
    """
    直接下载/在线播放视频
    """
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type="video/mp4", filename=filename)