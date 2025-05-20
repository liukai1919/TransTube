# -*- coding: utf-8 -*-
"""
使用 Whisper Timestamped 为没有原字幕的视频生成 SRT 文件
"""
import os
import whisper_timestamped as whisper
import srt
import datetime
import tempfile

# 强制使用 CPU
os.environ["CUDA_VISIBLE_DEVICES"] = ""

def transcribe_to_srt(video_path: str, lang="en") -> str:
    # 明确指定使用 CPU
    model = whisper.load_model("base", device="cpu")
    result = whisper.transcribe(model, audio=video_path, language=lang)
    segments = result["segments"]

    subs = []
    for seg in segments:
        start = datetime.timedelta(seconds=seg["start"])
        end   = datetime.timedelta(seconds=seg["end"])
        subs.append(srt.Subtitle(index=len(subs)+1,
                                 start=start, end=end,
                                 content=seg["text"].strip()))
    srt_str = srt.compose(subs)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".srt") as tmp:
        tmp.write(srt_str.encode("utf-8"))
        srt_path = tmp.name
    return srt_path
