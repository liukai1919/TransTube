# -*- coding: utf-8 -*-
"""
字幕翻译模块（Ollama 版本，极简实现）

依赖运行在本地或局域网的 **Ollama** 服务进行 Chat 交互，
保留 translate_srt_to_zh(srt_path, target_lang="zh") 及 translate_text 接口，
兼容 main.py / processor.py 现有调用。

工作流程：
1. 解析输入 SRT，提取所有行文本。
2. 按字符阈值 (默认 3500) 分批提交给 Ollama Chat API，每批返回逐行译文。
3. 将译文写回字幕条目并生成新的 SRT 文件。

环境变量：
OLLAMA_URL  (默认 "http://localhost:11434")
OLLAMA_MODEL (默认 "gpt-oss:20b")
OLLAMA_NUM_PREDICT (默认 1024)
TRANSLATE_BATCH_CHAR_LIMIT (默认 3500)
"""

from __future__ import annotations

import os
import logging
import tempfile
from typing import List

import requests  # 与本地 Ollama 通讯
import json
import srt       # python-srt 解析库
from pathlib import Path

# ------------------------- 环境变量 ------------------------- #
# Provider 选择：ollama | openai（OpenAI API 兼容）
TRANSLATE_PROVIDER = os.getenv("TRANSLATE_PROVIDER", "ollama").lower()
TRANSLATE_LINE_BY_LINE = os.getenv("TRANSLATE_LINE_BY_LINE", "0").lower() in {"1", "true", "yes"}

# Ollama（本地/兼容）
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:27b")
# 备用模型：当主模型输出为空或无中文时用于二次重试（可选）
OLLAMA_FALLBACK_MODEL = os.getenv("OLLAMA_FALLBACK_MODEL", "").strip()
NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "1024"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# OpenAI 兼容（如 OpenAI、DeepSeek 等）
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", os.getenv("OLLAMA_MODEL", "gpt-4o-mini"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1024"))

# 批量分片
BATCH_CHAR_LIMIT = int(os.getenv("TRANSLATE_BATCH_CHAR_LIMIT", "500"))

# 批量翻译定界符，模型几乎不会生成该串
DELIM = "<<<|||>>>"

# ------------------------- 日志 ------------------------- #
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
# ------------------------- 术语词表 ------------------------- #
TERMINOLOGY_FILE = str(Path(__file__).resolve().parent.parent / "config" / "terminology.txt")

def _load_keep_terms() -> list:
    terms: list[str] = []
    try:
        with open(TERMINOLOGY_FILE, "r", encoding="utf-8") as fp:
            for ln in fp:
                t = ln.strip()
                if not t or t.startswith("#"):
                    continue
                terms.append(t)
    except Exception:
        pass
    return terms

KEEP_TERMS = _load_keep_terms()

# ------------------------- LLM 请求工具 ------------------------- #

def _chat_with_ollama(system_prompt: str, user_prompt: str, *, model: str | None = None) -> str:
    """与 Ollama 通讯，优先使用 /api/chat；若 404/不支持则回退 /api/generate。"""
    model_name = model or OLLAMA_MODEL
    chat_url = f"{OLLAMA_URL}/api/chat"
    chat_payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "options": {"temperature": 0.2, "num_predict": NUM_PREDICT},
        "stream": False,
    }

    try:
        resp = requests.post(chat_url, json=chat_payload, timeout=300)
        if resp.status_code == 404:
            raise RuntimeError("CHAT_NOT_SUPPORTED")
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("message", {}) or {}).get("content", "").strip()
        if content:
            return content
        # 若无内容，尝试回退 generate
        raise RuntimeError("EMPTY_CHAT_CONTENT")
    except Exception as e:
        # 回退到 /api/generate（旧版本 Ollama 或不支持 chat）
        if isinstance(e, RuntimeError) and str(e) in {"CHAT_NOT_SUPPORTED", "EMPTY_CHAT_CONTENT"} or (
            hasattr(e, "response") and getattr(e.response, "status_code", None) == 404
        ):
            gen_url = f"{OLLAMA_URL}/api/generate"
            # 将 system + user 拼成单条 prompt
            prompt = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_prompt}"
            gen_payload = {
                "model": model_name,
                "prompt": prompt,
                "options": {"temperature": 0.2, "num_predict": NUM_PREDICT},
                "stream": False,
            }
            r2 = requests.post(gen_url, json=gen_payload, timeout=300)
            r2.raise_for_status()
            j2 = r2.json()
            content = (j2.get("response") or "").strip()
            return content
        logger.error("Ollama 请求失败: %s", str(e))
        raise


def _chat_with_openai(system_prompt: str, user_prompt: str) -> str:
    """与 OpenAI 兼容 Chat API 通讯，返回 assistant content。"""
    url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": OPENAI_MAX_TOKENS,
        "stream": False,
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        print(f"🔍 最终拼接的 content: {content[:200]}...")
        return content
    except Exception as e:
        logger.error("OpenAI 兼容 API 请求失败: %s", e)
        raise

# ------------------------- 内部算法 ------------------------- #

def _split_into_batches(lines: List[str], char_limit: int = BATCH_CHAR_LIMIT) -> List[List[str]]:
    """按总字符数将字幕行切分为多批。"""
    batches: List[List[str]] = []
    current: List[str] = []
    cur_len = 0
    for line in lines:  # type: ignore  
        add = len(line) + 1
        if current and cur_len + add > char_limit:
            batches.append(current)
            current = [line]
            cur_len = add
        else:
            current.append(line)
            cur_len += add
    if current:
        batches.append(current)
    return batches


def validate_single_translation(original: str, translated: str, target_lang: str) -> str:
    """
    验证单个翻译结果的质量
    
    Args:
        original: 原文
        translated: 翻译结果
        target_lang: 目标语言
    
    Returns:
        有效的翻译结果或原文（如果翻译质量不佳）
    """
    def _has_chinese(text: str) -> bool:
        return any('\u4e00' <= ch <= '\u9fff' for ch in text)
    
    # 如果翻译结果为空，返回原文
    if not translated or not translated.strip():
        return original
    
    # 如果目标语言是中文
    if target_lang.startswith("zh"):
        # 检查翻译结果是否包含中文
        if not _has_chinese(translated):
            return original
        
        # 检查是否只是重复了原文
        if translated.strip().lower() == original.strip().lower():
            return original
        
        # 检查是否包含明显的翻译失败标志
        failure_indicators = [
            "i cannot", "i can't", "sorry", "unable to", 
            "无法翻译", "翻译失败", "error", "failed"
        ]
        if any(indicator in translated.lower() for indicator in failure_indicators):
            return original
    
    # 翻译结果通过验证
    return translated


def _translate_batch(batch: List[str], target_lang: str) -> List[str]:
    """调用 Ollama 翻译批次字幕，返回逐行译文。"""
    
    def _has_chinese(text: str) -> bool:
        return any('\u4e00' <= ch <= '\u9fff' for ch in text)
    
    # 检查是否包含英文内容需要翻译
    has_english = any(any(c.isalpha() and ord(c) < 128 for c in text) for text in batch)
    if not has_english:
        logger.info("检测到没有英文内容需要翻译，保持原样")
        return batch
    
    joined = f" {DELIM} ".join(batch)
    keep_terms_clause = (" Keep these terms exactly as-is: " + " | ".join(KEEP_TERMS) + ".") if KEEP_TERMS else ""
    # 调整提示：仅严格保留术语表与代码/路径/缩写，避免整句被误判为需保留
    system_prompt = (
        "You are a professional subtitle translator. "
        f"Translate each segment into {target_lang}. Segments are separated by the token {DELIM}. "
        "Translate ONLY the natural-language parts; translate around preserved tokens. "
        "STRICTLY KEEP the following AS-IS: entries from the provided terminology list, inline code, file names/paths, "
        "CLI commands, and common acronyms (e.g., API, SDK, GPU). Preserve numbers and units. "
        "Do NOT add brackets or explanations; do NOT transliterate; preserve casing." + keep_terms_clause + " "
        f"Return EXACTLY the same number of segments, in the same order, separated by {DELIM} and nothing else."
    )

    print(f"🔍 发送给 Ollama:")
    print(f"   system: {system_prompt}")
    print(f"   user: {joined[:300]}...")
    print(f"   请求长度: {len(joined)} 字符")
    
    try:
        # 参考 KlicStudio：支持不同 LLM Provider
        if TRANSLATE_PROVIDER == "openai" and OPENAI_API_KEY:
            content = _chat_with_openai(system_prompt, joined)
        else:
            content = _chat_with_ollama(system_prompt, joined)
        print(f"🔍 Ollama 返回 content: {content}")
        # 拆分译文（不丢弃空段，尽量保持与输入对齐）
        translated_lines = [seg.strip() for seg in content.split(DELIM)]
        print(f"🔍 解析后译文 ({len(translated_lines)} 条): {translated_lines[:3]}...")

        # 若目标中文但译文不含中文，视为失败
        if target_lang.startswith("zh") and not any(_has_chinese(t) for t in translated_lines):
            logger.warning("Ollama 返回内容不含中文，重试一次…")
            # 再次尝试，附带更强指令
            retry_prompt = system_prompt + "\n注意：务必输出简体中文，仅返回翻译文本。"
            if TRANSLATE_PROVIDER == "openai" and OPENAI_API_KEY:
                content = _chat_with_openai(retry_prompt, joined)
            else:
                content = _chat_with_ollama(retry_prompt, joined)
            translated_lines = [seg.strip() for seg in content.split(DELIM)]

        # 对齐段数：不直接用原文填充，而是先占位为空，后续逐行重试
        if len(translated_lines) != len(batch):
            logger.warning("译文行数与输入不一致 (in=%d, out=%d)，先对齐长度并标记需重试。", len(batch), len(translated_lines))
            if len(translated_lines) < len(batch):
                translated_lines = translated_lines + [""] * (len(batch) - len(translated_lines))
            else:
                translated_lines = translated_lines[: len(batch)]

        # 逐项校验：对不含中文/等于原文/为空的条目进行行级重试（含备用模型）
        def _is_valid_cn_item(src: str, hyp: str) -> bool:
            if not hyp or not hyp.strip():
                return False
            if hyp.strip().lower() == src.strip().lower():
                return False
            return _has_chinese(hyp)

        fixed_lines: list[str] = []
        for src_text, hyp_text in zip(batch, translated_lines):
            if target_lang.startswith("zh") and not _is_valid_cn_item(src_text, hyp_text):
                single_prompt = (
                    "You are a professional subtitle translator. "
                    f"Translate the following line into {target_lang}. Translate ONLY the natural-language parts; "
                    "keep terminology/code/paths/acronyms as-is. Return ONLY the translation text."
                )
                # 第一次单行重试
                try:
                    ans = _chat_with_openai(single_prompt, src_text) if (TRANSLATE_PROVIDER == "openai" and OPENAI_API_KEY) else _chat_with_ollama(single_prompt, src_text)
                    ans = (ans or "").strip()
                except Exception:
                    ans = ""

                # 若仍无效，附加更强限制中文提示
                if not _is_valid_cn_item(src_text, ans):
                    try:
                        ans = _chat_with_openai(single_prompt + "\n务必输出简体中文，仅返回翻译文本。", src_text) if (TRANSLATE_PROVIDER == "openai" and OPENAI_API_KEY) else _chat_with_ollama(single_prompt + "\n务必输出简体中文，仅返回翻译文本。", src_text)
                        ans = (ans or "").strip()
                    except Exception:
                        ans = ""

                # 若还不行，尝试备用模型
                if not _is_valid_cn_item(src_text, ans) and OLLAMA_FALLBACK_MODEL and TRANSLATE_PROVIDER != "openai":
                    try:
                        ans = _chat_with_ollama(single_prompt, src_text, model=OLLAMA_FALLBACK_MODEL)
                        ans = (ans or "").strip()
                    except Exception:
                        ans = ""

                fixed_lines.append(ans if _is_valid_cn_item(src_text, ans) else src_text)
            else:
                fixed_lines.append(hyp_text)
        translated_lines = fixed_lines

        # 验证每个翻译结果的质量，对翻译失败的保留原文
        validated_translations = []
        for i, (original, translated) in enumerate(zip(batch, translated_lines)):
            validated_translation = validate_single_translation(original, translated, target_lang)
            validated_translations.append(validated_translation)
            
            if validated_translation == original:
                logger.debug(f"翻译条目 {i+1} 质量不佳，保留原文: {original[:30]}...")

        return validated_translations
    except Exception as e:
        logger.error("翻译批次失败: %s", e)
        raise Exception(f"翻译批次失败: {e}")

# ------------------------- 对外主接口 ------------------------- #

def translate_srt_to_zh(srt_path: str, target_lang: str = "zh", **kwargs) -> str:
    """翻译 SRT 文件，返回翻译后临时文件路径。"""
    logger.info("开始翻译字幕 %s -> %s (Ollama)", srt_path, target_lang)
        
    # 读取并解析原字幕
    with open(srt_path, "r", encoding="utf-8") as fp:
        subs = list(srt.parse(fp.read()))
            
    if TRANSLATE_LINE_BY_LINE:
        logger.info("启用逐句翻译模式（不分批）…")
        translated: List[str] = []
        keep_terms_clause = (" Keep these terms exactly as-is: " + " | ".join(KEEP_TERMS) + ".") if KEEP_TERMS else ""
        for i, sub in enumerate(subs, 1):
            line = sub.content.replace("\n", " ")
            system_prompt = (
                "You are a professional subtitle translator. "
                f"Translate the following line into {target_lang}. Translate ONLY the natural-language parts; "
                "STRICTLY KEEP entries from the terminology list, inline code, file names/paths, CLI commands, and common acronyms AS-IS. "
                "Preserve numbers and units. Do NOT add brackets or explanations; do NOT transliterate; preserve casing." + keep_terms_clause + " "
                "Return ONLY the translation text."
            )
            try:
                ans = _chat_with_openai(system_prompt, line) if (TRANSLATE_PROVIDER == "openai" and OPENAI_API_KEY) else _chat_with_ollama(system_prompt, line)
                ans = (ans or "").strip()
                if target_lang.startswith("zh") and not any('\u4e00' <= ch <= '\u9fff' for ch in ans):
                    # 加强一次重试
                    try:
                        ans2 = _chat_with_openai(system_prompt + "\n务必输出简体中文，仅返回翻译文本。", line) if (TRANSLATE_PROVIDER == "openai" and OPENAI_API_KEY) else _chat_with_ollama(system_prompt + "\n务必输出简体中文，仅返回翻译文本。", line)
                        ans2 = (ans2 or "").strip()
                        if any('\u4e00' <= ch <= '\u9fff' for ch in ans2):
                            ans = ans2
                        elif OLLAMA_FALLBACK_MODEL and TRANSLATE_PROVIDER != "openai":
                            ans3 = _chat_with_ollama(system_prompt, line, model=OLLAMA_FALLBACK_MODEL)
                            ans3 = (ans3 or "").strip()
                            ans = ans3 if any('\u4e00' <= ch <= '\u9fff' for ch in ans3) else line
                        else:
                            ans = line
                    except Exception:
                        ans = line
            except Exception:
                ans = line
            translated.append(validate_single_translation(line, ans, target_lang))
        logger.info("逐句翻译完成：%d 行", len(translated))
    else:
        texts = [s.content.replace("\n", " ") for s in subs]
        batches = _split_into_batches(texts)
        logger.info("共 %d 行字幕，拆为 %d 批", len(texts), len(batches))

        translated = []
        done = 0
        for idx, batch in enumerate(batches, 1):
            logger.info("翻译批次 %d/%d (≈%d 行)…", idx, len(batches), len(batch))
            translated.extend(_translate_batch(batch, target_lang))
            done += len(batch)
            logger.info("已翻译 %d/%d 行", done, len(texts))

    if len(translated) != len(subs):
        logger.error("翻译后行数不匹配，翻译失败: %s", srt_path)
        raise Exception(f"翻译失败：期望 {len(subs)} 行，实际得到 {len(translated)} 行")

    for sub, new_txt in zip(subs, translated):
        sub.content = new_txt

    zh_content = srt.compose(subs)
    with tempfile.NamedTemporaryFile("w", suffix=".zh.srt", delete=False, encoding="utf-8") as fp:
        fp.write(zh_content)
        out_path = fp.name

    logger.info("字幕翻译完成：%s", out_path)
    return out_path


def translate_srt_to_bilingual(en_srt_path: str, target_lang: str = "zh", **kwargs) -> str:
    """
    翻译SRT文件并生成双语字幕
    
    Args:
        en_srt_path: 英文字幕文件路径
        target_lang: 目标语言
    
    Returns:
        双语字幕文件路径
    """
    logger.info("开始生成双语字幕 %s -> %s (Ollama)", en_srt_path, target_lang)
    
    # 先进行正常翻译
    zh_srt_path = translate_srt_to_zh(en_srt_path, target_lang, **kwargs)
    
    # 导入双语字幕合并模块
    try:
        from .bilingual_subtitle_merger import create_bilingual_subtitles_from_translation
        
        # 生成双语字幕
        bilingual_srt_path = create_bilingual_subtitles_from_translation(
            en_srt_path, zh_srt_path
        )
        
        logger.info("双语字幕生成完成: %s", bilingual_srt_path)
        return bilingual_srt_path
        
    except ImportError as e:
        logger.error("无法导入双语字幕合并模块: %s", e)
        # 如果导入失败，返回中文字幕
        return zh_srt_path
    except Exception as e:
        logger.error("生成双语字幕失败: %s", e)
        # 如果生成失败，返回中文字幕
        return zh_srt_path


def translate_text(text: str, target_lang: str = "zh") -> str:
    """翻译任意文本的便捷方法。"""
    return _translate_batch([text], target_lang)[0]


# 向后兼容 main.py 早期接口 -----------------------------------------------------

def translate_video_title(title: str, target_lang: str = "zh") -> str:
    """旧版接口包装：翻译视频标题。"""
    return translate_text(title, target_lang)
