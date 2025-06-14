# -*- coding: utf-8 -*-
"""
翻译路由模块
处理视频字幕翻译请求
"""
import os
import shutil
import tempfile
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict
import asyncio

from ..utils.translator import translate_srt_to_zh
from ..utils.subtitle_fixer import fix_blank_terminology_in_srt, analyze_blank_patterns
from ..config.translation_config import get_translation_config, detect_video_domain

# ... existing code ...

class TranslateRequest(BaseModel):
    url: str
    target_lang: str = "zh"
    use_smart_split: bool = True
    use_three_stage: bool = True
    extract_terms: bool = True
    custom_terminology_path: Optional[str] = None
    enable_web_search: bool = False
    auto_fix_blanks: bool = True  # 新增：自动修复空白
    video_title: Optional[str] = None
    video_description: Optional[str] = None

# ... existing code ...

@router.post("/translate")
async def translate_video(request: TranslateRequest, background_tasks: BackgroundTasks):
    """
    翻译视频字幕
    支持智能术语处理和空白修复
    """
    try:
        # 检测视频领域并获取相应配置
        domain = "general"
        if request.video_title or request.video_description:
            domain = detect_video_domain(
                request.video_title or "", 
                request.video_description or ""
            )
        
        config = get_translation_config(domain)
        logger.info(f"检测到视频领域: {domain}")
        
        # 下载并提取字幕的逻辑...
        # (这里省略现有的下载和提取逻辑)
        
        # 假设我们已经有了英文字幕文件路径
        english_srt_path = "path/to/english.srt"  # 这里应该是实际的路径
        
        # 执行翻译
        logger.info("开始翻译字幕...")
        zh_srt_path = translate_srt_to_zh(
            english_srt_path,
            use_smart_split=request.use_smart_split or config.translation.use_smart_split,
            use_three_stage=request.use_three_stage or config.translation.use_three_stage,
            extract_terms=request.extract_terms or config.terminology.auto_extract_terms,
            custom_terminology_path=request.custom_terminology_path or config.terminology.custom_terminology_path,
            enable_web_search=request.enable_web_search or config.terminology.enable_web_search
        )
        
        # 自动修复空白专有名词（如果启用）
        if request.auto_fix_blanks:
            logger.info("开始修复空白专有名词...")
            
            try:
                # 分析空白模式
                blank_patterns = analyze_blank_patterns(zh_srt_path)
                if blank_patterns:
                    logger.info(f"发现 {len(blank_patterns)} 种空白模式，开始修复...")
                    
                    # 执行修复
                    fixed_srt_path = fix_blank_terminology_in_srt(zh_srt_path)
                    
                    # 如果修复成功，使用修复后的文件
                    if fixed_srt_path != zh_srt_path:
                        zh_srt_path = fixed_srt_path
                        logger.info("空白修复完成")
                    else:
                        logger.info("未发现需要修复的空白模式")
                else:
                    logger.info("未发现空白模式")
                    
            except Exception as fix_error:
                logger.error(f"空白修复失败: {str(fix_error)}")
                # 修复失败不影响主流程，继续使用原翻译文件
        
        # 返回结果
        return {
            "success": True,
            "message": "翻译完成",
            "data": {
                "chinese_srt_path": zh_srt_path,
                "domain_detected": domain,
                "auto_fixed": request.auto_fix_blanks
            }
        }
        
    except Exception as e:
        logger.error(f"翻译失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"翻译失败: {str(e)}")

@router.post("/fix-subtitles")
async def fix_subtitle_blanks(srt_path: str):
    """
    单独的字幕修复端点
    用于修复已翻译字幕中的空白专有名词问题
    """
    try:
        if not os.path.exists(srt_path):
            raise HTTPException(status_code=404, detail="字幕文件不存在")
        
        logger.info(f"开始分析和修复字幕文件: {srt_path}")
        
        # 分析空白模式
        blank_patterns = analyze_blank_patterns(srt_path)
        
        # 执行修复
        fixed_srt_path = fix_blank_terminology_in_srt(srt_path)
        
        return {
            "success": True,
            "message": "修复完成",
            "data": {
                "original_path": srt_path,
                "fixed_path": fixed_srt_path,
                "blank_patterns_found": len(blank_patterns),
                "patterns": dict(list(blank_patterns.items())[:10])  # 返回前10个最常见的模式
            }
        }
        
    except Exception as e:
        logger.error(f"字幕修复失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"字幕修复失败: {str(e)}")

@router.get("/analyze-blanks")
async def analyze_subtitle_blanks(srt_path: str):
    """
    分析字幕中的空白模式
    不进行修复，仅分析和报告
    """
    try:
        if not os.path.exists(srt_path):
            raise HTTPException(status_code=404, detail="字幕文件不存在")
        
        logger.info(f"分析字幕空白模式: {srt_path}")
        
        # 分析空白模式
        blank_patterns = analyze_blank_patterns(srt_path)
        
        # 建议新术语
        from ..utils.subtitle_fixer import suggest_terminology_additions
        suggestions = suggest_terminology_additions(srt_path)
        
        return {
            "success": True,
            "message": "分析完成",
            "data": {
                "file_path": srt_path,
                "blank_patterns_count": len(blank_patterns),
                "patterns": blank_patterns,
                "terminology_suggestions": suggestions
            }
        }
        
    except Exception as e:
        logger.error(f"分析失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")

# ... existing code ... 