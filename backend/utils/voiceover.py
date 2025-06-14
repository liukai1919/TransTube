# -*- coding: utf-8 -*-
"""Generate Chinese voice-over from English video audio."""

import logging
import tempfile
import os
import srt
from gtts import gTTS
from .transcriber import transcribe_to_srt
from .translator import translate_srt_to_zh

logger = logging.getLogger(__name__)


def english_audio_to_chinese_voice(video_path: str) -> str:
    """Convert English audio in a video to Chinese speech.

    Parameters
    ----------
    video_path: str
        Path to the original video file.

    Returns
    -------
    str
        Path to the generated Chinese speech audio file (mp3).
    """
    try:
        # Step 1: transcribe English speech
        en_srt = transcribe_to_srt(video_path, lang="en")

        # Step 2: translate subtitles to Chinese
        zh_srt = translate_srt_to_zh(en_srt)

        # Read Chinese subtitles and join text
        with open(zh_srt, "r", encoding="utf-8") as fp:
            subs = list(srt.parse(fp.read()))
        zh_text = " ".join(sub.content for sub in subs)

        # Step 3: generate Chinese speech using gTTS
        tts = gTTS(zh_text, lang="zh-cn")
        output_path = tempfile.mktemp(suffix=".mp3")
        tts.save(output_path)
        logger.info(f"中文语音已生成: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"生成中文语音失败: {e}")
        raise
