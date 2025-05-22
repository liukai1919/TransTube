from typing import List, Tuple, Callable
import os
import math
import ffmpeg
import logging
import time
import csv
from concurrent.futures import ThreadPoolExecutor
import psutil
import GPUtil
import pysrt

logger = logging.getLogger(__name__)

def get_optimal_chunk_duration(duration: float) -> int:
    """
    根据视频时长计算最优切片长度
    
    Args:
        duration: 视频总时长（秒）
        
    Returns:
        int: 切片长度（秒）
    """
    if duration > 3600:  # 1小时以上
        return 180  # 3分钟
    elif duration > 1800:  # 30分钟以上
        return 240  # 4分钟
    else:
        return 300  # 5分钟

def split_video(video_path: str, output_dir: str, chunk_duration: int = None) -> List[str]:
    """
    将视频分割成多个片段
    
    Args:
        video_path: 视频文件路径
        output_dir: 输出目录
        chunk_duration: 切片时长（秒），如果为 None 则自动计算
        
    Returns:
        List[str]: 切片文件路径列表
    """
    try:
        # 获取视频时长
        probe = ffmpeg.probe(video_path)
        duration = float(probe['format']['duration'])
        
        # 如果未指定切片时长，则自动计算
        if chunk_duration is None:
            chunk_duration = get_optimal_chunk_duration(duration)
            
        # 计算切片数量
        num_chunks = math.ceil(duration / chunk_duration)
        chunk_files = []
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 分割视频
        for i in range(num_chunks):
            start_time = i * chunk_duration
            output_path = os.path.join(output_dir, f"chunk_{i:03d}.mp4")
            
            # 使用 GPU 加速的 FFmpeg 命令
            stream = (
                ffmpeg
                .input(video_path, ss=start_time, t=chunk_duration, hwaccel='cuda')
                .output(
                    output_path,
                    vcodec='h264_nvenc',  # 使用 NVIDIA GPU 编码
                    acodec='aac',
                    video_bitrate='2000k',
                    audio_bitrate='128k',
                    preset='p4',  # 平衡质量和速度
                    cq=23,  # 恒定质量参数
                    **{'b:v': '0'}  # 使用 VBR
                )
                .overwrite_output()
            )
            
            try:
                stream.run(capture_stdout=True, capture_stderr=True)
                chunk_files.append(output_path)
                logger.info(f"切片 {i+1}/{num_chunks} 完成: {output_path}")
            except ffmpeg.Error as e:
                logger.error(f"切片 {i+1}/{num_chunks} 失败: {str(e)}")
                raise
                
        return chunk_files
        
    except Exception as e:
        logger.error(f"视频分割失败: {str(e)}")
        raise

def process_chunk(chunk_path: str, output_dir: str, lang: str = "en") -> Tuple[str, float]:
    """
    处理单个视频切片
    
    Args:
        chunk_path: 切片文件路径
        output_dir: 输出目录
        lang: 语言代码
        
    Returns:
        Tuple[str, float]: (SRT文件路径, 实际音频时长)
    """
    try:
        # 生成状态文件路径
        done_file = f"{chunk_path}.done"
        fail_file = f"{chunk_path}.fail"
        
        # 检查是否已完成
        if os.path.exists(done_file):
            logger.info(f"切片已完成，跳过处理: {chunk_path}")
            with open(done_file, 'r') as f:
                return f.read().strip(), float(f.readline().strip())
                
        # 检查是否已失败
        if os.path.exists(fail_file):
            logger.info(f"切片处理失败，重试: {chunk_path}")
            os.remove(fail_file)
            
        # 获取实际音频时长
        probe = ffmpeg.probe(chunk_path)
        audio_duration = float(probe['format']['duration'])
        
        # 转录音频
        srt_path = transcribe_to_srt(chunk_path, lang)
        
        # 记录成功状态
        with open(done_file, 'w') as f:
            f.write(f"{srt_path}\n{audio_duration}")
            
        return srt_path, audio_duration
        
    except Exception as e:
        # 记录失败状态
        with open(fail_file, 'w') as f:
            f.write(str(e))
        logger.error(f"处理切片失败: {chunk_path}, 错误: {str(e)}")
        raise

def merge_subtitles(srt_files: List[Tuple[str, float]], output_path: str) -> str:
    """
    合并多个 SRT 文件
    
    Args:
        srt_files: SRT文件路径和实际时长的元组列表
        output_path: 输出文件路径
        
    Returns:
        str: 合并后的 SRT 文件路径
    """
    try:
        current_offset = 0
        current_index = 1
        
        with open(output_path, 'w', encoding='utf-8') as outfile:
            for srt_path, duration in srt_files:
                with open(srt_path, 'r', encoding='utf-8') as infile:
                    for line in infile:
                        if line.strip().isdigit():  # 字幕序号
                            outfile.write(f"{current_index}\n")
                            current_index += 1
                        elif '-->' in line:  # 时间戳
                            start, end = line.split(' --> ')
                            # 调整时间戳
                            new_start = adjust_timestamp(start, current_offset)
                            new_end = adjust_timestamp(end, current_offset)
                            outfile.write(f"{new_start} --> {new_end}\n")
                        else:  # 字幕文本
                            outfile.write(line)
                            
                # 更新偏移量
                current_offset += duration
                
        return output_path
        
    except Exception as e:
        logger.error(f"合并字幕失败: {str(e)}")
        raise

def adjust_timestamp(timestamp: str, offset: float) -> str:
    """
    调整时间戳
    
    Args:
        timestamp: 原始时间戳 (HH:MM:SS,mmm)
        offset: 偏移量（秒）
        
    Returns:
        str: 调整后的时间戳
    """
    try:
        # 解析时间戳
        hours, minutes, seconds = timestamp.replace(',', '.').split(':')
        total_seconds = float(hours) * 3600 + float(minutes) * 60 + float(seconds)
        
        # 添加偏移量
        total_seconds += offset
        
        # 重新格式化
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = total_seconds % 60
        milliseconds = int((seconds - int(seconds)) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"
        
    except Exception as e:
        logger.error(f"调整时间戳失败: {str(e)}")
        raise

class PerformanceMonitor:
    def __init__(self, log_file: str):
        self.log_file = log_file
        self.start_time = time.time()
        self.metrics = []
        
    def log_metrics(self, chunk_id: int, duration: float, fps: float, retry_count: int):
        """记录性能指标"""
        metrics = {
            'timestamp': time.time() - self.start_time,
            'chunk_id': chunk_id,
            'duration': duration,
            'fps': fps,
            'retry_count': retry_count,
            'cpu_percent': psutil.cpu_percent(),
            'memory_percent': psutil.virtual_memory().percent
        }
        
        # 获取 GPU 使用情况
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                metrics['gpu_memory_percent'] = gpus[0].memoryUtil * 100
                metrics['gpu_load'] = gpus[0].load * 100
        except:
            pass
            
        self.metrics.append(metrics)
        
    def save_metrics(self):
        """保存性能指标到 CSV 文件"""
        if not self.metrics:
            return
            
        fieldnames = self.metrics[0].keys()
        with open(self.log_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.metrics)

def get_optimal_workers() -> int:
    """
    计算最优的线程池大小
    
    Returns:
        int: 线程池大小
    """
    cpu_count = os.cpu_count() or 4
    try:
        gpu = GPUtil.getGPUs()[0]
        # 根据 GPU 的 SM 数量设置并发数
        gpu_workers = min(4, gpu.multi_processor_count // 2)
    except:
        gpu_workers = 1
        
    return min(cpu_count - 1, gpu_workers)

def process_video(
        video_path: str,
        transcribe_func: Callable,
        translate_func: Callable,
        burn_func: Callable
    ) -> Tuple[str, str]:
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
            optimized_srt = _optimize_subtitle_format(zh_srt_path)
            
            return output_video, optimized_srt
            
        except Exception as e:
            print(f"处理视频时出错: {str(e)}")
            raise
    
    def _optimize_subtitle_format(self, srt_path: str) -> str:
        """优化字幕格式"""
        try:
            # 读取原始字幕
            with open(srt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析字幕
            subs = pysrt.open(srt_path)
            
            # 优化字幕格式
            optimized_subs = []
            for sub in subs:
                # 1. 移除多余的空格
                text = ' '.join(sub.text.split())
                
                # 2. 限制每行最大字符数（中文字符）
                max_chars_per_line = 20
                if len(text) > max_chars_per_line:
                    # 在标点符号处换行
                    punctuation = ['，', '。', '！', '？', '；', '：', '、']
                    lines = []
                    current_line = ''
                    
                    for char in text:
                        current_line += char
                        if len(current_line) >= max_chars_per_line and char in punctuation:
                            lines.append(current_line)
                            current_line = ''
                    
                    if current_line:
                        lines.append(current_line)
                    
                    text = '\n'.join(lines)
                
                # 3. 设置字幕样式
                sub.text = text
                optimized_subs.append(sub)
            
            # 保存优化后的字幕
            optimized_srt_path = srt_path.replace('.srt', '_optimized.srt')
            with open(optimized_srt_path, 'w', encoding='utf-8') as f:
                for sub in optimized_subs:
                    f.write(f"{sub.index}\n")
                    f.write(f"{sub.start} --> {sub.end}\n")
                    f.write(f"{sub.text}\n\n")
            
            return optimized_srt_path
            
        except Exception as e:
            print(f"优化字幕格式时出错: {str(e)}")
            return srt_path 