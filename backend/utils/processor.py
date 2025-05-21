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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Optional, Callable
from datetime import timedelta

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
        import srt
        
        try:
            # 将开始时间转换为timedelta对象
            start_timedelta = timedelta(seconds=start_time)
            
            # 读取SRT文件
            with open(srt_path, 'r', encoding='utf-8') as f:
                subs = list(srt.parse(f.read()))
            
            # 调整时间戳
            for sub in subs:
                sub.start = sub.start + start_timedelta
                sub.end = sub.end + start_timedelta
            
            # 保存调整后的字幕
            adjusted_path = srt_path.replace('.srt', f'.adjusted_{start_time}.srt')
            with open(adjusted_path, 'w', encoding='utf-8') as f:
                f.write(srt.compose(subs))
                
            return adjusted_path
        except Exception as e:
            logger.error(f"调整字幕时间戳失败: {str(e)}")
            raise Exception(f"调整字幕时间戳失败: {str(e)}")
    
    def merge_subtitles(self, processed_chunks: List[Dict]) -> str:
        """合并所有字幕"""
        import srt
        
        try:
            # 按索引排序
            processed_chunks.sort(key=lambda x: x['index'])
            
            all_subs = []
            current_index = 1
            
            for chunk in processed_chunks:
                # 调整字幕时间
                adjusted_srt = self.adjust_subtitle_timing(
                    chunk['zh_srt_path'], 
                    chunk['start_time']
                )
                
                # 读取调整后的字幕
                with open(adjusted_srt, 'r', encoding='utf-8') as f:
                    subs = list(srt.parse(f.read()))
                
                # 更新字幕索引并添加到列表
                for sub in subs:
                    sub.index = current_index
                    current_index += 1
                    all_subs.append(sub)
            
            # 合并所有字幕
            merged_srt = srt.compose(all_subs)
            merged_path = os.path.join(self.temp_dir, f"merged_{uuid.uuid4()}.srt")
            
            with open(merged_path, 'w', encoding='utf-8') as f:
                f.write(merged_srt)
                
            self.update_progress(f"已合并所有字幕", 1)
            return merged_path
        except Exception as e:
            logger.error(f"合并字幕失败: {str(e)}")
            raise Exception(f"合并字幕失败: {str(e)}")
    
    def process_video(self, video_path: str, transcribe_func: Callable, translate_func: Callable, burn_subtitle_func: Callable) -> Tuple[str, str]:
        """
        处理完整视频
        
        Args:
            video_path: 视频路径
            transcribe_func: 转录函数，接收视频路径参数，返回SRT路径
            translate_func: 翻译函数，接收SRT路径参数，返回翻译后的SRT路径
            burn_subtitle_func: 烧录字幕函数，接收视频路径和SRT路径参数，返回输出视频路径
            
        Returns:
            Tuple[str, str]: (处理后的视频路径, 字幕文件路径)
        """
        try:
            # 重置进度
            self.current_progress = 0
            
            # 获取视频时长
            duration = self.get_video_duration(video_path)
            logger.info(f"视频时长: {duration}秒")
            
            # 如果视频时长小于20分钟，直接处理整个视频
            if duration <= 1200:  # 20分钟 = 1200秒
                logger.info("视频时长小于20分钟，将直接处理整个视频")
                self.update_progress("正在转录视频...", 0)
                srt_path = transcribe_func(video_path)
                self.update_progress("转录完成，正在翻译...", 50)
                zh_srt_path = translate_func(srt_path)
                self.update_progress("翻译完成，正在烧录字幕...", 75)
                output_video = burn_subtitle_func(video_path, zh_srt_path)
                self.update_progress("处理完成!", 100)
                return output_video, zh_srt_path
            
            # 对于长视频，进行切片处理
            self.update_progress("开始切分视频...", 0)
            chunks = self.split_video(video_path)
            
            # 2. 并行处理各个切片
            processed_chunks = []
            
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(
                        self.process_chunk, 
                        chunk, 
                        transcribe_func, 
                        translate_func
                    ): chunk for chunk in chunks
                }
                
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        processed_chunks.append(result)
                    except Exception as e:
                        logger.error(f"处理切片时出错: {str(e)}")
                        raise
            
            # 3. 合并字幕
            self.update_progress("正在合并字幕...", 0)
            merged_srt = self.merge_subtitles(processed_chunks)
            
            # 4. 烧录字幕
            self.update_progress("正在烧录字幕...", 0)
            output_video = burn_subtitle_func(video_path, merged_srt)
            self.update_progress("视频处理完成!", 1)
            
            return output_video, merged_srt
        except Exception as e:
            logger.error(f"视频处理失败: {str(e)}")
            raise Exception(f"视频处理失败: {str(e)}") 