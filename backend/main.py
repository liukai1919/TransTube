from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os, json, shutil
from utils.downloader import download_video
from utils.transcriber import transcribe_to_srt
from utils.translator import translate_srt_to_zh
from utils.subtitle_embedder import burn_subtitle
from utils.processor import VideoProcessor

app = FastAPI()

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建必要的目录
os.makedirs("downloads", exist_ok=True)
os.makedirs("static/videos", exist_ok=True)
os.makedirs("static/subtitles", exist_ok=True)

# 设置目录权限
for dir_path in ["downloads", "static/videos", "static/subtitles"]:
    os.chmod(dir_path, 0o777)

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 全局任务状态
tasks = {}

# 获取服务器地址
def get_server_url():
    return os.getenv("SERVER_URL", "http://localhost:8000")

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
        video_path, srt_path, vid, title, duration = download_video(url, "downloads")
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
        output_video, merged_srt = processor.process_video(
            video_path,
            transcribe_to_srt,
            translate_srt_to_zh,
            burn_subtitle
        )
        
        # 4. 移动文件到静态目录 (90-100%)
        update_task_progress(task_id, "正在保存结果...", 90)
        
        video_filename = f"{vid}_sub.mp4"
        srt_filename = f"{vid}_zh.srt"
        
        final_video_path = os.path.join("static", "videos", video_filename)
        final_srt_path = os.path.join("static", "subtitles", srt_filename)
        
        # 使用 shutil.copy2 保留文件权限
        shutil.copy2(output_video, final_video_path)
        update_task_progress(task_id, "正在保存视频...", 95)
        shutil.copy2(merged_srt, final_srt_path)
        update_task_progress(task_id, "正在保存字幕...", 98)
        
        # 设置文件权限
        os.chmod(final_video_path, 0o644)
        os.chmod(final_srt_path, 0o644)
        
        # 清理临时文件
        try:
            os.remove(output_video)
            os.remove(merged_srt)
            if os.path.exists(video_path):
                os.remove(video_path)
            if srt_path and os.path.exists(srt_path):
                os.remove(srt_path)
        except Exception as e:
            print(f"清理临时文件时出错: {str(e)}")
        
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