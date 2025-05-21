# -*- coding: utf-8 -*-
"""
调用 FFmpeg 将中文字幕烧录进视频
"""
import os, subprocess, tempfile, shutil, logging

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

def burn_subtitle(video_path: str, srt_path: str) -> str:
    """
    将字幕烧录到视频中
    """
    # ---------- 保证字幕文件在 FFmpeg 运行期间仍然可用 ----------
    # 某些调用场景下，srt_path 可能位于临时目录（e.g. tempfile.TemporaryDirectory）
    # 当退出上层 with 语句时目录会被删除，导致 FFmpeg 报 "Unable to open … .srt"
    if not os.path.exists(srt_path):
        raise FileNotFoundError(f"字幕文件不存在: {srt_path}")

    # 将字幕文件复制到与视频同目录的稳定位置，名称形如 originalname.merged.srt
    stable_srt_path = os.path.join(
        os.path.dirname(video_path),
        os.path.basename(video_path).rsplit('.', 1)[0] + '.merged.srt'
    )

    # 只有当目标位置与源文件不同，且副本尚不存在时才复制
    if os.path.abspath(srt_path) != os.path.abspath(stable_srt_path):
        shutil.copyfile(srt_path, stable_srt_path)
        srt_path = stable_srt_path
    # -----------------------------------------------------------

    # 创建临时输出文件
    output_path = video_path.rsplit('.', 1)[0] + '.sub.mp4'
    
    # 查找可用字体并构建 filter 字符串
    font_path = find_available_font()
    if font_path:
        force_style = f"FontName={os.path.basename(font_path)},FontSize=18"
        filter_str = f"subtitles={srt_path}:fontsdir={os.path.dirname(font_path)}:force_style='{force_style}'"
    else:
        filter_str = f"subtitles={srt_path}:force_style=FontSize=18"
    
    # 检查是否支持 GPU
    use_gpu = check_gpu_support()
    
    # 构建基础命令
    command = [
        'ffmpeg', '-hide_banner',
        '-i', video_path,
        '-vf', filter_str,
    ]
    
    # 根据是否支持 GPU 添加编码器参数
    if use_gpu:
        command.extend([
            '-c:v', 'h264_nvenc',  # 使用 NVIDIA 硬件编码器
            '-preset', 'p4',  # NVENC 预设
            '-tune', 'hq',  # 高质量调优
            '-rc', 'vbr',  # 可变比特率
            '-cq', '23',  # 质量参数
            '-b:v', '0',  # 自动比特率
            '-spatial-aq', '1',  # 空间自适应量化
            '-temporal-aq', '1',  # 时间自适应量化
        ])
    else:
        command.extend([
            '-c:v', 'libx264',  # 使用 CPU 编码器
            '-preset', 'medium',
            '-crf', '23',
            '-profile:v', 'high',
            '-level', '4.0',
        ])
    
    # 添加通用参数
    command.extend([
        '-pix_fmt', 'yuv420p',  # 像素格式，确保兼容性
        '-movflags', '+faststart',  # 优化网络播放
        '-c:a', 'copy',  # 复制音频流
        '-y',  # 覆盖已存在的文件
        '-threads', '0',  # 自动选择线程数
        output_path
    ])
    
    # 打印完整命令以便调试
    logger.info("Running: " + " ".join(command))
    
    try:
        # 执行命令
        result = subprocess.run(command, capture_output=True, text=True)
        if result.stderr:
            logger.warning(f"FFmpeg 警告: {result.stderr}")
        result.check_returncode()  # 这会抛出异常并包含完整的 stderr
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg 错误: {e.stderr}")
        raise Exception(f"字幕烧录失败: {str(e)}")