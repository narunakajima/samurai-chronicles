"""
gen_sc_channel_art.py — Samurai Chronicles チャンネルアート生成
YouTube推奨: 2560×1440px
"""
import os, sys, io
from pathlib import Path
from PIL import Image

TARGET_W, TARGET_H = 2560, 1440

API_KEY = os.environ.get("GEMINI_API_KEY_SC") or os.environ.get("GEMINI_API_KEY", "")
if not API_KEY:
    print("GEMINI_API_KEY が未設定です")
    sys.exit(1)

from google import genai
from google.genai import types

client = genai.Client(api_key=API_KEY)

prompt = (
    "YouTube channel banner, ultra-wide cinematic landscape, 16:9 format. "
    "Scene: A lone samurai warrior stands in the exact vertical and horizontal center of the frame. "
    "The samurai is small in frame — full body visible, taking up about 20% of image height. "
    "He wears dark battle armor (tosei gusoku), kabuto helmet with dramatic maedate crest. "
    "He stands still, facing slightly away, surveying a vast misty landscape. "
    "Setting: feudal Japan, dramatic mountain range at dusk or dawn, low mist over the valley. "
    "Ancient pine trees silhouetted on the sides. "
    "Sky: deep crimson and gold sunset/sunrise with dramatic clouds. "
    "Color palette: deep crimson red, dark gold, charcoal black, dramatic amber. "
    "Mood: epic, powerful, solitary, historical gravitas. "
    "COMPOSITION: vast open sky above, misty valley below, samurai centered in the middle band. "
    "Visual style: cinematic, dramatic, painterly with photographic realism, subtle film grain. "
    "No text, no watermarks, no logos. "
    "Ultra high quality."
)

print("生成中...")
response = client.models.generate_content(
    model="gemini-3.1-flash-image-preview",
    contents=prompt,
    config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
)

raw_bytes = None
for part in response.candidates[0].content.parts:
    if part.inline_data is not None:
        raw_bytes = part.inline_data.data
        break

if not raw_bytes:
    print("エラー: 画像データが取得できませんでした")
    sys.exit(1)

img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
src_w, src_h = img.size
print(f"  生成サイズ: {src_w}×{src_h}px")

# 16:9 クロップ → 2560×1440 リサイズ
src_ratio = src_w / src_h
target_ratio = TARGET_W / TARGET_H
if src_ratio > target_ratio:
    new_w = int(src_h * target_ratio)
    left = (src_w - new_w) // 2
    img = img.crop((left, 0, left + new_w, src_h))
else:
    new_h = int(src_w / target_ratio)
    top = (src_h - new_h) // 2
    img = img.crop((0, top, src_w, top + new_h))

img = img.resize((TARGET_W, TARGET_H), Image.LANCZOS)

out = Path.home() / "Desktop" / "sc_channel_art_2560x1440.png"
img.save(out, "PNG")
print(f"✓ 保存: {out}  ({TARGET_W}×{TARGET_H}px)")
