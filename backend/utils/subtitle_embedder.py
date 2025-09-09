# -*- coding: utf-8 -*-
"""
调用 FFmpeg 将中文字幕烧录进视频
"""
import os, subprocess, tempfile, shutil, logging, shlex, re, math
import srt
from pathlib import Path

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 可能的字体路径列表（参考 KlicStudio 常用字体）
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

def sanitize_path_for_ffmpeg(file_path):
    """处理文件路径，确保FFmpeg能正确处理特殊字符"""
    # 使用Path对象确保路径是绝对路径并转换为字符串
    path_str = str(Path(file_path).resolve())
    # 将文件路径复制到临时文件夹，使用随机文件名避免特殊字符
    temp_dir = tempfile.mkdtemp()
    
    # 确定文件扩展名
    ext = os.path.splitext(path_str)[1]
    temp_file = os.path.join(temp_dir, f"temp_file{ext}")
    
    # 复制文件
    shutil.copy2(path_str, temp_file)
    logger.info(f"将文件 '{path_str}' 复制到临时位置 '{temp_file}'")
    
    return temp_file, temp_dir

def get_video_dimensions(video_path):
    """获取视频尺寸"""
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height',
        '-of', 'json',
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"获取视频尺寸失败: {result.stderr}")
    
    import json
    data = json.loads(result.stdout)
    width = int(data['streams'][0]['width'])
    height = int(data['streams'][0]['height'])
    return width, height

def calculate_subtitle_style(width, height, is_bilingual=False, content_scale: float = 1.0):
    """根据视频尺寸智能计算字幕样式，支持双语显示优化"""
    
    # 全局字号：双语略小，单语接近原生
    size_multiplier = 0.78 if is_bilingual else 0.95
    margin_multiplier = 1.5 if is_bilingual else 1.0
    
    # 修正字体大小比例
    if height >= 2160:  # 4K+
        # 更小的基础比例与更低的最小值，避免在4K上过大
        font_size = max(14, min(26, int(height * 0.010 * size_multiplier)))
        margin_v = int(height * 0.018 * margin_multiplier)
        outline = 3
    elif height >= 1440:  # 2K
        font_size = max(18, min(24, int(height * 0.014 * size_multiplier)))
        margin_v = int(height * 0.022 * margin_multiplier)
        outline = 2.5
    elif height >= 1080:  # 1080p
        font_size = max(14, min(20, int(height * 0.016 * size_multiplier)))
        margin_v = int(height * 0.025 * margin_multiplier)
        outline = 2
    elif height >= 720:   # 720p
        font_size = max(12, min(18, int(height * 0.018 * size_multiplier)))
        margin_v = int(height * 0.03 * margin_multiplier)
        outline = 2
    else:  # SD (≤480p)
        font_size = max(10, min(14, int(height * 0.020 * size_multiplier)))
        margin_v = int(height * 0.04 * margin_multiplier)
        outline = 1.5
    
    # 宽高比自适应边距
    aspect_ratio = width / height
    if aspect_ratio > 2.0:  # 超宽屏
        margin_l = margin_r = int(width * 0.07)
    elif aspect_ratio > 1.6:  # 标准宽屏
        margin_l = margin_r = int(width * 0.045)
    elif aspect_ratio < 1.0:  # 竖屏
        margin_l = margin_r = int(width * 0.03)
        font_size = int(font_size * 1.1)  # 竖屏字体稍大
    else:  # 4:3 等
        margin_l = margin_r = 40

    # 环境变量微调（默认 1.0，可通过 SUBTITLE_FONT_SCALE 覆盖）
    scale = float(os.getenv("SUBTITLE_FONT_SCALE", "1.0"))
    font_size = int(font_size * scale)
    
    # 基于内容的自适应缩放（0.6 ~ 1.2 之间）
    content_scale = max(0.5, min(1.2, float(content_scale)))
    font_size = int(font_size * content_scale)
    
    # 构建 ASS 样式，双语字幕使用不同的字体配置
    if is_bilingual:
        # 双语字幕样式：支持英文和中文字体；强制不自动换行（WrapStyle=2）
        style = (
            f"FontName=Noto Sans SC,Arial Unicode MS,DejaVu Sans,"
            f"FontSize={font_size},"
            f"PrimaryColour=&HFFFFFF&,"
            f"OutlineColour=&H000000&,"
            f"Outline={outline},"
            f"BorderStyle=1,"
            f"Alignment=2,"  # 底部居中
            f"MarginV={margin_v},"
            f"MarginL={margin_l},"
            f"MarginR={margin_r},"
            f"Spacing=3,"  # 行间距稍大，提高可读性
            f"WrapStyle=2"  # 不自动换行，仅保留显式换行
        )
    else:
        # 单语字幕样式
        style = (
            f"FontName=Noto Sans SC,"
            f"FontSize={font_size},"
            f"PrimaryColour=&HFFFFFF&,"
            f"OutlineColour=&H000000&,"
            f"Outline={outline},"
            f"BorderStyle=1,"
            f"Alignment=2,"  # 底部居中
            f"MarginV={margin_v},"
            f"MarginL={margin_l},"
            f"MarginR={margin_r},"
            f"Spacing=2,"  # 行间距
            f"WrapStyle=2"  # 不自动换行
        )
    
    subtitle_type = "双语" if is_bilingual else "单语"
    logger.info(f"{subtitle_type}字幕样式: {width}x{height} -> 字体{font_size}pt, 边距V{margin_v}px, content_scale={content_scale}")
    return style

def detect_bilingual_subtitle(srt_path: str) -> bool:
    """
    检测字幕文件是否为双语字幕
    通过分析字幕内容中是否同时包含中英文来判断
    """
    try:
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查是否包含中文字符
        has_chinese = any('\u4e00' <= ch <= '\u9fff' for ch in content)
        
        # 检查是否包含英文字母
        has_english = any(ch.isalpha() and ord(ch) < 128 for ch in content)
        
        # 检查是否包含换行符（双语字幕通常每个条目有多行）
        lines = content.split('\n')
        multi_line_entries = 0
        
        for i, line in enumerate(lines):
            # 跳过序号和时间戳行
            if line.strip().isdigit() or '-->' in line:
                continue
            # 检查字幕内容行
            if line.strip() and i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].strip().isdigit() and '-->' not in lines[i + 1]:
                multi_line_entries += 1
        
        # 如果同时包含中英文且有多行条目，很可能是双语字幕
        is_bilingual = has_chinese and has_english and multi_line_entries > 0
        
        logger.info(f"字幕检测结果: 中文={has_chinese}, 英文={has_english}, 多行条目={multi_line_entries}, 双语={is_bilingual}")
        return is_bilingual
        
    except Exception as e:
        logger.warning(f"检测双语字幕失败: {str(e)}, 默认为单语字幕")
        return False

def _measure_line_equivalent_chars(line: str) -> float:
    """估算一行的等效字符宽度：中文≈1.0，ASCII≈0.6。"""
    eq = 0.0
    for ch in line:
        if ch == '\n':
            continue
        if '\u4e00' <= ch <= '\u9fff':
            eq += 1.0
        elif ch.isascii():
            eq += 0.6
        else:
            eq += 0.8
    return eq


def compute_content_scale(srt_path: str, width: int, height: int, is_bilingual: bool) -> float:
    """根据字幕内容长度粗略自适应字体缩放。
    以1080p为基准：
      - 双语字幕期望单行最大等效宽度≈34（英文衡量）
      - 单语字幕期望单行最大等效宽度≈42
    不足时不放大，超出时按比例缩小，最小到0.6。
    """
    try:
        with open(srt_path, 'r', encoding='utf-8') as fp:
            subs = list(srt.parse(fp.read()))
    except Exception as e:
        logger.warning(f"读取字幕失败，忽略内容自适应: {e}")
        return 1.0

    max_eq = 0.0
    for sub in subs:
        for ln in str(sub.content).split('\n'):
            ln = ln.strip()
            if not ln:
                continue
            max_eq = max(max_eq, _measure_line_equivalent_chars(ln))

    # 基准阈值按照分辨率线性缩放
    # 更保守的最大行宽阈值：促使长句更频繁地缩小
    base_threshold_1080 = 26.0 if is_bilingual else 34.0
    threshold = base_threshold_1080 * (height / 1080.0)

    if max_eq <= 0.0:
        return 1.0

    if max_eq <= threshold:
        return 1.0  # 不放大，保持稳定

    scale = threshold / max_eq
    return max(0.6, min(1.0, scale))


def burn_subtitle(video_path: str, srt_path: str, output_file_path: str, is_bilingual: bool = None) -> str:
    """
    将字幕硬烧录进视频。

    1. 若系统检测到 NVENC 且未设置 SUBTITLE_FORCE_CPU=1，则优先使用 GPU (h264_nvenc)。
    2. GPU 编码失败时自动回退 CPU (libx264)。
    3. 最终结果复制到 output_file_path 并返回该路径。
    4. 自动检测或手动指定是否为双语字幕，优化显示样式。
    
    Args:
        video_path: 输入视频路径
        srt_path: 字幕文件路径
        output_file_path: 输出视频路径
        is_bilingual: 是否为双语字幕，None表示自动检测
    """
    temp_video_dir: str | None = None
    temp_srt_dir: str | None = None
    temp_output_dir: str | None = None

    # ------------------------------------------------------------
    # 1. 预处理与参数计算
    # ------------------------------------------------------------
    try:
        # 验证输入文件
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        if not os.path.exists(srt_path):
            raise FileNotFoundError(f"字幕文件不存在: {srt_path}")
        
        logger.info(f"开始烧录字幕，视频: {video_path}, 字幕: {srt_path}")

        # --------------------------------------------------------
        # 2. 获取视频尺寸 & 计算字幕样式
        # --------------------------------------------------------
        width, height = get_video_dimensions(video_path)
        logger.info(f"视频尺寸: {width}x{height}")
        
        # 检测是否为双语字幕
        if is_bilingual is None:
            is_bilingual = detect_bilingual_subtitle(srt_path)
        
        # 计算内容自适应缩放
        content_scale = compute_content_scale(srt_path, width, height, is_bilingual)
        # 计算字幕样式
        subtitle_style = calculate_subtitle_style(width, height, is_bilingual, content_scale)
        logger.info(f"字幕样式: {subtitle_style}")

        # --------------------------------------------------------
        # 3. 在临时目录中准备输入 & 输出
        # --------------------------------------------------------
        temp_video_dir = tempfile.mkdtemp()
        temp_srt_dir = tempfile.mkdtemp()
        temp_output_dir = tempfile.mkdtemp()
        
        # 复制视频和字幕到临时目录
        temp_video_filename = "input_video" + os.path.splitext(video_path)[1]
        temp_video_path = os.path.join(temp_video_dir, temp_video_filename)
        temp_srt_internal_path = os.path.join(temp_srt_dir, "subtitles.srt")

        shutil.copy2(video_path, temp_video_path)
        shutil.copy2(srt_path, temp_srt_internal_path)
        
        # 设置输出路径
        output_path = os.path.join(temp_output_dir, "output.mp4")
        
        # 构建字幕滤镜
        subtitle_filter_value = f"subtitles={temp_srt_internal_path}:force_style='{subtitle_style}'"
        logger.info(f"FFmpeg subtitles filter: {subtitle_filter_value}")

        # 4. 选择编码方案（GPU 优先）
        def _run_ffmpeg(cmd: list[str]):
            logger.info("执行 FFmpeg: %s", ' '.join(cmd))
            return subprocess.run(cmd, check=True, capture_output=True, text=True)

        def _build_gpu_cmd() -> list[str]:
            """GPU 编码命令（参考 KlicStudio 优化）"""
            return [
                'ffmpeg', '-hide_banner', '-loglevel', 'warning',
                '-i', temp_video_path,
                '-vf', subtitle_filter_value,
                '-c:v', 'h264_nvenc',
                '-preset', 'p4', '-tune', 'hq', '-rc', 'vbr', '-cq', '20',
                '-b:v', '0', '-maxrate', '15M', '-bufsize', '30M',
                '-spatial-aq', '1', '-temporal-aq', '1',
                '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
                '-movflags', '+faststart', '-y', output_path
            ]

        def _build_cpu_cmd() -> list[str]:
            """CPU 编码命令（参考 KlicStudio 优化）"""
            return [
                'ffmpeg', '-hide_banner', '-loglevel', 'warning',
                '-i', temp_video_path,
                '-vf', subtitle_filter_value,
                '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
                '-profile:v', 'high', '-level', '4.0',
                '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
                '-movflags', '+faststart', '-pix_fmt', 'yuv420p',
                '-y', output_path
            ]

        use_gpu = (os.getenv("SUBTITLE_FORCE_CPU") != "1") and check_gpu_support()

        try:
            if use_gpu:
                logger.info("检测到可用 GPU，尝试使用 NVENC 烧录字幕…")
                _run_ffmpeg(_build_gpu_cmd())
            else:
                raise RuntimeError("GPU 不可用或已被禁用，直接使用 CPU")
        except Exception as gpu_err:  # 捕获 GPU 不可用或失败
            logger.warning("GPU 路径失败 (%s)，回退 libx264…", gpu_err)
            _run_ffmpeg(_build_cpu_cmd())
        
        # --------------------------------------------------------
        # 5. 结果校验 & 输出（参考 KlicStudio 增强校验）
        # --------------------------------------------------------
        if not os.path.exists(output_path):
            raise FileNotFoundError("FFmpeg 输出文件不存在")
            
        file_size = os.path.getsize(output_path)
        input_size = os.path.getsize(video_path)
        logger.info(f"输出文件: {file_size / (1024*1024):.1f}MB (原始: {input_size / (1024*1024):.1f}MB)")
        
        # 更严格的文件校验
        if file_size < 50000:  # 小于50KB肯定有问题
            raise Exception(f"输出文件异常小 ({file_size} bytes)")
        elif file_size < input_size * 0.1:  # 小于原文件10%可能有问题
            logger.warning(f"输出文件可能过小，请检查质量")
        
        # 简单的完整性检查：用 ffprobe 验证输出文件
        try:
            probe_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', output_path]
            result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                raise Exception("输出文件格式校验失败")
        except subprocess.TimeoutExpired:
            logger.warning("文件校验超时，跳过")
        except Exception as e:
            logger.warning(f"文件校验失败: {e}")
        
        # 确保目标目录存在并复制
        Path(output_file_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output_path, output_file_path)
        logger.info(f"字幕烧录完成: {output_file_path}")
        
        return output_file_path
    
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg 错误: {e.stderr}")
        raise Exception(f"字幕烧录失败: {str(e)}") 
    
    finally:
        # 清理临时文件和目录
        try:
            if temp_video_dir and os.path.exists(temp_video_dir):
                shutil.rmtree(temp_video_dir)
                logger.info(f"已清理临时视频目录: {temp_video_dir}")
            if temp_srt_dir and os.path.exists(temp_srt_dir):
                shutil.rmtree(temp_srt_dir)
                logger.info(f"已清理临时字幕目录: {temp_srt_dir}")
            if temp_output_dir and os.path.exists(temp_output_dir):
                shutil.rmtree(temp_output_dir)
                logger.info(f"已清理临时输出目录: {temp_output_dir}")
        except Exception as e:
            logger.warning(f"清理临时文件时出错: {str(e)}") 