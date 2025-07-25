import os
import torchaudio as ta

from chatterbox.tts import ChatterboxTTS

AUDIO_PROMPT_PATH = 'meta/baldurs_gate_narrator.wav' 

model = ChatterboxTTS.from_pretrained(device="cuda")

def generate_voice(text: str, dst_path: str):
    wav = model.generate(text, audio_prompt_path=AUDIO_PROMPT_PATH)
    ta.save(dst_path, wav, model.sr)
    return
