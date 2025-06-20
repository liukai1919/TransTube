# -*- coding: utf-8 -*-
"""
本地语音转换服务
实现 A→B→C→D 完整管道：音频输入→语音识别→翻译→语音合成
使用推荐的本地模型：faster-whisper + NLLB + VITS
"""

import os
import logging
import tempfile
import torch
import numpy as np
import soundfile as sf
from pathlib import Path
from typing import Optional, List, Dict, Any
import srt
from datetime import timedelta

# 导入所需的模型库
try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    logging.warning("faster-whisper not available, falling back to whisper")

try:
    from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    NLLB_AVAILABLE = True
except ImportError:
    NLLB_AVAILABLE = False
    logging.warning("NLLB models not available")

try:
    import torch
    import torchaudio
    from TTS.api import TTS
    VITS_AVAILABLE = True
except ImportError:
    VITS_AVAILABLE = False
    logging.warning("VITS/TTS not available")

logger = logging.getLogger(__name__)

class LocalSpeechTranslationPipeline:
    """本地语音翻译管道"""
    
    def __init__(self, 
                 whisper_model_size: str = "large-v3",
                 translation_model: str = "nllb-200-distilled-1.3B",
                 tts_model: str = "tts_models/zh-CN/baker/tacotron2-DDC-GST",
                 device: str = "auto"):
        """
        初始化本地语音翻译管道
        
        Args:
            whisper_model_size: Whisper模型大小 (tiny, base, small, medium, large-v3)
            translation_model: 翻译模型名称
            tts_model: TTS模型名称
            device: 设备 (auto, cpu, cuda)
        """
        self.device = self._get_device(device)
        self.whisper_model = None
        self.translation_model = None
        self.translation_tokenizer = None
        self.tts_model = None
        
        # 模型配置
        self.whisper_model_size = whisper_model_size
        self.translation_model_name = translation_model
        self.tts_model_name = tts_model
        
        # 初始化模型
        self._init_models()
    
    def _get_device(self, device: str) -> str:
        """获取计算设备"""
        if device == "auto":
            if torch.cuda.is_available():
                return "cuda"
            else:
                return "cpu"
        return device
    
    def _init_models(self):
        """初始化所有模型"""
        logger.info("正在初始化本地语音翻译模型...")
        
        # Stage B: 初始化 ASR 模型 (faster-whisper)
        self._init_whisper_model()
        
        # Stage C: 初始化翻译模型 (NLLB)
        self._init_translation_model()
        
        # Stage D: 初始化 TTS 模型 (VITS)
        self._init_tts_model()
        
        logger.info("所有模型初始化完成")
    
    def _init_whisper_model(self):
        """初始化 Whisper ASR 模型"""
        try:
            if FASTER_WHISPER_AVAILABLE:
                logger.info(f"正在加载 faster-whisper {self.whisper_model_size} 模型...")
                
                # 根据设备选择计算类型
                compute_type = "float16" if self.device == "cuda" else "int8"
                
                self.whisper_model = WhisperModel(
                    self.whisper_model_size,
                    device=self.device,
                    compute_type=compute_type,
                    download_root=os.path.expanduser("~/.cache/whisper")
                )
                logger.info("faster-whisper 模型加载完成")
            else:
                # 回退到标准 whisper
                import whisper
                logger.info(f"正在加载标准 whisper {self.whisper_model_size} 模型...")
                self.whisper_model = whisper.load_model(self.whisper_model_size, device=self.device)
                logger.info("标准 whisper 模型加载完成")
                
        except Exception as e:
            logger.error(f"初始化 Whisper 模型失败: {str(e)}")
            raise
    
    def _init_translation_model(self):
        """初始化 NLLB 翻译模型"""
        try:
            if NLLB_AVAILABLE:
                logger.info(f"正在加载 NLLB 翻译模型: {self.translation_model_name}")
                
                # 使用 NLLB-200 模型
                model_name = f"facebook/{self.translation_model_name}"
                
                self.translation_tokenizer = AutoTokenizer.from_pretrained(model_name)
                self.translation_model = AutoModelForSeq2SeqLM.from_pretrained(
                    model_name,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
                ).to(self.device)
                
                logger.info("NLLB 翻译模型加载完成")
            else:
                logger.warning("NLLB 不可用，将使用备用翻译方法")
                
        except Exception as e:
            logger.error(f"初始化翻译模型失败: {str(e)}")
            # 不抛出异常，使用备用翻译方法
    
    def _init_tts_model(self):
        """初始化 VITS TTS 模型"""
        try:
            if VITS_AVAILABLE:
                logger.info(f"正在加载 TTS 模型: {self.tts_model_name}")
                
                # 初始化 TTS 模型
                self.tts_model = TTS(
                    model_name=self.tts_model_name,
                    progress_bar=False,
                    gpu=self.device == "cuda"
                )
                
                logger.info("TTS 模型加载完成")
            else:
                logger.warning("TTS 不可用，将使用备用语音合成方法")
                
        except Exception as e:
            logger.error(f"初始化 TTS 模型失败: {str(e)}")
            # 不抛出异常，使用备用 TTS 方法
    
    def transcribe_audio(self, audio_path: str, language: str = "en") -> List[Dict]:
        """
        Stage B: 语音识别 (ASR)
        
        Args:
            audio_path: 音频文件路径
            language: 源语言代码
            
        Returns:
            转录结果列表，包含时间戳和文本
        """
        try:
            logger.info(f"正在转录音频: {audio_path}")
            
            if FASTER_WHISPER_AVAILABLE and hasattr(self.whisper_model, 'transcribe'):
                # 使用 faster-whisper
                segments, info = self.whisper_model.transcribe(
                    audio_path,
                    language=language,
                    beam_size=5,
                    word_timestamps=True
                )
                
                results = []
                for segment in segments:
                    results.append({
                        "start": segment.start,
                        "end": segment.end,
                        "text": segment.text.strip()
                    })
                
                logger.info(f"转录完成，检测到语言: {info.language}, 置信度: {info.language_probability:.2f}")
                
            else:
                # 使用标准 whisper
                result = self.whisper_model.transcribe(audio_path, language=language)
                
                results = []
                for segment in result["segments"]:
                    results.append({
                        "start": segment["start"],
                        "end": segment["end"],
                        "text": segment["text"].strip()
                    })
                
                logger.info("转录完成")
            
            return results
            
        except Exception as e:
            logger.error(f"音频转录失败: {str(e)}")
            raise
    
    def translate_text(self, text: str, source_lang: str = "eng_Latn", target_lang: str = "zho_Hans") -> str:
        """
        Stage C: 文本翻译 (NMT)
        
        Args:
            text: 待翻译文本
            source_lang: 源语言代码 (NLLB格式)
            target_lang: 目标语言代码 (NLLB格式)
            
        Returns:
            翻译后的文本
        """
        try:
            if self.translation_model and self.translation_tokenizer:
                # 使用 NLLB 模型翻译
                logger.debug(f"正在翻译文本: {text[:50]}...")
                
                # 设置源语言
                self.translation_tokenizer.src_lang = source_lang
                
                # 编码输入文本
                inputs = self.translation_tokenizer(
                    text,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=512
                ).to(self.device)
                
                # 生成翻译
                with torch.no_grad():
                    generated_tokens = self.translation_model.generate(
                        **inputs,
                        forced_bos_token_id=self.translation_tokenizer.lang_code_to_id[target_lang],
                        max_length=512,
                        num_beams=5,
                        early_stopping=True
                    )
                
                # 解码结果
                translated_text = self.translation_tokenizer.batch_decode(
                    generated_tokens, skip_special_tokens=True
                )[0]
                
                logger.debug(f"翻译结果: {translated_text[:50]}...")
                return translated_text
                
            else:
                # 备用翻译方法
                logger.warning("使用备用翻译方法")
                from ..translator import translate_text
                return translate_text(text, target_lang="zh")
                
        except Exception as e:
            logger.error(f"文本翻译失败: {str(e)}")
            # 返回原文本作为备用
            return text
    
    def synthesize_speech(self, text: str, output_path: str = None) -> str:
        """
        Stage D: 语音合成 (TTS)
        
        Args:
            text: 待合成的文本
            output_path: 输出音频文件路径
            
        Returns:
            生成的音频文件路径
        """
        try:
            if not output_path:
                output_path = tempfile.mktemp(suffix=".wav")
            
            logger.info(f"正在合成语音: {text[:50]}...")
            
            if self.tts_model:
                # 使用 VITS/TTS 模型
                self.tts_model.tts_to_file(
                    text=text,
                    file_path=output_path
                )
                
                logger.info(f"语音合成完成: {output_path}")
                
            else:
                # 备用 TTS 方法
                logger.warning("使用备用 TTS 方法")
                from gtts import gTTS
                tts = gTTS(text=text, lang='zh-cn')
                tts.save(output_path)
            
            return output_path
            
        except Exception as e:
            logger.error(f"语音合成失败: {str(e)}")
            raise
    
    def process_audio_to_audio(self, 
                              input_audio_path: str,
                              output_audio_path: str = None,
                              source_lang: str = "en",
                              target_lang: str = "zh") -> str:
        """
        完整的 A→B→C→D 管道处理
        
        Args:
            input_audio_path: 输入音频文件路径
            output_audio_path: 输出音频文件路径
            source_lang: 源语言
            target_lang: 目标语言
            
        Returns:
            输出音频文件路径
        """
        try:
            logger.info("开始完整的语音翻译管道处理...")
            
            # Stage B: 语音识别
            logger.info("Stage B: 执行语音识别...")
            transcription_results = self.transcribe_audio(input_audio_path, language=source_lang)
            
            # 合并所有转录文本
            full_text = " ".join([segment["text"] for segment in transcription_results])
            logger.info(f"转录文本: {full_text[:100]}...")
            
            # Stage C: 文本翻译
            logger.info("Stage C: 执行文本翻译...")
            
            # 语言代码映射
            lang_mapping = {
                "en": "eng_Latn",
                "zh": "zho_Hans",
                "zh-cn": "zho_Hans"
            }
            
            source_lang_code = lang_mapping.get(source_lang, "eng_Latn")
            target_lang_code = lang_mapping.get(target_lang, "zho_Hans")
            
            translated_text = self.translate_text(
                full_text, 
                source_lang=source_lang_code,
                target_lang=target_lang_code
            )
            logger.info(f"翻译文本: {translated_text[:100]}...")
            
            # Stage D: 语音合成
            logger.info("Stage D: 执行语音合成...")
            if not output_audio_path:
                output_audio_path = tempfile.mktemp(suffix=".wav")
            
            final_audio_path = self.synthesize_speech(translated_text, output_audio_path)
            
            logger.info(f"完整管道处理完成: {final_audio_path}")
            return final_audio_path
            
        except Exception as e:
            logger.error(f"完整管道处理失败: {str(e)}")
            raise
    
    def process_video_to_chinese_audio(self, video_path: str) -> str:
        """
        从视频生成中文配音
        这是对原有 english_audio_to_chinese_voice 函数的本地化替代
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            生成的中文音频文件路径
        """
        try:
            logger.info(f"正在处理视频生成中文配音: {video_path}")
            
            # 从视频中提取音频
            import ffmpeg
            temp_audio = tempfile.mktemp(suffix=".wav")
            
            (
                ffmpeg
                .input(video_path)
                .output(temp_audio, acodec='pcm_s16le', ac=1, ar='16000')
                .overwrite_output()
                .run(quiet=True)
            )
            
            # 使用完整管道处理
            output_audio = self.process_audio_to_audio(
                input_audio_path=temp_audio,
                source_lang="en",
                target_lang="zh"
            )
            
            # 清理临时文件
            if os.path.exists(temp_audio):
                os.unlink(temp_audio)
            
            logger.info(f"中文配音生成完成: {output_audio}")
            return output_audio
            
        except Exception as e:
            logger.error(f"生成中文配音失败: {str(e)}")
            raise

# 全局实例
_pipeline_instance = None

def get_local_pipeline() -> LocalSpeechTranslationPipeline:
    """获取全局管道实例（单例模式），从环境变量读取模型配置"""
    global _pipeline_instance
    if _pipeline_instance is None:
        whisper_size = os.getenv("WHISPER_MODEL_SIZE", "large-v3")
        translation_model = os.getenv("TRANSLATION_MODEL", "nllb-200-distilled-1.3B")
        tts_model = os.getenv("LOCAL_TTS_MODEL", "tts_models/zh-CN/baker/tacotron2-DDC-GST")
        device = os.getenv("TORCH_DEVICE", "auto")
        _pipeline_instance = LocalSpeechTranslationPipeline(
            whisper_model_size=whisper_size,
            translation_model=translation_model,
            tts_model=tts_model,
            device=device
        )
    return _pipeline_instance

def english_audio_to_chinese_voice_local(video_path: str) -> str:
    """
    本地化的英文音频转中文语音函数
    替代原有的 gTTS 实现
    """
    pipeline = get_local_pipeline()
    return pipeline.process_video_to_chinese_audio(video_path) 