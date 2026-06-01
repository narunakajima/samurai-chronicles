"""
sc_bgm_library.py — BGM ライブラリ管理ユーティリティ

使い方:
  # Freesound新規BGMをライブラリに追加
  python3 sc_bgm_library.py --add --episode ep012 --file <path> --stem BGM_candidate_01_xxx

  # ライブラリ既存BGMをエピソードに紐付け（bgm_source を episode JSON に記録）
  python3 sc_bgm_library.py --use-library --episode ep012 --stem BGM_library_01_ep003-BGM
"""

import argparse
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
LIBRARY_JSON = BASE_DIR / "bgm_library.json"
DRIVE_BASE = (
    Path.home()
    / "Library/CloudStorage"
    / "GoogleDrive-naru.nakajima@gmail.com"
    / "マイドライブ"
    / "samurai-chronicles"
)


def _load_library() -> list:
    if LIBRARY_JSON.exists():
        return json.loads(LIBRARY_JSON.read_text(encoding="utf-8"))
    return []


def _save_library(data: list):
    LIBRARY_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_ep(episode_id: str) -> tuple:
    """エピソードJSON を読み込んで (data, path) を返す。"""
    ep_json = BASE_DIR / "episodes" / f"{episode_id}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}")
        sys.exit(1)
    data = json.loads(ep_json.read_text(encoding="utf-8"))
    return data, ep_json


def _save_ep(ep_json: Path, data: dict):
    ep_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _tags_from_stem(stem: str) -> list:
    """Freesound ファイル名のキーワードからタグを推測する。
    例: BGM_candidate_01_12345_epic-orchestral → ["epic", "orchestral"]
    """
    # ファイル名から数字・アンダースコア・BGM_candidate プレフィックスを除去してキーワード抽出
    cleaned = re.sub(r'^BGM_candidate_\d+_\d+_', '', stem)
    words = re.split(r'[-_\s]+', cleaned.lower())
    known = {"orchestral", "epic", "dramatic", "cinematic", "heroic", "dark",
             "powerful", "tense", "triumphant", "strings", "brass", "choir",
             "taiko", "percussion", "medieval", "emotional"}
    return [w for w in words if w in known] or ["orchestral", "cinematic"]


def cmd_add(episode_id: str, bgm_file: Path, stem: str):
    """Freesound 新規BGMをライブラリに追加し、used_in を記録する。"""
    library = _load_library()

    # BGM/フォルダに移動してDRIVE_BASE相対パスを記録
    bgm_folder = DRIVE_BASE / "BGM"
    bgm_folder.mkdir(exist_ok=True)
    dst = bgm_folder / f"{episode_id}-BGM.mp3"
    import shutil
    shutil.move(str(bgm_file), str(dst))
    rel_path = f"BGM/{episode_id}-BGM.mp3"
    print(f"  ✓ Drive BGM/ に移動: {dst.name}")

    # 重複チェック（同パスが既にある場合は used_in のみ更新）
    existing = next((e for e in library if e["path"] == rel_path), None)
    if existing:
        if episode_id not in existing["used_in"]:
            existing["used_in"].append(episode_id)
            _save_library(library)
        print(f"  ✓ ライブラリ更新（既存エントリに {episode_id} を追加）")
        return

    # 新規エントリ
    tags = _tags_from_stem(stem)
    entry = {
        "id": f"{episode_id}-BGM",
        "path": rel_path,
        "duration": 0,  # 後で ffprobe で更新可
        "license": "CC0",  # credit.txt があれば CC BY に変更
        "credit": None,
        "tags": tags,
        "used_in": [episode_id],
    }

    # credit.txt が /tmp にあれば CC BY として登録
    credit_path = Path(f"/tmp/sc_bgm_credits/{stem}.credit.txt")
    if credit_path.exists():
        entry["license"] = "CC BY"
        entry["credit"] = credit_path.read_text(encoding="utf-8").strip()

    library.append(entry)
    _save_library(library)
    print(f"  ✓ ライブラリに追加: {rel_path}  tags={tags}")


def cmd_use_library(episode_id: str, stem: str):
    """ライブラリ既存BGMをエピソードに紐付ける（bgm_source を episode JSON に記録）。

    stem 例: BGM_library_01_ep003-BGM
    → ライブラリから id="ep003-BGM" のエントリを探して bgm_source に path を設定
    """
    library = _load_library()
    ep_data, ep_json = _load_ep(episode_id)

    # stem から元のライブラリ id を取得
    # "BGM_library_01_ep003-BGM" → "ep003-BGM"
    lib_id = re.sub(r'^BGM_library_\d+_', '', stem)
    entry = next((e for e in library if e["id"] == lib_id), None)

    if not entry:
        print(f"❌ ライブラリにエントリが見つかりません: id={lib_id}")
        sys.exit(1)

    # episode JSON に bgm_source を記録
    ep_data["bgm_source"] = entry["path"]
    _save_ep(ep_json, ep_data)

    # ライブラリの used_in を更新
    if episode_id not in entry["used_in"]:
        entry["used_in"].append(episode_id)
        _save_library(library)

    # credit.txt を /tmp に用意（CC BY の場合、sc_inject_bgm_credit.py 用）
    if entry["license"] == "CC BY" and entry.get("credit"):
        credit_tmp = Path(f"/tmp/sc_bgm_credits/{stem}.credit.txt")
        credit_tmp.parent.mkdir(parents=True, exist_ok=True)
        credit_tmp.write_text(entry["credit"], encoding="utf-8")

    print(f"  ✓ bgm_source を設定: {entry['path']}")
    print(f"  ✓ ライブラリ used_in 更新: {entry['used_in']}")


def cli():
    parser = argparse.ArgumentParser(description="BGMライブラリ管理")
    parser.add_argument("--add", action="store_true", help="新規BGMをライブラリに追加")
    parser.add_argument("--use-library", action="store_true", help="ライブラリ曲をエピソードに紐付け")
    parser.add_argument("--episode", required=True)
    parser.add_argument("--file", help="BGMファイルパス（--add 時）")
    parser.add_argument("--stem", required=True, help="ファイル名（拡張子なし）")
    args = parser.parse_args()

    if args.add:
        if not args.file:
            parser.error("--add には --file が必要です")
        cmd_add(args.episode, Path(args.file), args.stem)
    elif args.use_library:
        cmd_use_library(args.episode, args.stem)
    else:
        parser.error("--add または --use-library を指定してください")


if __name__ == "__main__":
    cli()
