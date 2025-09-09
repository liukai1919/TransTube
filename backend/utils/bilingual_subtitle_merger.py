# -*- coding: utf-8 -*-
"""
双语字幕合并工具
将英文字幕和中文字幕合并为一个双语显示的SRT文件
"""
import os
import tempfile
import logging
from typing import Optional, List
import srt
from datetime import timedelta

# 行内换行修复与折叠工具（同目录下）
try:
    from .subtitle_fixer import merge_inline_linebreaks, collapse_linebreaks
except Exception:
    # 兜底：在作为独立脚本运行时支持绝对导入
    from backend.utils.subtitle_fixer import merge_inline_linebreaks, collapse_linebreaks

logger = logging.getLogger(__name__)

def merge_bilingual_subtitles(en_srt_path: str, zh_srt_path: str, output_path: str = None) -> str:
    """
    合并英文和中文字幕为双语字幕文件
    
    Args:
        en_srt_path: 英文字幕文件路径
        zh_srt_path: 中文字幕文件路径
        output_path: 输出文件路径，如果为None则创建临时文件
    
    Returns:
        合并后的双语字幕文件路径
    """
    try:
        # 读取英文字幕
        with open(en_srt_path, 'r', encoding='utf-8') as f:
            en_subs = list(srt.parse(f.read()))
        
        # 读取中文字幕
        with open(zh_srt_path, 'r', encoding='utf-8') as f:
            zh_subs = list(srt.parse(f.read()))
        
        logger.info(f"读取字幕: 英文 {len(en_subs)} 条, 中文 {len(zh_subs)} 条")
        
        # 合并字幕
        bilingual_subs = []
        max_len = max(len(en_subs), len(zh_subs))
        
        for i in range(max_len):
            # 获取当前时间段的字幕
            en_sub = en_subs[i] if i < len(en_subs) else None
            zh_sub = zh_subs[i] if i < len(zh_subs) else None
            
            # 确定时间范围（优先使用英文字幕的时间，如果没有则使用中文的）
            if en_sub:
                start_time = en_sub.start
                end_time = en_sub.end
                en_text = en_sub.content.strip()
            elif zh_sub:
                start_time = zh_sub.start
                end_time = zh_sub.end
                en_text = ""
            else:
                continue
            
            # 获取中文文本
            if zh_sub:
                zh_text = zh_sub.content.strip()
            else:
                zh_text = ""
            
            # 构建双语字幕内容
            bilingual_content = create_bilingual_content(en_text, zh_text)
            
            # 创建双语字幕条目
            bilingual_sub = srt.Subtitle(
                index=i + 1,
                start=start_time,
                end=end_time,
                content=bilingual_content
            )
            bilingual_subs.append(bilingual_sub)
        
        # 生成输出文件路径
        if output_path is None:
            output_file = tempfile.NamedTemporaryFile(mode='w', suffix='_bilingual.srt', delete=False, encoding='utf-8')
            output_path = output_file.name
            output_file.close()
        
        # 写入合并后的字幕
        bilingual_content = srt.compose(bilingual_subs)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(bilingual_content)
        
        logger.info(f"双语字幕已保存到: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"合并双语字幕失败: {str(e)}")
        raise Exception(f"合并双语字幕失败: {str(e)}")

def create_bilingual_content(en_text: str, zh_text: str) -> str:
    """
    创建双语字幕内容
    
    Args:
        en_text: 英文文本
        zh_text: 中文文本
    
    Returns:
        格式化的双语字幕内容
    """
    # 清理与规范化行内换行：
    # - 英文与中文都应当单行显示，以避免出现竖排或单词被拆行的问题
    # - 英文先合并行内换行（单词被\n拆分的情况），再压缩为单行
    # - 中文同样压缩为单行，避免多行导致遮挡
    en_text = en_text.strip() if en_text else ""
    zh_text = zh_text.strip() if zh_text else ""

    if en_text:
        en_text = merge_inline_linebreaks(en_text)
        en_text = collapse_linebreaks(en_text, max_lines=1)
    if zh_text:
        zh_text = merge_inline_linebreaks(zh_text)
        zh_text = collapse_linebreaks(zh_text, max_lines=1)
    
    # 如果没有中文翻译或翻译失败，使用英文原文
    if not zh_text or zh_text == en_text:
        if en_text:
            return f"{en_text}\n{en_text}"  # 显示两行英文
        else:
            return ""
    
    # 如果没有英文，只显示中文
    if not en_text:
        return zh_text
    
    # 正常情况：英文在上，中文在下
    return f"{en_text}\n{zh_text}"

def create_bilingual_subtitles_from_translation(en_srt_path: str, translated_srt_path: str, 
                                              output_path: str = None) -> str:
    """
    从原文和翻译结果创建双语字幕
    处理翻译失败的情况，保留英文原文
    
    Args:
        en_srt_path: 英文原文字幕路径
        translated_srt_path: 翻译后的字幕路径
        output_path: 输出路径
    
    Returns:
        双语字幕文件路径
    """
    try:
        # 读取原文字幕
        with open(en_srt_path, 'r', encoding='utf-8') as f:
            en_subs = list(srt.parse(f.read()))
        
        # 读取翻译字幕
        with open(translated_srt_path, 'r', encoding='utf-8') as f:
            zh_subs = list(srt.parse(f.read()))
        
        logger.info(f"处理双语字幕: 英文 {len(en_subs)} 条, 翻译 {len(zh_subs)} 条")
        
        # 创建双语字幕
        bilingual_subs = []
        
        for i, en_sub in enumerate(en_subs):
            zh_sub = zh_subs[i] if i < len(zh_subs) else None
            
            en_text = en_sub.content.strip()
            zh_text = zh_sub.content.strip() if zh_sub else ""
            
            # 检查翻译质量
            zh_text = validate_translation(en_text, zh_text)
            
            # 创建双语内容
            bilingual_content = create_bilingual_content(en_text, zh_text)
            
            bilingual_sub = srt.Subtitle(
                index=i + 1,
                start=en_sub.start,
                end=en_sub.end,
                content=bilingual_content
            )
            bilingual_subs.append(bilingual_sub)
        
        # 生成输出文件
        if output_path is None:
            output_file = tempfile.NamedTemporaryFile(mode='w', suffix='_bilingual.srt', delete=False, encoding='utf-8')
            output_path = output_file.name
            output_file.close()
        
        # 保存双语字幕
        bilingual_content = srt.compose(bilingual_subs)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(bilingual_content)
        
        logger.info(f"双语字幕已创建: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"创建双语字幕失败: {str(e)}")
        raise Exception(f"创建双语字幕失败: {str(e)}")

def validate_translation(en_text: str, zh_text: str) -> str:
    """
    验证翻译质量，如果翻译无效则返回英文原文
    
    Args:
        en_text: 英文原文
        zh_text: 中文翻译
    
    Returns:
        有效的中文翻译或英文原文
    """
    if not zh_text:
        return en_text
    
    # 检查是否包含中文字符
    has_chinese = any('\u4e00' <= ch <= '\u9fff' for ch in zh_text)
    
    # 如果翻译结果没有中文，可能翻译失败，使用英文原文
    if not has_chinese:
        logger.warning(f"翻译可能失败，使用英文原文: {en_text[:50]}...")
        return en_text
    
    # 检查是否只是重复了英文
    if zh_text.strip().lower() == en_text.strip().lower():
        logger.warning(f"翻译结果与原文相同，使用英文原文: {en_text[:50]}...")
        return en_text
    
    return zh_text

def adjust_subtitle_timing(srt_path: str, time_offset: float = 0.0) -> str:
    """
    调整字幕时间偏移
    
    Args:
        srt_path: 字幕文件路径
        time_offset: 时间偏移（秒）
    
    Returns:
        调整后的字幕文件路径
    """
    try:
        with open(srt_path, 'r', encoding='utf-8') as f:
            subs = list(srt.parse(f.read()))
        
        # 调整时间
        offset_delta = timedelta(seconds=time_offset)
        for sub in subs:
            sub.start += offset_delta
            sub.end += offset_delta
        
        # 保存调整后的字幕
        adjusted_content = srt.compose(subs)
        output_file = tempfile.NamedTemporaryFile(mode='w', suffix='_adjusted.srt', delete=False, encoding='utf-8')
        output_file.write(adjusted_content)
        output_file.close()
        
        logger.info(f"字幕时间已调整: {time_offset}秒, 保存到: {output_file.name}")
        return output_file.name
        
    except Exception as e:
        logger.error(f"调整字幕时间失败: {str(e)}")
        return srt_path