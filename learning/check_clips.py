"""切り出した英文クリップの文末が、欠けていないかを、手元の Whisper で全文検査する。

使い方: python3 check_clips.py ep115       （欠けた疑いのあるクリップを一覧表示）
        python3 check_clips.py ep115 --fix  （疑いのあるシーンのクリップを消す。そのあと build_lesson.py で作り直す）
"""
import json
import sys
from pathlib import Path

import hashlib

from clips import _clip_path, split_sentences, whisper_tail_ok
from words import CACHE_DIR, MODEL_NAME

DRIVE = Path.home() / "Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ/samurai-chronicles"
SC_EPISODES = Path(__file__).parent.parent / "episodes"


def deep(ep_id: str):
    """疑いのあるクリップが、本当に欠けているかを、シーン全体の Whisper の単語の時刻で確かめる。
    狙った文の最後の語が、クリップの終わりより「あと」に話されていれば、本当に欠けている（聞き違いではない）。"""
    import difflib
    import whisper
    from clips import _norm, _words, sentence_spans
    model = whisper.load_model("small")
    ep = json.loads((SC_EPISODES / f"{ep_id}.json").read_text(encoding="utf-8"))
    real = []
    for i, sc in enumerate(ep["scenes"], 1):
        wav = DRIVE / ep_id / "audio" / f"S{i:02d}.wav"
        sents = split_sentences(sc["narration"])
        clips = [_clip_path(wav, s) for s in sents]
        if not all(c.exists() for c in clips):
            continue
        flagged = [k for k, s in enumerate(sents) if not whisper_tail_ok(clips[k], s)]
        if not flagged:
            continue
        spans = sentence_spans(wav, clips)
        r = model.transcribe(str(wav), language="en", word_timestamps=True, fp16=False)
        W = [(_norm(w["word"]), float(w["start"]), float(w["end"])) for seg in r["segments"] for w in seg["words"] if _norm(w["word"])]
        for k in flagged:
            last = _words(sents[k])[-1]
            a, b = spans[k]
            # クリップの終わりの少し前〜後ろ2秒の範囲に、最後の語が、終わり以降に始まる形で聞こえるか
            late = [w for w in W if difflib.SequenceMatcher(None, last, w[0], autojunk=False).ratio() >= 0.8 and w[1] >= b - 0.05 and w[1] <= b + 2.0]
            inside = [w for w in W if difflib.SequenceMatcher(None, last, w[0], autojunk=False).ratio() >= 0.8 and a <= w[1] < b - 0.05]
            if late and not inside:
                real.append((i, k))
                print(f"  ❌ シーン{i} 文{k}: 最後の語「{last}」がクリップの終わり（{b:.2f}s）より後（{late[0][1]:.2f}s）に話されている: {sents[k][-50:]}")
            else:
                print(f"  （聞き違い）シーン{i} 文{k}: {sents[k][-40:]}")
    print(f"{ep_id}: 本当に欠けているクリップ {real or 'なし'}")


def main():
    if "--deep" in sys.argv:
        deep(sys.argv[1])
        return
    ep_id = sys.argv[1]
    fix = "--fix" in sys.argv
    ep = json.loads((SC_EPISODES / f"{ep_id}.json").read_text(encoding="utf-8"))
    bad_scenes = set()
    for i, sc in enumerate(ep["scenes"], 1):
        wav = DRIVE / ep_id / "audio" / f"S{i:02d}.wav"
        for k, sent in enumerate(split_sentences(sc["narration"])):
            clip = _clip_path(wav, sent)
            if not clip.exists():
                continue
            if not whisper_tail_ok(clip, sent):
                print(f"  ⚠️ シーン{i} 文{k}: 文末が欠けた疑い: {sent[-60:]}")
                bad_scenes.add(i)
    print(f"{ep_id}: 疑いのあるシーン {sorted(bad_scenes) or 'なし'}")
    if fix and bad_scenes:
        for i in bad_scenes:
            sc = ep["scenes"][i - 1]
            wav = DRIVE / ep_id / "audio" / f"S{i:02d}.wav"
            for sent in split_sentences(sc["narration"]):
                clip = _clip_path(wav, sent)
                clip.unlink(missing_ok=True)
                key = hashlib.sha1(f"{clip.name}|{sent}|{MODEL_NAME}|v4".encode()).hexdigest()[:16]
                (CACHE_DIR / f"words_{key}.json").unlink(missing_ok=True)   # 単語の時刻も、同じ名前のクリップで作り直す
        print("該当シーンのクリップを消しました。build_lesson.py を実行すると作り直します")


if __name__ == "__main__":
    main()
