# -*- coding: utf-8 -*-
"""
字幕翻译：默认用 OpenAI GPT-4o
"""
import os, openai, srt, tempfile
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 设置 OpenAI API 密钥
openai.api_key = os.getenv("OPENAI_API_KEY")

def translate_srt_to_zh(srt_path: str) -> str:
    """
    将 SRT 字幕文件翻译成中文
    """
    with open(srt_path, "r", encoding="utf-8") as fp:
        subs = list(srt.parse(fp.read()))
    # 将所有句子合并，减少 API 调用
    full_text = "\n".join([s.content for s in subs])
    prompt = ("你是专业字幕翻译，请保持时间顺序，把以下英文字幕翻译成简体中文，"
              "每行先显示英文原文，然后显示中文翻译，用'|'分隔：\n\n" + full_text)
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user", "content": prompt}],
        temperature=0.3)
    zh_lines = resp.choices[0].message.content.strip().splitlines()
    # 回填到字幕对象
    for sub, zh in zip(subs, zh_lines):
        # 分割英文和中文
        parts = zh.strip().split('|')
        if len(parts) == 2:
            # 保留英文原文，添加中文翻译
            sub.content = f"{parts[0].strip()}\n{parts[1].strip()}"
        else:
            # 如果分割失败，保持原文
            sub.content = zh.strip()
    zh_srt = srt.compose(subs)
    zh_path = tempfile.mktemp(suffix=".zh.srt")
    with open(zh_path, "w", encoding="utf-8") as fp:
        fp.write(zh_srt)
    return zh_path 