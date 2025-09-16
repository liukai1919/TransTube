#!/usr/bin/env python3
import os
import sys
import tempfile
import wave
import struct

def make_silent_wav(duration_s=0.5, sr=16000, path=None):
    nframes = int(duration_s * sr)
    sampwidth = 2  # 16-bit PCM
    nchannels = 1
    if path is None:
        f = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        path = f.name
        f.close()
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(nchannels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sr)
        silence = struct.pack('<' + 'h'*nframes, *([0]*nframes))
        wf.writeframes(silence)
    return path

def main():
    print('CUDA_VISIBLE_DEVICES =', os.getenv('CUDA_VISIBLE_DEVICES'))
    import torch
    print('Torch:', torch.__version__, 'CUDA:', torch.version.cuda, 'is_available:', torch.cuda.is_available())
    if not torch.cuda.is_available():
        print('CUDA not available in torch')
        sys.exit(2)

    print('Import whisper_timestamped...')
    import whisper_timestamped as whisper
    print('Loading tiny model on CUDA...')
    model = whisper.load_model('tiny', device='cuda')

    print('Generating silent wav and transcribing (sanity)...')
    wav_path = make_silent_wav(0.5)
    res = model.transcribe(wav_path, language='en', task='transcribe', fp16=True)
    print('Segments:', len(res.get('segments', [])))
    print('CUDA whisper tiny smoke test OK')

if __name__ == '__main__':
    main()

