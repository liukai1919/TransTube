# -*- coding: utf-8 -*-
"""
视频切片并行处理管线
"""
import os
import uuid
import tempfile
import subprocess
import threading
import time
import logging
import srt  # 添加 srt 模块导入
import pysrt  # 添加 pysrt 模块导入
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Optional, Callable
from datetime import timedelta
import shutil

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self, chunk_duration=300, max_workers=8, progress_callback=None):
        """
        初始化视频处理器
        
        Args:
            chunk_duration: 每个切片的时长（秒）
            max_workers: 最大并行工作线程数
            progress_callback: 进度回调函数
        """
        self.chunk_duration = chunk_duration  # 默认5分钟一个切片
        self.max_workers = max_workers  # 默认8个并行处理线程
        self.progress_callback = progress_callback
        self.temp_dir = tempfile.mkdtemp()
        self.current_progress = 0
        self.total_steps = 0
        self.lock = threading.Lock()
        
        # 检查是否支持 GPU 加速
        self.use_gpu = False
        try:
            # 检查 NVIDIA GPU 是否可用
            nvidia_smi = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
            if nvidia_smi.returncode == 0:
                # 检查 FFmpeg 是否支持 NVENC
                ffmpeg_encoders = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True)
                if 'h264_nvenc' in ffmpeg_encoders.stdout:
                    self.use_gpu = True
                    logger.info("检测到 NVIDIA GPU 和 NVENC 支持，将使用 GPU 加速")
                else:
                    logger.warning("FFmpeg 未编译 NVENC 支持，将使用 CPU 编码")
            else:
                logger.info("未检测到 NVIDIA GPU，将使用 CPU 编码")
        except Exception as e:
            logger.error(f"检查 GPU 支持时出错: {e}")
        
    def update_progress(self, message: str, increment: float = 0):
        """更新进度"""
        if self.progress_callback:
            with self.lock:
                self.current_progress += increment
                progress = min(100, self.current_progress * 100 / max(1, self.total_steps))
                self.progress_callback(message, progress)
        
    def get_video_duration(self, video_path: str) -> int:
        """获取视频时长（秒）"""
        cmd = [
            'ffprobe', 
            '-v', 'error', 
            '-show_entries', 'format=duration', 
            '-of', 'default=noprint_wrappers=1:nokey=1', 
            video_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return int(float(result.stdout.strip()))
        except subprocess.CalledProcessError as e:
            logger.error(f"获取视频时长失败: {e.stderr}")
            raise Exception(f"无法获取视频时长: {str(e)}")
        
    def split_video(self, video_path: str) -> List[Dict]:
        """
        将视频分割成多个切片
        
        Returns:
            List[Dict]: 包含每个切片信息的列表，每个字典包含:
                - chunk_path: 切片路径
                - start_time: 开始时间（秒）
                - duration: 时长（秒）
                - index: 切片索引
        """
        duration = self.get_video_duration(video_path)
        chunks = []
        
        # 计算切片数量
        chunk_count = (duration + self.chunk_duration - 1) // self.chunk_duration
        self.total_steps = chunk_count * 3 + 2
        
        # 分割视频
        for i in range(chunk_count):
            start_time = i * self.chunk_duration
            current_duration = min(self.chunk_duration, duration - start_time)
            
            chunk_path = os.path.join(self.temp_dir, f"chunk_{i:04d}.mp4")
            
            # 基础命令
            cmd = [
                'ffmpeg',
                '-v', 'warning',  # 改为 warning 级别以获取更多信息
                '-ss', str(start_time),
                '-i', video_path,
                '-t', str(current_duration),
            ]
            
            # 如果支持 GPU，使用 NVENC 编码器
            if self.use_gpu:
                cmd.extend([
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
                cmd.extend([
                    '-c:v', 'libx264',  # 使用 CPU 编码器
                    '-preset', 'medium',
                    '-crf', '23',
                    '-profile:v', 'high',
                    '-level', '4.0',
                ])
            
            # 通用参数
            cmd.extend([
                '-pix_fmt', 'yuv420p',  # 像素格式，确保兼容性
                '-movflags', '+faststart',  # 优化网络播放
                # 音频编码设置
                '-c:a', 'aac',  # 音频编码
                '-b:a', '192k',  # 音频比特率
                '-ar', '48000',  # 音频采样率
                '-ac', '2',  # 双声道
                # 其他设置
                '-y',  # 覆盖已存在的文件
                '-threads', '0',  # 自动选择线程数
                chunk_path
            ])
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                if result.stderr:
                    logger.warning(f"视频切片 {i+1}/{chunk_count} 警告: {result.stderr}")
                
                # 验证切片是否有效
                if not os.path.exists(chunk_path) or os.path.getsize(chunk_path) == 0:
                    raise Exception(f"切片文件无效: {chunk_path}")
            
                chunks.append({
                    'chunk_path': chunk_path,
                    'start_time': start_time,
                    'duration': current_duration,
                    'index': i
                })
                
                self.update_progress(f"已切分视频片段 {i+1}/{chunk_count}", 1)
            except subprocess.CalledProcessError as e:
                logger.error(f"视频切片 {i+1}/{chunk_count} 失败: {e.stderr}")
                raise Exception(f"视频切片失败: {str(e)}")
            
        return chunks
    
    def process_chunk(self, chunk: Dict, transcribe_func: Callable, translate_func: Callable) -> Dict:
        """处理单个视频切片"""
        try:
            # 转录
            self.update_progress(f"正在转录片段 {chunk['index']+1}", 0)
            srt_path = transcribe_func(chunk['chunk_path'])
            if not srt_path or not os.path.exists(srt_path):
                raise Exception(f"转录失败: 未生成有效的字幕文件")
            self.update_progress(f"片段 {chunk['index']+1} 转录完成", 1)
            
            # 翻译
            self.update_progress(f"正在翻译片段 {chunk['index']+1}", 0)
            zh_srt_path = translate_func(srt_path)
            if not zh_srt_path or not os.path.exists(zh_srt_path):
                raise Exception(f"翻译失败: 未生成有效的字幕文件")
            self.update_progress(f"片段 {chunk['index']+1} 翻译完成", 1)
            
            return {
                **chunk,
                'srt_path': srt_path,
                'zh_srt_path': zh_srt_path
            }
        except Exception as e:
            logger.error(f"处理切片 {chunk['index']+1} 时出错: {str(e)}")
            raise
    
    def adjust_subtitle_timing(self, srt_path: str, start_time: int) -> str:
        """调整字幕时间戳"""
        try:
            with open(srt_path, 'r', encoding='utf-8') as f:
                subs = list(srt.parse(f.read()))
            
            # 调整每个字幕的时间戳
            for sub in subs:
                sub.start = sub.start + timedelta(seconds=start_time)
                sub.end = sub.end + timedelta(seconds=start_time)
            
            # 保存调整后的字幕
            adjusted_path = os.path.join(self.temp_dir, f"adjusted_{os.path.basename(srt_path)}")
            with open(adjusted_path, 'w', encoding='utf-8') as f:
                f.write(srt.compose(subs))
                
            return adjusted_path
        except Exception as e:
            logger.error(f"调整字幕时间戳失败: {str(e)}")
            raise
    
    def merge_subtitles(self, subtitle_paths: List[str]) -> str:
        """合并多个字幕文件"""
        try:
            all_subs = []
            for path in subtitle_paths:
                with open(path, 'r', encoding='utf-8') as f:
                    subs = list(srt.parse(f.read()))
                    all_subs.extend(subs)
            
            # 按时间排序
            all_subs.sort(key=lambda x: x.start)
        
            # 重新编号
            for i, sub in enumerate(all_subs, 1):
                sub.index = i
            
            # 保存合并后的字幕
            merged_path = os.path.join(self.temp_dir, "merged.srt")
            with open(merged_path, 'w', encoding='utf-8') as f:
                f.write(srt.compose(all_subs))
            
            return merged_path
        except Exception as e:
            logger.error(f"合并字幕失败: {str(e)}")
            raise
    
    def process_video(self, video_path: str, transcribe_func: Callable, translate_func: Callable, burn_func: Callable) -> Tuple[str, str]:
        """处理视频：转写、翻译、烧录字幕"""
        try:
            # 1. 转写视频生成英文字幕
            print("开始转写视频...")
            srt_path = transcribe_func(video_path)
            if not srt_path or not os.path.exists(srt_path):
                raise Exception("转写失败：未生成字幕文件")
            
            # 2. 翻译字幕为中文
            print("开始翻译字幕...")
            zh_srt_path = translate_func(srt_path)
            if not zh_srt_path or not os.path.exists(zh_srt_path):
                raise Exception("翻译失败：未生成中文字幕文件")
            
            # 3. 烧录字幕到视频
            print("开始烧录字幕...")
            output_video = burn_func(video_path, zh_srt_path)
            if not output_video or not os.path.exists(output_video):
                raise Exception("烧录失败：未生成带字幕的视频文件")
            
            # 4. 优化字幕格式
            print("优化字幕格式...")
            optimized_srt = self.optimize_subtitle_format(zh_srt_path)
            
            return output_video, optimized_srt
            
        except Exception as e:
            print(f"处理视频时出错: {str(e)}")
            raise

    def optimize_subtitle_format(self, srt_path: str) -> str:
        """优化字幕格式"""
        try:
            # 读取原始字幕
            with open(srt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析字幕
            subs = pysrt.open(srt_path)
            
            # 优化字幕格式
            optimized_subs = []
            merge_gap = 0.8  # 小于 0.8 秒的间隔自动合并
            max_chars_per_line = 20

            buffer_sub = None

            def flush_buffer(buf):
                if buf:
                    optimized_subs.append(buf)

            for sub in subs:
                # 清理文本
                text_clean = ' '.join(sub.text.split())

                if buffer_sub is None:
                    buffer_sub = sub
                    buffer_sub.text = text_clean
                    continue

                gap = (sub.start - buffer_sub.end).total_seconds()
                combined_len = len(buffer_sub.text.replace('\n', '')) + len(text_clean)

                if gap <= merge_gap and combined_len <= max_chars_per_line * 2:
                    # 合并：扩展结束时间并追加文本（用空格分隔）
                    buffer_sub.end = sub.end
                    buffer_sub.text += '\n' + text_clean
                else:
                    flush_buffer(buffer_sub)
                    buffer_sub = sub
                    buffer_sub.text = text_clean

            flush_buffer(buffer_sub)

            # 再次限制每行长度及重排 index
            punctuation = ['，', '。', '！', '？', '；', '：', '、']
            final_subs = []
            for idx, sub in enumerate(optimized_subs, 1):
                lines = []
                for line in sub.text.split('\n'):
                    if len(line) > max_chars_per_line:
                        cur = ''
                        for ch in line:
                            cur += ch
                            if len(cur) >= max_chars_per_line and ch in punctuation:
                                lines.append(cur)
                                cur = ''
                        if cur:
                            lines.append(cur)
                    else:
                        lines.append(line)
                sub.index = idx
                sub.text = '\n'.join(lines)
                final_subs.append(sub)
            
            # 保存优化后的字幕
            optimized_srt_path = srt_path.replace('.srt', '_optimized.srt')
            with open(optimized_srt_path, 'w', encoding='utf-8') as f:
                for sub in final_subs:
                    f.write(f"{sub.index}\n")
                    f.write(f"{sub.start} --> {sub.end}\n")
                    f.write(f"{sub.text}\n\n")
            
            return optimized_srt_path
            
        except Exception as e:
            logger.error(f"优化字幕格式时出错: {str(e)}")
            return srt_path