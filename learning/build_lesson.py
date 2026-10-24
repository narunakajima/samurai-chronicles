"""SC エピソードから、散歩で聴く英語耳トレーニング音声（1本・約45分）を組み立てる。

構成: 日本語の導入 → 20シーン（日本語の見どころ説明 → 1文ずつ「合図の音 → 日本語の訳 → 英語の文」）
      → 通し（英語のみ）→ 締め

使い方: python3 build_lesson.py ep106
台本は lessons/{episode_id}.json。英語音声は SC の Drive フォルダ（ep{NNN}/audio/S01.wav〜）をそのまま使う。
"""
import array
import json
import shutil
import subprocess
import sys
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from audio_check import check_japanese
from clips import PAD, cut_scene_sentences, sentence_spans, split_sentences
from words import word_times
from tts_ja import tts

BASE_DIR = Path(__file__).parent
SC_EPISODES = BASE_DIR.parent / "episodes"
DRIVE = Path.home() / "Library/CloudStorage/GoogleDrive-naru.nakajima@gmail.com/マイドライブ"
SC_DRIVE = DRIVE / "samurai-chronicles"
SAMPLE_RATE = 24000
WORKERS = 4
JA_QA_RETRIES = 3

# 間（秒）
GAP_AFTER_CUE = 0.8
GAP_AFTER_EN = 1.2
GAP_JA_TO_CLIP = 0.4
GAP_CHIME = 0.25  # 合図の音のあと、日本語の訳が始まるまでの間
CHIME = BASE_DIR / "chime.wav"  # 日本語の訳の前に鳴らす合図の音
GAP_AFTER_CLIP = 1.0
GAP_SCENE_END = 1.5
GAP_INTRO_PARA = 0.8
GAP_FULL_SCENE = 1.0
GAP_SECTION = 2.0
GAP_BEFORE_OP = 0.8  # シーンの最後の文から、ワンポイントまでの間
GAP_OP_TO_EN = 0.6   # ワンポイントの解説から、その英文をもう一度流すまでの間
GAP_OPENING = 3.0  # 冒頭の間。動画で Tokio が転送エフェクトで現れ終わってから話し始めるため
FADE_SAMPLES = 240  # 10ms
JA_TEMPO = 1.1  # 日本語の話す速さ（音の高さは変えずに速める）。英語に比べて遅く感じるとの指摘で 1.0→1.1（2026-10-22）
LOUDNESS = "loudnorm=I=-16:TP=-1.5:LRA=11"


def run(cmd: list[str]):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        sys.exit(1)


def fade_edges(pcm: bytes, n: int = FADE_SAMPLES) -> bytes:
    """音声の両端に短いフェードをかけて、つなぎ目の「プチッ」というノイズを防ぐ。"""
    a = array.array("h")
    a.frombytes(pcm)
    n = min(n, len(a) // 2)
    for i in range(n):
        g = i / n
        a[i] = int(a[i] * g)
        a[len(a) - 1 - i] = int(a[len(a) - 1 - i] * g)
    return a.tobytes()


def ja_tempo(path: Path) -> Path:
    """日本語の音声を JA_TEMPO 倍の速さにした版を返す（cache に保存して使い回す）。"""
    if JA_TEMPO == 1.0:
        return path
    out = path.with_name(f"{path.stem}_t{int(round(JA_TEMPO * 100))}.wav")
    if not out.exists():
        run(["ffmpeg", "-y", "-i", str(path), "-af", f"atempo={JA_TEMPO}",
             "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(out)])
    return out


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def ja_audio(text: str) -> Path:
    """日本語を音声化し、台本どおりに読めているかを Gemini で確かめる（だめなら作り直す）。"""
    for attempt in range(1, JA_QA_RETRIES + 1):
        path = tts(text)
        qa_file = path.with_suffix(".qa.json")
        if qa_file.exists():
            qa = json.loads(qa_file.read_text())
        else:
            qa = check_japanese(path, text)
            qa_file.write_text(json.dumps(qa, ensure_ascii=False))
        if qa.get("ok"):
            return path
        print(f"  ⚠️ 読みの問題（{attempt}回目）: {'; '.join(qa.get('issues', []))} — {text[:20]}…")
        if attempt < JA_QA_RETRIES:
            path.unlink()
            qa_file.unlink()
    print(f"  ⚠️ {JA_QA_RETRIES}回作っても指摘が残ったため、最後のテイクを使います: {text[:30]}…")
    return path


def mix_full_bgm(narr_wav: Path, out_wav: Path, episode: dict, ep_id: str, events: list) -> list:
    """「通し」（英語だけの区間）に、SC 本編と同じ BGM を重ねる（2026-10-24 ユーザー指示）。
    曲の構成・音量・曲間のクロスフェードは sc_video_gen と同じ。通しの外（導入・各シーン・締め）には入れない。
    BGM が見つからないときは、ナレーションだけの音声をそのまま使う。戻り値は、説明欄に載せる CC BY のクレジット行。"""
    sys.path.insert(0, str(SC_EPISODES.parent))
    import sc_video_gen as vg
    full = [e for e in events if e["kind"] == "full_scene"]
    paths = vg.resolve_bgm_paths(episode, ep_id)
    files = [p for p in paths.values()]
    if not full or not files or not all(Path(p).exists() for p in files):
        print("  ⚠️ BGM が見つからないので、通しは BGM なしになります")
        shutil.copyfile(narr_wav, out_wav)
        return []
    t0 = full[0]["start"]
    t1 = full[-1]["end"] + GAP_FULL_SCENE            # 最後のシーンのあとの間でフェードアウトを終える
    start_of = {e["scene"]: e["start"] for e in full}
    offsets = [start_of[s["scene_id"]] - t0 for s in episode["scenes"]]
    segs = vg.compute_bgm_segments(paths, episode["scenes"], offsets, 0.0, t1 - t0)
    segs = [(p, a + t0, b + t0) for p, a, b in segs]
    filters = [f"[0:a]aformat=sample_rates={SAMPLE_RATE}:channel_layouts=mono[n]"]
    labels = []
    for i, (p, a, b) in enumerate(segs):
        filters.append(vg._bgm_segment_filter(1 + i, a, b, i == 0, i == len(segs) - 1, f"b{i}"))
        labels.append(f"[b{i}]")
    filters.append(f"[n]{''.join(labels)}amix=inputs={1 + len(segs)}:duration=first:normalize=0,"
                   f"aformat=sample_rates={SAMPLE_RATE}:channel_layouts=mono[out]")
    cmd = ["ffmpeg", "-y", "-i", str(narr_wav)]
    for p, _, _ in segs:
        cmd += ["-i", str(p)]
    run(cmd + ["-filter_complex", ";".join(filters), "-map", "[out]", "-c:a", "pcm_s16le", str(out_wav)])
    print(f"  🎵 通し（{t0:.0f}s〜{t1:.0f}s）に BGM を重ねました（{len(segs)}曲）")
    used = {str(Path(p).relative_to(vg.DRIVE_BASE)) for p, _, _ in segs}
    lib = json.loads((SC_EPISODES.parent / "bgm_library.json").read_text(encoding="utf-8"))
    return [x["credit"] for x in lib if x.get("path") in used and x.get("credit")]


def main():
    if len(sys.argv) != 2:
        print("使い方: python3 build_lesson.py ep106")
        sys.exit(1)
    ep_id = sys.argv[1]
    lesson = json.loads((BASE_DIR / "lessons" / f"{ep_id}.json").read_text(encoding="utf-8"))
    episode = json.loads((SC_EPISODES / f"{ep_id}.json").read_text(encoding="utf-8"))
    audio_dir = SC_DRIVE / ep_id / "audio"
    narration = {i: s["narration"] for i, s in enumerate(episode["scenes"], 1)}
    scene_wav = {i: audio_dir / f"S{i:02d}.wav" for i in narration}
    for p in scene_wav.values():
        if not p.exists():
            print(f"英語音声がありません: {p}")
            sys.exit(1)

    if not CHIME.exists():
        print(f"合図の音がありません: {CHIME}")
        sys.exit(1)

    # 必要な日本語・切り出しを先にまとめて作る（並列）
    ja_texts = list(lesson["intro"]) + [lesson["to_full"], lesson["closing"]]
    sentences = {}
    for sc in lesson["scenes"]:
        n = sc["scene"]
        sentences[n] = split_sentences(narration[n])
        if len(sentences[n]) != len(sc["sentences"]):
            print(f"シーン{n}: 英語 {len(sentences[n])} 文に対して、訳が {len(sc['sentences'])} 本です")
            sys.exit(1)
        ja_texts.append(sc["cue"])
        ja_texts += [t for t in sc["sentences"] if t]
        if sc.get("one_point"):
            ja_texts.append(sc["one_point"]["ja"])
    ja_texts = list(dict.fromkeys(ja_texts))
    print(f"🎙️  日本語 {len(ja_texts)} 本・英語の文 {sum(len(v) for v in sentences.values())} 文を準備します")
    with ThreadPoolExecutor(WORKERS) as ex:
        ja = dict(zip(ja_texts, ex.map(ja_audio, ja_texts)))
        ja = dict(zip(ja, ex.map(ja_tempo, ja.values())))
    print("✅ 日本語の音声ができました")
    with ThreadPoolExecutor(WORKERS) as ex:
        clip_list = list(ex.map(lambda n: cut_scene_sentences(scene_wav[n], narration[n]), sorted(scene_wav)))
    clips = dict(zip(sorted(scene_wav), clip_list))
    print("✅ 英語の文の切り出しができました")
    # 単語ごとの時刻（動画の単語ハイライト用。手元の Whisper を使う。結果は cache/ に保存）
    words = {n: [word_times(c, t) for c, t in zip(clips[n], sentences[n])] for n in sorted(scene_wav)}
    print("✅ 単語の時刻を取りました")

    # 並び順を組み立てる。("audio", パス, 情報) と ("gap", 秒数, None)。情報は動画の字幕・画像の切り替えに使う
    seq: list[tuple] = []
    chapters: list[tuple[str, int]] = []  # (見出し, seq の位置)

    def gap(sec):
        seq.append(("gap", sec, None))

    def audio(path, **info):
        seq.append(("audio", path, info))

    gap(GAP_OPENING)
    chapters.append(("導入", len(seq)))
    for para in lesson["intro"]:
        audio(ja[para], kind="intro", text=para)
        gap(GAP_INTRO_PARA)
    gap(GAP_SECTION)
    for sc in lesson["scenes"]:
        n = sc["scene"]
        chapters.append((f"シーン{n}", len(seq)))
        audio(ja[sc["cue"]], kind="cue", scene=n, text=sc["cue"])
        gap(GAP_AFTER_CUE)
        for k, (text, clip, en_text) in enumerate(zip(sc["sentences"], clips[n], sentences[n])):
            if text:
                audio(CHIME, kind="chime", scene=n, idx=k)
                gap(GAP_CHIME)
                audio(ja[text], kind="ja", scene=n, idx=k, text=text)
                gap(GAP_JA_TO_CLIP)
            audio(clip, kind="en", scene=n, idx=k, text=en_text, words=words[n][k])
            gap(GAP_AFTER_CLIP)
        op = sc.get("one_point")
        if op:  # ワンポイント: 使える英語表現の解説 → その表現を含む英文をもう一度
            k = op["idx"]
            gap(GAP_BEFORE_OP)
            audio(ja[op["ja"]], kind="op", scene=n, idx=k, text=op["ja"], phrase=op["phrase"], phrase_ja=op["phrase_ja"])
            gap(GAP_OP_TO_EN)
            audio(clips[n][k], kind="op_en", scene=n, idx=k, text=sentences[n][k], words=words[n][k])
            gap(GAP_AFTER_CLIP)
        gap(GAP_SCENE_END)
    chapters.append(("通し", len(seq)))
    audio(ja[lesson["to_full"]], kind="to_full", text=lesson["to_full"])
    gap(GAP_SECTION)
    for n in sorted(scene_wav):
        spans = sentence_spans(scene_wav[n], clips[n])
        audio(scene_wav[n], kind="full_scene", scene=n,
              sentences=[{"idx": k, "text": t, "start": a, "end": b,
                          # 単語の時刻は、文の開始からの秒（切り出しの前の余白 PAD を引く）
                          "words": [dict(w, s=round(w["s"] - PAD, 3), e=round(w["e"] - PAD, 3)) for w in words[n][k]]}
                         for k, (t, (a, b)) in enumerate(zip(sentences[n], spans))])
        gap(GAP_FULL_SCENE)
    gap(GAP_SECTION)
    chapters.append(("締め", len(seq)))
    audio(ja[lesson["closing"]], kind="closing", text=lesson["closing"])
    gap(GAP_SECTION)

    # 無音を含めて1本の wav にする（全素材 24kHz・モノラル・16bit で揃っている）
    work = BASE_DIR / "build" / ep_id
    work.mkdir(parents=True, exist_ok=True)
    full_wav = work / "lesson.wav"
    narr_wav = work / "lesson_narr.wav"   # BGM を入れる前のナレーションだけの音声（作り直しのたびに、ここから BGM を重ねる）
    times = []
    events = []  # 動画用のタイムライン
    t = 0.0
    with wave.open(str(narr_wav), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        for kind, val, info in seq:
            times.append(t)
            if kind == "gap":
                frames = int(val * SAMPLE_RATE)
                out.writeframes(b"\x00\x00" * frames)
                t += frames / SAMPLE_RATE
            else:
                with wave.open(str(val)) as w:
                    if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (SAMPLE_RATE, 1, 2):
                        print(f"音声の形式が揃っていません: {val}")
                        sys.exit(1)
                    out.writeframes(fade_edges(w.readframes(w.getnframes())))
                    dur = w.getnframes() / SAMPLE_RATE
                ev = dict(info, start=round(t, 3), end=round(t + dur, 3))
                if info["kind"] == "full_scene":  # シーン音声の中の文の位置を、全体の時刻に直す
                    for sen in ev["sentences"]:
                        sen["start"] = round(t + sen["start"], 3)
                        sen["end"] = round(t + sen["end"], 3)
                events.append(ev)
                t += dur
    bgm_credits = mix_full_bgm(narr_wav, full_wav, episode, ep_id, events)
    (work / "timeline.json").write_text(
        json.dumps({"episode_id": ep_id, "title_ja": lesson["title_ja"], "total": round(t, 3), "bgm_credits": bgm_credits,
                    "chapters": [{"name": n, "start": round(times[i], 3)} for n, i in chapters],
                    "events": events}, ensure_ascii=False, indent=1), encoding="utf-8")

    out_dir = SC_DRIVE / ep_id / "learning"  # 出力は他の成果物と同じく ep{NNN}/ の下に置く
    out_dir.mkdir(parents=True, exist_ok=True)
    title = f"{ep_id} {lesson['title_ja']}"
    mp3_local = work / f"{title}.mp3"  # 動画の組み立てが手元から読めるように、手元にも置く（Drive 上を直接読むと、待ちで失敗することがある）
    run(["ffmpeg", "-y", "-i", str(full_wav), "-af", LOUDNESS, "-ar", "44100", "-ac", "1", "-b:a", "96k",
         "-metadata", f"title={title}", "-metadata", "artist=Tokio Kamiya", "-metadata", "album=英語耳 Samurai Chronicles",
         str(mp3_local)])
    mp3 = out_dir / f"{title}.mp3"
    shutil.copyfile(mp3_local, mp3)

    lines = [f"{title}  全体 {int(t // 60)}分{int(t % 60):02d}秒", ""]
    for name, idx in chapters:
        s = times[idx]
        lines.append(f"{int(s // 60):02d}:{int(s % 60):02d}  {name}")
    (work / "chapters.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n✅ 完成: {mp3}")


if __name__ == "__main__":
    main()
