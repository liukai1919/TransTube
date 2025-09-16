# -*- coding: utf-8 -*-
"""
调用 FFmpeg 将中文字幕烧录进视频
"""
import os, subprocess, tempfile, shutil, logging, shlex, re, math
import srt
from datetime import timedelta
from pathlib import Path

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _env_font_name() -> str | None:
    name = os.getenv("SUBTITLE_FONT_NAME")
    return name.strip() if name else None

# 可能的字体路径列表（系统常见中文字体）
FONT_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
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

def find_fonts_dir() -> str | None:
    """尝试定位包含 CJK 字体的目录，以便 ffmpeg subtitles 指定 fontsdir。
    避免因系统缺失字体映射导致中文方框/乱码。"""
    # 优先使用环境变量覆盖
    env_dir = os.getenv("SUBTITLE_FONTS_DIR")
    if env_dir and os.path.isdir(env_dir):
        return env_dir
    candidates = [
        "/usr/share/fonts/opentype/noto",
        "/usr/share/fonts/truetype/noto",
        "/usr/share/fonts/noto-cjk",
        "/usr/share/fonts/truetype/wqy",
        "/usr/share/fonts",
    ]
    for d in candidates:
        if os.path.isdir(d):
            # 仅在目录内存在常见 CJK 字体时返回
            for name in ("NotoSansCJK", "NotoSansSC", "wqy", "WenQuanYi"):
                if any(name.lower() in fn.lower() for fn in os.listdir(d)):
                    return d
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
    """通用字幕样式方案：不同分辨率自适应，默认描边，也支持半透明底框。"""

    # 以 1080p≈44 为基准线性缩放，双语略小
    # 更保守的基础字号，避免占屏：1080p ≈ 28（可被 SUBTITLE_FONT_SCALE 进一步调节）
    base_size_1080 = 28
    size_mult = 0.92 if is_bilingual else 1.0
    font_size = int(round((height / 1080.0) * base_size_1080 * size_mult))

    # 合理区间钳制
    if height <= 480:
        font_min, font_max = 18, 24
    elif height <= 720:
        font_min, font_max = 26, 34
    elif height <= 1080:
        font_min, font_max = 22, 32
    elif height <= 1440:
        font_min, font_max = 28, 42
    elif height <= 2160:
        font_min, font_max = 40, 56
    else:
        font_min, font_max = 80, 110
    font_size = max(font_min, min(font_size, font_max))

    # 轮廓与阴影
    outline = max(1, min(4, int(round(height / 540))))  # 1080p≈2，2160p≈4
    shadow = 1

    # 边距（按分辨率比例），双语增加底部边距
    margin_v = int(round(height * (0.06 if is_bilingual else 0.05)))
    aspect_ratio = width / max(1, height)
    if aspect_ratio > 2.0:
        margin_l = margin_r = int(width * 0.06)
    elif aspect_ratio > 1.6:
        margin_l = margin_r = int(width * 0.05)
    else:
        margin_l = margin_r = int(width * 0.04)

    # 行距（可通过环境变量覆盖）
    try:
        spacing_bi = int(os.getenv("SUBTITLE_SPACING_BI", "2"))
    except Exception:
        spacing_bi = 2
    try:
        spacing_mono = int(os.getenv("SUBTITLE_SPACING", "1"))
    except Exception:
        spacing_mono = 1
    spacing = spacing_bi if is_bilingual else spacing_mono

    # 文本长度自适应（0.6~1.2）
    content_scale = max(0.6, min(1.2, float(content_scale)))
    font_size = int(font_size * content_scale)

    # 用户整体缩放
    user_scale = float(os.getenv("SUBTITLE_FONT_SCALE", "1.0"))
    font_size = int(font_size * user_scale)

    # 边框风格：1=描边（默认），3=半透明底框
    border_style = os.getenv("SUBTITLE_BORDER_STYLE", "1").strip()
    border_style = "3" if border_style == "3" else "1"

    # 字体族（优先中文，含英文字体回退）
    env_font = _env_font_name()
    font_chain = (
        (env_font + ',') if env_font else ''
    ) + "Noto Sans CJK SC,Noto Sans SC,Source Han Sans SC,Microsoft YaHei,Arial Unicode MS,DejaVu Sans"

    # 组装样式
    common = (
        f"FontSize={font_size},"
        f"PrimaryColour=&HFFFFFF&,"
        f"OutlineColour=&H000000&,"
        f"Outline={0 if border_style=='3' else outline},"
        f"Shadow={shadow if border_style=='1' else 0},"
        f"BorderStyle={border_style},"
        f"Alignment=2,"
        f"MarginV={margin_v},"
        f"MarginL={margin_l},"
        f"MarginR={margin_r},"
        f"Spacing={spacing},"
        f"WrapStyle={os.getenv('SUBTITLE_WRAP_STYLE','2').strip()}"
    )
    if border_style == '3':
        # 半透明黑底（约 50% 透明）
        common += ",BackColour=&H80000000&"

    style = f"FontName={font_chain}," + common

    subtitle_type = "双语" if is_bilingual else "单语"
    logger.info(f"{subtitle_type}字幕样式: {width}x{height} -> 字体{font_size}px, Outline={outline}, BorderStyle={border_style}, content_scale={content_scale}")
    return style

def _wrap_line_by_eq(text: str, max_eq: float) -> str:
    """按等效字符宽度对单行进行软换行（插入 \n）。
    - 带空格的文本优先按词切分；纯 CJK/无空格按字符切分。
    - max_eq 按 _measure_line_equivalent_chars 的度量。
    """
    text = text.strip()
    if not text:
        return text

    def eq_len(s: str) -> float:
        return _measure_line_equivalent_chars(s)

    tokens = text.split()
    lines = []
    cur = ''

    if len(tokens) > 1:
        for tok in tokens:
            pending = (cur + (' ' if cur else '') + tok)
            if eq_len(pending) <= max_eq or not cur:
                cur = pending
            else:
                lines.append(cur)
                cur = tok
        if cur:
            lines.append(cur)
    else:
        # 无空格：逐字符断行（兼容中文）
        cur = ''
        for ch in text:
            pending = cur + ch
            if eq_len(pending) <= max_eq or not cur:
                cur = pending
            else:
                lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)

    return "\n".join(lines)

def _wrap_srt_for_width(input_path: str, output_path: str, width: int, height: int, is_bilingual: bool, content_scale: float) -> None:
    """读取 SRT，针对当前分辨率进行软换行，写回 output_path。
    阈值基于 1080p 的目标等效宽度并随分辨率及缩放调整。
    可通过环境变量覆盖：
      - SUBTITLE_MAX_EQ_1080_BI（默认 26.0）
      - SUBTITLE_MAX_EQ_1080（默认 34.0）
    """
    try:
        with open(input_path, 'r', encoding='utf-8') as fp:
            subs = list(srt.parse(fp.read()))
    except Exception as e:
        logger.warning(f"读取字幕失败，跳过断句优化: {e}")
        shutil.copy2(input_path, output_path)
        return

    base_1080 = float(os.getenv('SUBTITLE_MAX_EQ_1080_BI' if is_bilingual else 'SUBTITLE_MAX_EQ_1080', '26.0' if is_bilingual else '34.0'))
    # 按高度缩放，并叠加 content_scale & 用户缩放
    max_eq = base_1080 * (height / 1080.0)
    try:
        user_scale = float(os.getenv('SUBTITLE_FONT_SCALE', '1.0'))
    except Exception:
        user_scale = 1.0
    max_eq = max_eq * content_scale * user_scale

    def _split_bilingual_pages(en_line: str, zh_line: str) -> list[tuple[str,str]]:
        en_wrapped = _wrap_line_by_eq(en_line, max_eq).split('\n') if en_line else []
        zh_wrapped = _wrap_line_by_eq(zh_line, max_eq).split('\n') if zh_line else []
        pages = []
        n = max(len(en_wrapped), len(zh_wrapped)) or 1
        for i in range(n):
            en_i = en_wrapped[i] if i < len(en_wrapped) else ""
            zh_i = zh_wrapped[i] if i < len(zh_wrapped) else ""
            pages.append((en_i, zh_i))
        return pages

    def _eq_units(text: str) -> float:
        return _measure_line_equivalent_chars(text)

    new_subs = []
    for sub in subs:
        content = str(sub.content)
        # 解析成英文、中文两行（若是单语则一行为空）
        lines = content.split("\n")
        if is_bilingual:
            en_line = lines[0] if lines else ""
            zh_line = lines[1] if len(lines) > 1 else ""
            pages = _split_bilingual_pages(en_line, zh_line)
            # 分配时间：按字符等效长度占比分配
            total_units = sum(_eq_units(a) + _eq_units(b) or 1.0 for a,b in pages) or 1.0
            total_sec = (sub.end - sub.start).total_seconds() or (0.001)
            # 最小单页时长（可调），不足则按比例压缩
            min_page = float(os.getenv("SUBTITLE_PAGE_MIN_SEC", "0.9"))
            need = min_page * len(pages)
            ratio = 1.0 if total_sec >= need else (total_sec / need)

            cur_start = sub.start
            acc = 0.0
            for idx, (en_i, zh_i) in enumerate(pages):
                units = (_eq_units(en_i) + _eq_units(zh_i)) or 1.0
                dur = (units / total_units) * total_sec
                # 施加下限，但全局按 ratio 缩放，避免总时长超出
                dur = max(min_page * ratio, dur)
                # 修正最后一页对齐
                if idx == len(pages) - 1:
                    dur = total_sec - acc
                cur_end = cur_start + timedelta(seconds=dur)
                page_text = (en_i + ("\n" if zh_i else "" ) + zh_i).strip()
                new_subs.append(srt.Subtitle(index=0, start=cur_start, end=cur_end, content=page_text))
                cur_start = cur_end
                acc += dur
        else:
            wrapped = _wrap_line_by_eq(content, max_eq)
            new_subs.append(srt.Subtitle(index=0, start=sub.start, end=sub.end, content=wrapped))

    with open(output_path, 'w', encoding='utf-8') as out:
        # 重新编号
        for i, sub in enumerate(new_subs, 1):
            sub.index = i
        out.write(srt.compose(new_subs))

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
        # 断句优化：支持开关。默认关闭以保持稳定，如需开启设 SUBTITLE_SMART_WRAP=1。
        if os.getenv('SUBTITLE_SMART_WRAP', '0') in {'1','true','True'}:
            _wrap_srt_for_width(srt_path, temp_srt_internal_path, width, height, is_bilingual, content_scale)
        else:
            shutil.copy2(srt_path, temp_srt_internal_path)
        
        # 设置输出路径
        output_path = os.path.join(temp_output_dir, "output.mp4")
        
        # 构建字幕滤镜
        # 增加 UTF-8 编码与字体目录，避免中文乱码/方块
        fonts_dir = find_fonts_dir()
        extra = []
        extra.append("charenc=UTF-8")
        if fonts_dir:
            extra.append(f"fontsdir={fonts_dir}")
        extra_opts = ":".join(extra)
        subtitle_filter_value = f"subtitles={temp_srt_internal_path}:{extra_opts}:force_style='{subtitle_style}'"
        logger.info(f"FFmpeg subtitles filter: {subtitle_filter_value}")

        # 4. 选择编码方案（GPU 优先）
        def _run_ffmpeg(cmd: list[str]):
            logger.info("执行 FFmpeg: %s", ' '.join(cmd))
            return subprocess.run(cmd, check=True, capture_output=True, text=True)

        def _build_gpu_cmd() -> list[str]:
            """GPU 编码命令（参考 KlicStudio 优化）"""
            cq = os.getenv('SUBTITLE_NVENC_CQ', '20')
            maxrate = os.getenv('SUBTITLE_MAXRATE', '15M')
            bufsize = os.getenv('SUBTITLE_BUFSIZE', '30M')
            aac_bps = os.getenv('SUBTITLE_AAC_BPS', '192k')
            return [
                'ffmpeg', '-hide_banner', '-loglevel', 'warning',
                '-i', temp_video_path,
                '-vf', subtitle_filter_value,
                '-c:v', 'h264_nvenc',
                '-preset', 'p4', '-tune', 'hq', '-rc', 'vbr', '-cq', cq,
                '-b:v', '0', '-maxrate', maxrate, '-bufsize', bufsize,
                '-spatial-aq', '1', '-temporal-aq', '1',
                '-c:a', 'aac', '-b:a', aac_bps, '-ar', '48000',
                '-movflags', '+faststart', '-y', output_path
            ]

        def _build_cpu_cmd() -> list[str]:
            """CPU 编码命令（参考 KlicStudio 优化）"""
            crf = os.getenv('SUBTITLE_X264_CRF', '23')
            aac_bps = os.getenv('SUBTITLE_AAC_BPS', '192k')
            return [
                'ffmpeg', '-hide_banner', '-loglevel', 'warning',
                '-i', temp_video_path,
                '-vf', subtitle_filter_value,
                '-c:v', 'libx264', '-preset', 'medium', '-crf', crf,
                '-profile:v', 'high', '-level', '4.0',
                '-c:a', 'aac', '-b:a', aac_bps, '-ar', '48000',
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
