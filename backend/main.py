from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Query, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, Response
from pydantic import BaseModel
from typing import Optional
import os, json, shutil, socket, re, logging, uuid, asyncio
from utils.downloader import download_youtube_video, list_downloaded_videos, check_available_subtitles, download_youtube_subtitles, download_youtube_translated_subtitles, DOWNLOAD_DIR
from utils.transcriber import transcribe_to_srt
from utils.translator import translate_srt_to_zh, translate_video_title
from utils.subtitle_embedder import burn_subtitle
from utils.processor import VideoProcessor
import ffmpeg
from pathlib import Path
from starlette.types import Scope, Receive, Send
from datetime import datetime
import threading
import concurrent.futures
import uvicorn

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
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

app = FastAPI(title="视频翻译 API", version="1.0.0")

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
TASKS_DIR = BASE_DIR / "tasks"  # 任务状态目录

for path in [DOWNLOAD_DIR, STATIC_VIDEOS_DIR, STATIC_SUBS_DIR, TASKS_DIR]:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o777)

# 全局任务状态
tasks = {}

# 添加线程锁和线程池
tasks_lock = threading.RLock()  # 可重入锁，防止死锁
executor = concurrent.futures.ThreadPoolExecutor(max_workers=3, thread_name_prefix="VideoProcessor")

# 添加线程安全的任务状态更新函数
def thread_safe_update_task_progress(task_id: str, message: str, progress: int, stage: str = None):
    """线程安全的任务进度更新"""
    with tasks_lock:
        if task_id in tasks:
            tasks[task_id].update({
                "message": message,
                "progress": progress,
                "updated_at": datetime.now().isoformat()
            })
            if stage:
                tasks[task_id]["stage"] = stage
            
            # 异步保存任务状态，避免阻塞
            threading.Thread(target=save_task_state, args=(task_id, tasks[task_id]), daemon=True).start()
            
            logger.info(f"任务 {task_id}: {message} ({progress}%)")

def save_task_state(task_id: str, task_data: dict):
    """保存任务状态到文件 - 线程安全版本"""
    try:
        task_file = TASKS_DIR / f"{task_id}.json"
        
        # 创建任务数据的副本，避免并发修改
        with tasks_lock:
            safe_task_data = task_data.copy()
        
        with open(task_file, 'w', encoding='utf-8') as f:
            json.dump(safe_task_data, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"任务状态已保存: {task_id}")
    except Exception as e:
        logger.error(f"保存任务状态失败 {task_id}: {str(e)}")

def load_task_state(task_id: str) -> Optional[dict]:
    """从文件加载任务状态"""
    try:
        task_file = TASKS_DIR / f"{task_id}.json"
        if task_file.exists():
            with open(task_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"加载任务状态失败 {task_id}: {str(e)}")
    return None

def load_all_tasks():
    """启动时加载所有任务状态"""
    global tasks
    try:
        for task_file in TASKS_DIR.glob("*.json"):
            task_id = task_file.stem
            state = load_task_state(task_id)
            if state:
                tasks[task_id] = state
                logger.info(f"恢复任务状态: {task_id}")
    except Exception as e:
        logger.error(f"加载任务状态失败: {str(e)}")

def check_existing_results(video_id: str) -> dict:
    """检查是否已有处理结果"""
    try:
        video_filename = f"{video_id}_sub.mp4"
        srt_filename = f"{video_id}_zh.srt"
        
        video_path = STATIC_VIDEOS_DIR / video_filename
        srt_path = STATIC_SUBS_DIR / srt_filename
        
        if video_path.exists() and srt_path.exists():
            # 获取文件信息
            try:
                probe = ffmpeg.probe(video_path)
                duration = float(probe['format']['duration'])
                title = probe['format'].get('tags', {}).get('title', '已处理视频')
            except:
                duration = 0
                title = '已处理视频'
            
            server_url = get_server_url()
            return {
                "exists": True,
                "video_url": f"{server_url}/static/videos/{video_filename}" if duration <= 1800 else None,
                "srt_url": f"{server_url}/static/subtitles/{srt_filename}",
                "download_url": f"{server_url}/static/videos/{video_filename}",
                "duration": duration,
                "title": title,
                "processing_method": "已缓存结果"
            }
    except Exception as e:
        logger.error(f"检查已有结果失败: {str(e)}")
    
    return {"exists": False}

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
async def process_video(
    video_url: str = Form(...),
    target_lang: str = Form(default="zh")
):
    """处理视频 - 线程安全版本"""
    try:
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 线程安全地创建任务
        task = {
            "id": task_id,
            "video_url": video_url,
            "target_lang": target_lang,
            "status": "pending",
            "progress": 0,
            "message": "任务已创建，等待处理",
            "stage": "pending",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        with tasks_lock:
            tasks[task_id] = task
            save_task_state(task_id, task)
        
        logger.info(f"创建新任务: {task_id} - {video_url}")
        
        # 启动后台处理任务
        asyncio.create_task(process_video_task(task))
        
        return {
            "message": "任务已创建",
            "task_id": task_id,
            "status": "pending"
        }
        
    except Exception as e:
        logger.error(f"创建任务失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")

@app.get("/api/task/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状态 - 线程安全版本"""
    with tasks_lock:
        # 首先检查内存中的任务
        if task_id in tasks:
            task_data = tasks[task_id].copy()  # 创建副本避免并发修改
            return task_data
    
    # 如果内存中没有，尝试从文件加载
    task_data = load_task_state(task_id)
    if task_data:
        # 将加载的任务重新放入内存
        with tasks_lock:
            tasks[task_id] = task_data
        return task_data
    
    # 任务不存在
    raise HTTPException(status_code=404, detail="任务不存在")

@app.post("/api/task/{task_id}/resume")
async def resume_task(task_id: str, background_tasks: BackgroundTasks):
    """恢复失败的任务"""
    if task_id not in tasks:
        state = load_task_state(task_id)
        if not state:
            raise HTTPException(status_code=404, detail="Task not found")
        tasks[task_id] = state
    
    task_state = tasks[task_id]
    
    if task_state["status"] not in ["failed", "interrupted"]:
        raise HTTPException(status_code=400, detail="Task is not in a resumable state")
    
    # 重置任务状态
    task_state["status"] = "pending"
    task_state["message"] = "任务恢复中..."
    task_state["error"] = None
    save_task_state(task_id, task_state)
    
    # 重新启动任务
    background_tasks.add_task(
        process_video_task,
        task_state
    )
    
    return {"message": "Task resumed successfully"}

def update_task_progress(task_id: str, message: str, progress: int, stage: str = None):
    """更新任务进度 - 线程安全版本"""
    thread_safe_update_task_progress(task_id, message, progress, stage)

async def process_video_task(task: dict):
    """
    异步包装器 - 将任务提交到线程池
    """
    task_id = task["id"]
    try:
        # 将同步任务提交到线程池
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, process_video_task_sync, task)
    except Exception as e:
        logger.error(f"提交任务到线程池失败 {task_id}: {str(e)}")
        with tasks_lock:
            tasks[task_id].update({
                "status": "failed",
                "message": f"任务启动失败: {str(e)}",
                "error": str(e),
                "failed_at": datetime.now().isoformat()
            })
            save_task_state(task_id, tasks[task_id])

def process_video_task_sync(task: dict):
    """
    同步处理视频任务 - 在线程池中运行
    """
    task_id = task["id"]
    try:
        video_url = task["video_url"]
        target_lang = task["target_lang"]
        
        # 更新任务状态
        thread_safe_update_task_progress(task_id, "正在下载视频...", 10, stage="downloading")
        
        # 下载视频
        video_info = download_youtube_video(video_url)
        if not video_info or 'filepath' not in video_info:
            raise Exception("视频下载失败")
        
        video_path = video_info['filepath']
        
        # 检查字幕可用性
        thread_safe_update_task_progress(task_id, "正在检查字幕可用性...", 20, stage="checking_subtitles")
        
        subtitle_info = check_available_subtitles(video_url)
        en_srt = None
        processing_method = "完整处理"
        
        # 优先尝试使用 youtube-transcript-api 获取字幕
        if subtitle_info.get('transcript_api_available') and (
            subtitle_info.get('has_english_manual') or subtitle_info.get('has_english_auto')
        ):
            thread_safe_update_task_progress(task_id, "正在下载YouTube字幕...", 30, stage="downloading_subtitles")
            
            # 优先选择手动字幕
            prefer_manual = subtitle_info.get('has_english_manual', False)
            en_srt = download_youtube_subtitles(video_url, ['en', 'en-US', 'en-GB'], prefer_manual)
            
            if en_srt:
                processing_method = "YouTube字幕" + ("(手动)" if prefer_manual else "(自动)")
                logger.info(f"成功获取YouTube字幕: {processing_method}")
            else:
                logger.warning("YouTube字幕下载失败，回退到语音转录")
        
        # 如果没有获取到字幕，使用语音转录
        if not en_srt:
            thread_safe_update_task_progress(task_id, "正在转写音频...", 30, stage="processing")
            thread_safe_update_task_progress(task_id, "正在生成英文字幕...", 40, stage="transcribing")
            
            en_srt = transcribe_to_srt(video_path)
            if not en_srt:
                raise Exception("转写失败")
            processing_method = "语音转录"
        
        # 翻译成中文字幕
        thread_safe_update_task_progress(task_id, "正在翻译字幕...", 60, stage="translating")
        
        zh_srt_path = translate_srt_to_zh(en_srt)
        if not zh_srt_path:
            raise Exception("翻译失败")
        
        # 读取翻译后的字幕内容
        with open(zh_srt_path, 'r', encoding='utf-8') as f:
            zh_srt_content = f.read()
        
        # 生成输出文件名
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        output_video_path = STATIC_VIDEOS_DIR / f"{base_name}_sub.mp4"
        output_srt_path = STATIC_SUBS_DIR / f"{base_name}_zh.srt"
        
        # 烧录字幕到视频
        thread_safe_update_task_progress(task_id, "正在烧录字幕...", 80, stage="embedding")
        
        final_video_path = burn_subtitle(video_path, zh_srt_path, str(output_video_path))
        if not final_video_path:
            raise Exception("烧录字幕失败")

        # 保存中文字幕到最终位置
        with open(output_srt_path, 'w', encoding='utf-8') as f:
            f.write(zh_srt_content)
        
        # 清理临时字幕文件
        if os.path.exists(en_srt):
            os.unlink(en_srt)
        if os.path.exists(zh_srt_path) and str(Path(zh_srt_path).resolve()) != str(output_srt_path.resolve()):
            os.unlink(zh_srt_path)
        
        # 构建结果
        server_url = get_server_url() 
        duration = video_info.get('duration', 0)
        
        result = {
            "video_url": f"{server_url}/static/videos/{output_video_path.name}" if duration <= 1800 else None,
            "srt_url": f"{server_url}/static/subtitles/{output_srt_path.name}",
            "download_url": f"{server_url}/static/videos/{output_video_path.name}",
            "duration": duration,
            "title": video_info.get('title', '未命名视频'),
            "processing_method": processing_method
        }
        
        # 线程安全地更新任务状态为完成
        with tasks_lock:
            tasks[task_id].update({
                "status": "completed",
                "progress": 100,
                "message": "处理完成",
                "result": result,
                "output_path": str(final_video_path),
                "srt_path": str(output_srt_path),
                "video_info": video_info,
                "completed_at": datetime.now().isoformat()
            })
            save_task_state(task_id, tasks[task_id])
        
        logger.info(f"任务 {task_id} 处理完成")
        
    except Exception as e:
        logger.error(f"处理任务失败: {str(e)}", exc_info=True)
        
        # 构建用户友好的错误消息
        user_message = f"处理失败: {getattr(e, 'message', str(e))}"
        if "No space left on device" in str(e):
            user_message = "处理失败：设备空间不足，请清理磁盘后再试。"
        elif "ffmpeg" in str(e).lower():
            user_message = f"处理失败：视频处理错误 - {str(e)}"

        # 线程安全地更新任务状态为失败
        with tasks_lock:
            current_progress = tasks[task_id].get("progress", 0)
            tasks[task_id].update({
                "status": "failed",
                "progress": current_progress,
                "message": user_message,
                "error": str(e),
                "failed_at": datetime.now().isoformat()
            })
            save_task_state(task_id, tasks[task_id])
        
        logger.error(f"任务 {task_id} 处理失败: {str(e)}")

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
            if filename.endswith(("_sub.mp4", ".sub.mp4")):  # 支持两种格式
                # 提取视频ID
                vid = filename.replace("_sub.mp4", "").replace(".sub.mp4", "")
                
                # 构建文件路径
                video_path = video_dir / filename
                srt_path = subtitle_dir / f"{vid}_zh.srt"
                
                # 获取原始视频信息
                original_title = "未命名视频"
                try:
                    # 尝试从 info.json 文件读取原始标题
                    info_file = Path(DOWNLOAD_DIR) / f"{vid}.info.json"
                    if info_file.exists():
                        with open(info_file, 'r', encoding='utf-8') as f:
                            info_data = json.load(f)
                            original_title = info_data.get('title', '未命名视频')
                    else:
                        # 如果没有 info.json，尝试从视频文件元数据获取
                        try:
                            probe = ffmpeg.probe(video_path)
                            original_title = probe['format'].get('tags', {}).get('title', '未命名视频')
                        except:
                            pass
                        
                        # 如果还是没有标题，尝试从YouTube API获取
                        if original_title == "未命名视频":
                            original_title = get_video_title_from_id(vid)
                            
                            # 保存获取到的标题信息
                            if original_title != f"视频_{vid}":
                                info_data = {
                                    "id": vid,
                                    "title": original_title,
                                    "duration": 0,
                                    "uploader": "",
                                    "upload_date": "",
                                    "thumbnail": "",
                                    "description": "",
                                    "webpage_url": f"https://www.youtube.com/watch?v={vid}",
                                }
                                with open(info_file, 'w', encoding='utf-8') as f:
                                    json.dump(info_data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.warning(f"无法获取视频 {vid} 的原始标题: {str(e)}")
                
                # 翻译标题
                try:
                    # 检查是否已有翻译缓存
                    title_cache_file = video_dir / f"{vid}_title_zh.txt"
                    if title_cache_file.exists():
                        with open(title_cache_file, 'r', encoding='utf-8') as f:
                            chinese_title = f.read().strip()
                    else:
                        # 翻译标题并缓存
                        chinese_title = translate_video_title(original_title)
                        with open(title_cache_file, 'w', encoding='utf-8') as f:
                            f.write(chinese_title)
                except Exception as e:
                    logger.error(f"翻译标题失败: {str(e)}")
                    chinese_title = original_title
                
                # 获取视频时长
                try:
                    probe = ffmpeg.probe(video_path)
                    duration = float(probe['format']['duration'])
                except:
                    duration = 0
                
                # 构建视频信息（绝对地址）
                video_info = {
                    "video_url": f"{server_url}/static/videos/{filename}",
                    "srt_url": f"{server_url}/static/subtitles/{vid}_zh.srt",
                    "duration": duration,
                    "title": chinese_title,
                    "original_title": original_title
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

@app.post("/api/check-subtitles")
async def check_subtitles(video_url: str = Form(...)):
    """检查YouTube视频的字幕可用性"""
    try:
        subtitle_info = check_available_subtitles(video_url)
        return {
            "success": True,
            "subtitle_info": subtitle_info
        }
    except Exception as e:
        logger.error(f"检查字幕失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"检查字幕失败: {str(e)}")

@app.post("/api/download-subtitles")
async def download_subtitles_only(
    video_url: str = Form(...),
    language_codes: str = Form(default="en,en-US,en-GB"),
    prefer_manual: bool = Form(default=True),
    target_language: str = Form(default="zh-Hans")
):
    """仅下载字幕（不处理视频）"""
    try:
        # 解析语言代码
        lang_codes = [lang.strip() for lang in language_codes.split(',')]
        
        # 下载原文字幕
        en_srt_path = download_youtube_subtitles(video_url, lang_codes, prefer_manual)
        if not en_srt_path:
            raise Exception("无法获取原文字幕")
        
        # 如果需要翻译
        if target_language not in ["en", "en-US", "en-GB"]:
            # 先尝试直接获取翻译字幕
            zh_srt_path = download_youtube_translated_subtitles(video_url, target_language)
            processing_method = "YouTube翻译字幕"
            
            if not zh_srt_path:
                # 如果没有直接的翻译字幕，使用我们的翻译服务
                logger.info("YouTube翻译字幕不可用，使用自定义翻译服务")
                zh_srt_path = translate_srt_to_zh(en_srt_path)
                processing_method = "自定义翻译"
                if not zh_srt_path:
                    # 如果翻译也失败，直接使用英文
                    logger.warning("翻译失败，使用英文原文")
                    zh_srt_path = en_srt_path
                    processing_method = "英文原文(翻译失败)"
        else:
            zh_srt_path = en_srt_path
            processing_method = "英文原文"
        
        # 读取字幕内容
        with open(zh_srt_path, 'r', encoding='utf-8') as f:
            subtitle_content = f.read()
        
        # 清理临时文件
        if os.path.exists(en_srt_path) and en_srt_path != zh_srt_path:
            os.unlink(en_srt_path)
        if os.path.exists(zh_srt_path):
            os.unlink(zh_srt_path)
        
        return {
            "success": True,
            "subtitle_content": subtitle_content,
            "processing_method": processing_method,
            "message": f"字幕获取成功 ({processing_method})"
        }
        
    except Exception as e:
        logger.error(f"下载字幕失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"下载字幕失败: {str(e)}")

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

def get_video_title_from_id(video_id: str) -> str:
    """
    尝试从视频ID获取YouTube标题
    """
    try:
        import yt_dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            url = f"https://www.youtube.com/watch?v={video_id}"
            info_dict = ydl.extract_info(url, download=False)
            return info_dict.get('title', '未命名视频')
    except Exception as e:
        logger.warning(f"无法获取视频 {video_id} 的标题: {str(e)}")
        return f"视频_{video_id}"

@app.delete("/api/videos/all")
async def delete_all_videos_and_tasks():
    """
    删除所有下载的视频、生成的视频、字幕和相关的任务状态。
    """
    deleted_files_count = 0
    deleted_tasks_count = 0

    # 删除 static/videos 中的文件
    try:
        for filename in os.listdir(STATIC_VIDEOS_DIR):
            file_path = STATIC_VIDEOS_DIR / filename
            if file_path.is_file():
                os.unlink(file_path)
                deleted_files_count += 1
        logger.info(f"已删除 static/videos 中的 {deleted_files_count} 个文件")
    except Exception as e:
        logger.error(f"删除 static/videos 中的文件时出错: {str(e)}")
        # 不立即抛出异常，继续尝试删除其他目录

    # 删除 static/subtitles 中的文件
    sub_deleted_count = 0
    try:
        for filename in os.listdir(STATIC_SUBS_DIR):
            file_path = STATIC_SUBS_DIR / filename
            if file_path.is_file():
                os.unlink(file_path)
                sub_deleted_count += 1
        deleted_files_count += sub_deleted_count
        logger.info(f"已删除 static/subtitles 中的 {sub_deleted_count} 个文件")
    except Exception as e:
        logger.error(f"删除 static/subtitles 中的文件时出错: {str(e)}")

    # 删除 downloads 中的文件和目录
    download_deleted_count = 0
    try:
        for item_name in os.listdir(DOWNLOAD_DIR):
            item_path = DOWNLOAD_DIR / item_name
            if item_path.is_file():
                os.unlink(item_path)
                download_deleted_count += 1
            elif item_path.is_dir():
                shutil.rmtree(item_path)
                download_deleted_count += 1 # 算作一个项目
        deleted_files_count += download_deleted_count
        logger.info(f"已删除 downloads 中的 {download_deleted_count} 个文件/目录")
    except Exception as e:
        logger.error(f"删除 downloads 中的文件时出错: {str(e)}")
        
    # 删除 tasks 目录中的任务状态文件并清空内存中的 tasks
    global tasks
    try:
        for task_file in TASKS_DIR.glob("*.json"):
            os.unlink(task_file)
            deleted_tasks_count += 1
        tasks.clear() # 清空内存中的任务字典
        logger.info(f"已删除 tasks 中的 {deleted_tasks_count} 个任务状态文件并清空内存")
    except Exception as e:
        logger.error(f"删除任务状态文件时出错: {str(e)}")

    return {
        "message": "所有相关视频、字幕和任务数据已删除。",
        "deleted_files_count": deleted_files_count,
        "deleted_tasks_count": deleted_tasks_count
    }

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时的清理工作"""
    logger.info("正在关闭应用...")
    
    # 等待所有任务完成，最多等待30秒
    try:
        executor.shutdown(wait=True, timeout=30)
        logger.info("线程池已成功关闭")
    except Exception as e:
        logger.warning(f"关闭线程池时出错: {str(e)}")
    
    # 保存所有未保存的任务状态
    with tasks_lock:
        for task_id, task_data in tasks.items():
            try:
                save_task_state(task_id, task_data)
            except Exception as e:
                logger.warning(f"保存任务状态失败 {task_id}: {str(e)}")
    
    logger.info("应用已安全关闭")

# 在应用启动时加载所有未完成的任务
@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化工作"""
    logger.info("正在启动应用...")
    
    # 从文件系统恢复任务状态
    try:
        for task_file in TASKS_DIR.glob("*.json"):
            try:
                task_id = task_file.stem
                task_data = load_task_state(task_id)
                if task_data:
                    with tasks_lock:
                        tasks[task_id] = task_data
                    logger.info(f"恢复任务状态: {task_id}")
            except Exception as e:
                logger.warning(f"恢复任务状态失败 {task_file}: {str(e)}")
    except Exception as e:
        logger.error(f"启动时恢复任务状态失败: {str(e)}")
    
    logger.info(f"应用启动完成，恢复了 {len(tasks)} 个任务")

# ---------------------------------------------------------------------------
# 文件下载端点（用于前端 /api/download/* 路径）
# ---------------------------------------------------------------------------

@app.get("/api/download/{file_type}/{filename:path}")
@app.head("/api/download/{file_type}/{filename:path}")
async def api_download_file(file_type: str, filename: str, request: Request):
    """按文件类型(video/subtitle)下载或获取文件信息。支持 GET / HEAD。"""
    # 仅允许两类文件夹，防止目录遍历
    if file_type == "video":
        file_path = STATIC_VIDEOS_DIR / filename
        default_media_type = "video/mp4"
    elif file_type == "subtitle":
        file_path = STATIC_SUBS_DIR / filename
        default_media_type = "text/plain; charset=utf-8"
    else:
        raise HTTPException(status_code=400, detail="Invalid file type")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # HEAD 请求只返回头部信息（如长度、类型）
    if request.method == "HEAD":
        return Response(headers={
            "Content-Length": str(file_path.stat().st_size),
            "Content-Type": default_media_type,
            "Content-Disposition": f'attachment; filename="{filename}"'
        })

    # GET 请求返回整文件
    return FileResponse(path=str(file_path), media_type=default_media_type, filename=filename)

# 确保使用 8001 端口启动，和前端配置保持一致
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)