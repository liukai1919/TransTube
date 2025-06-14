import os
import re
import tempfile
import logging
from typing import Optional, Dict, List, Tuple
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import SRTFormatter
import srt

logger = logging.getLogger(__name__)

class SubtitleExtractor:
    """YouTube字幕提取器，使用youtube-transcript-api"""
    
    def __init__(self):
        self.formatter = SRTFormatter()
    
    def extract_video_id(self, url: str) -> Optional[str]:
        """从YouTube URL中提取视频ID"""
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([^&\n?#]+)',
            r'youtube\.com/watch\?.*v=([^&\n?#]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        logger.error(f"无法从URL中提取视频ID: {url}")
        return None
    
    def get_available_transcripts(self, video_id: str) -> Dict:
        """获取可用的字幕信息"""
        try:
            # 获取字幕列表
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            available_transcripts = {
                'manual': [],
                'generated': [],
                'translatable_languages': []
            }
            
            for transcript in transcript_list:
                transcript_info = {
                    'language': transcript.language,
                    'language_code': transcript.language_code,
                    'is_generated': transcript.is_generated,
                    'is_translatable': transcript.is_translatable
                }
                
                if transcript.is_generated:
                    available_transcripts['generated'].append(transcript_info)
                else:
                    available_transcripts['manual'].append(transcript_info)
                
                # 如果可翻译，添加可翻译语言列表
                if transcript.is_translatable:
                    try:
                        translatable_langs = [
                            {'code': lang['language_code'], 'name': lang['language']} 
                            for lang in transcript.translation_languages
                        ]
                        available_transcripts['translatable_languages'] = translatable_langs
                    except:
                        pass
            
            logger.info(f"视频 {video_id} 可用字幕: 手动={len(available_transcripts['manual'])}, 自动={len(available_transcripts['generated'])}")
            return available_transcripts
            
        except Exception as e:
            logger.error(f"获取字幕列表失败 {video_id}: {str(e)}")
            return {'manual': [], 'generated': [], 'translatable_languages': []}
    
    def download_transcript(self, video_id: str, language_codes: List[str] = None, 
                          prefer_manual: bool = True) -> Optional[str]:
        """
        下载字幕并保存为SRT文件
        
        Args:
            video_id: YouTube视频ID
            language_codes: 优先语言代码列表，默认['en', 'en-US', 'en-GB']
            prefer_manual: 是否优先选择手动字幕
            
        Returns:
            str: SRT文件路径，失败返回None
        """
        if language_codes is None:
            language_codes = ['en', 'en-US', 'en-GB']
        
        try:
            # 获取字幕
            transcript_data = None
            used_language = None
            is_generated = False
            
            # 尝试获取字幕
            for lang_code in language_codes:
                try:
                    if prefer_manual:
                        # 优先尝试手动字幕
                        try:
                            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                            transcript = transcript_list.find_manually_created_transcript([lang_code])
                            transcript_data = transcript.fetch()
                            used_language = lang_code
                            is_generated = False
                            logger.info(f"获取到手动字幕: {lang_code}")
                            break
                        except:
                            # 如果没有手动字幕，尝试自动生成的
                            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                            transcript = transcript_list.find_generated_transcript([lang_code])
                            transcript_data = transcript.fetch()
                            used_language = lang_code
                            is_generated = True
                            logger.info(f"获取到自动生成字幕: {lang_code}")
                            break
                    else:
                        # 直接获取任何可用的字幕
                        transcript_data = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang_code])
                        used_language = lang_code
                        logger.info(f"获取到字幕: {lang_code}")
                        break
                        
                except Exception as e:
                    logger.debug(f"语言 {lang_code} 字幕获取失败: {str(e)}")
                    continue
            
            if not transcript_data:
                logger.warning(f"视频 {video_id} 没有找到可用的字幕")
                return None
            
            # 转换为SRT格式
            srt_content = self.convert_to_srt(transcript_data)
            
            # 保存到临时文件
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8')
            temp_file.write(srt_content)
            temp_file.close()
            
            logger.info(f"字幕已保存到: {temp_file.name} (语言: {used_language}, 自动生成: {is_generated})")
            return temp_file.name
            
        except Exception as e:
            logger.error(f"下载字幕失败 {video_id}: {str(e)}")
            return None
    
    def convert_to_srt(self, transcript_data: List[Dict]) -> str:
        """将transcript数据转换为SRT格式"""
        try:
            srt_subtitles = []
            
            for i, entry in enumerate(transcript_data, 1):
                start_time = entry['start']
                duration = entry.get('duration', 2.0)  # 默认2秒
                end_time = start_time + duration
                text = entry['text'].strip()
                
                if text:  # 只添加非空文本
                    subtitle = srt.Subtitle(
                        index=i,
                        start=srt.timedelta(seconds=start_time),
                        end=srt.timedelta(seconds=end_time),
                        content=text
                    )
                    srt_subtitles.append(subtitle)
            
            return srt.compose(srt_subtitles)
            
        except Exception as e:
            logger.error(f"转换SRT格式失败: {str(e)}")
            raise
    
    def download_translated_transcript(self, video_id: str, target_language: str = 'zh-Hans') -> Optional[str]:
        """
        下载翻译后的字幕
        
        Args:
            video_id: YouTube视频ID
            target_language: 目标语言代码，默认'zh-Hans'（简体中文）
            
        Returns:
            str: SRT文件路径，失败返回None
        """
        # 语言代码映射
        language_mapping = {
            'zh': 'zh-Hans',  # 中文映射到简体中文
            'zh-cn': 'zh-Hans',
            'chinese': 'zh-Hans'
        }
        
        # 标准化语言代码
        normalized_lang = language_mapping.get(target_language.lower(), target_language)
        
        try:
            # 尝试获取已翻译的字幕
            transcript_data = YouTubeTranscriptApi.get_transcript(
                video_id, 
                languages=[normalized_lang]
            )
            
            # 转换为SRT格式
            srt_content = self.convert_to_srt(transcript_data)
            
            # 保存到临时文件
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix=f'_{normalized_lang}.srt', delete=False, encoding='utf-8')
            temp_file.write(srt_content)
            temp_file.close()
            
            logger.info(f"翻译字幕已保存到: {temp_file.name} (语言: {normalized_lang})")
            return temp_file.name
            
        except Exception as e:
            logger.warning(f"下载翻译字幕失败 {video_id} -> {normalized_lang}: {str(e)}")
            
            # 如果翻译失败，尝试获取英文原文
            logger.info(f"翻译失败，尝试获取英文原文作为备选")
            try:
                en_transcript_data = YouTubeTranscriptApi.get_transcript(
                    video_id, 
                    languages=['en', 'en-US', 'en-GB']
                )
                
                # 转换为SRT格式
                srt_content = self.convert_to_srt(en_transcript_data)
                
                # 保存到临时文件
                temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='_en_fallback.srt', delete=False, encoding='utf-8')
                temp_file.write(srt_content)
                temp_file.close()
                
                logger.info(f"英文备选字幕已保存到: {temp_file.name}")
                return temp_file.name
                
            except Exception as fallback_e:
                logger.error(f"获取英文备选字幕也失败: {str(fallback_e)}")
                return None
    
    def get_transcript_with_translation(self, video_id: str, source_language: str = 'en', 
                                      target_language: str = 'zh-Hans') -> Optional[Tuple[str, str]]:
        """
        获取原文和翻译字幕
        
        Returns:
            Tuple[str, str]: (原文SRT路径, 翻译SRT路径)，失败返回None
        """
        try:
            # 获取原文字幕
            source_transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[source_language])
            
            # 尝试获取翻译字幕
            try:
                # 先尝试直接获取目标语言字幕
                target_transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[target_language])
            except:
                # 如果没有直接的目标语言字幕，尝试翻译
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                transcript = transcript_list.find_transcript([source_language])
                target_transcript = transcript.translate(target_language).fetch()
            
            # 转换为SRT格式
            source_srt = self.convert_to_srt(source_transcript)
            target_srt = self.convert_to_srt(target_transcript)
            
            # 保存到临时文件
            source_file = tempfile.NamedTemporaryFile(mode='w', suffix=f'_{source_language}.srt', delete=False, encoding='utf-8')
            source_file.write(source_srt)
            source_file.close()
            
            target_file = tempfile.NamedTemporaryFile(mode='w', suffix=f'_{target_language}.srt', delete=False, encoding='utf-8')
            target_file.write(target_srt)
            target_file.close()
            
            logger.info(f"双语字幕已保存: {source_file.name}, {target_file.name}")
            return (source_file.name, target_file.name)
            
        except Exception as e:
            logger.error(f"获取双语字幕失败 {video_id}: {str(e)}")
            return None

# 便捷函数
def extract_youtube_subtitles(url: str, language_codes: List[str] = None, 
                            prefer_manual: bool = True) -> Optional[str]:
    """
    从YouTube URL提取字幕的便捷函数
    
    Args:
        url: YouTube视频URL
        language_codes: 优先语言代码列表
        prefer_manual: 是否优先选择手动字幕
        
    Returns:
        str: SRT文件路径，失败返回None
    """
    extractor = SubtitleExtractor()
    video_id = extractor.extract_video_id(url)
    
    if not video_id:
        return None
    
    return extractor.download_transcript(video_id, language_codes, prefer_manual)

def check_youtube_subtitles(url: str) -> Dict:
    """
    检查YouTube视频可用字幕的便捷函数
    
    Args:
        url: YouTube视频URL
        
    Returns:
        Dict: 字幕信息字典
    """
    extractor = SubtitleExtractor()
    video_id = extractor.extract_video_id(url)
    
    if not video_id:
        return {'manual': [], 'generated': [], 'translatable_languages': []}
    
    return extractor.get_available_transcripts(video_id) 