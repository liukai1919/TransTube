#!/usr/bin/env python3
import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from utils.transcriber import transcribe_to_srt

def main():
    if len(sys.argv) < 2:
        print("Usage: scripts/transcribe_with_whisperx.py <video_path> [lang]", file=sys.stderr)
        sys.exit(2)
    video = sys.argv[1]
    lang = sys.argv[2] if len(sys.argv) > 2 else 'en'

    print("WHISPERX_MODEL_SIZE=", os.getenv('WHISPERX_MODEL_SIZE'))
    print("WHISPER_TIMESTAMPED_MODEL_SIZE=", os.getenv('WHISPER_TIMESTAMPED_MODEL_SIZE'))
    print("TRANSCRIBE_FORCE_CPU=", os.getenv('TRANSCRIBE_FORCE_CPU'))

    out = transcribe_to_srt(video, lang)
    print("SRT:", out)

if __name__ == '__main__':
    main()

