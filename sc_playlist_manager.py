"""
sc_playlist_manager.py — Samurai Chronicles キャラクター別プレイリスト自動管理

ルール:
  初登場   → character_playlists.json に記録のみ（プレイリストなし）
  2回目    → プレイリスト作成 → 全出演エピソードを追加
  3回目以降 → 既存プレイリストに追加

使い方（sc_sns_up.py から自動呼び出し。単体実行も可）:
  python3 sc_playlist_manager.py --episode ep006 --video-id abc123XYZ
"""

import argparse
import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
CHAR_PLAYLISTS_JSON = BASE_DIR / "character_playlists.json"

CHAR_DISPLAY_NAMES = {
    "musashi":            "Miyamoto Musashi",
    "kojiro":             "Sasaki Kojiro",
    "nobunaga":           "Oda Nobunaga",
    "hideyoshi":          "Toyotomi Hideyoshi",
    "ieyasu":             "Tokugawa Ieyasu",
    "mitsuhide":          "Akechi Mitsuhide",
    "katsuie":            "Shibata Katsuie",
    "yoshitsune":         "Minamoto Yoshitsune",
    "yoritomo":           "Minamoto Yoritomo",
    "kenshin":            "Uesugi Kenshin",
    "shingen":            "Takeda Shingen",
    "masamune":           "Date Masamune",
    "saigo":              "Saigo Takamori",
    "yukimura":           "Sanada Yukimura",
    "mitsunari":          "Ishida Mitsunari",
    "hattori_hanzo":      "Hattori Hanzo",
    "honda_tadakatsu":    "Honda Tadakatsu",
    "kuroda_kanbei":      "Kuroda Kanbei",
    "tomoe_gozen":        "Tomoe Gozen",
    "kiyomori":           "Taira Kiyomori",
    "yagyu":              "Yagyu Munenori",
    "kusunoki":           "Kusunoki Masashige",
    "naoe_kanetsugu":     "Naoe Kanetsugu",
    "ii_naomasa":         "Ii Naomasa",
    "shimazu":            "Shimazu Yoshihiro",
    "mori_motonari":      "Mori Motonari",
    "chosokabe":          "Chosokabe Motochika",
    "maeda_toshiie":      "Maeda Toshiie",
    "tachibana_ginchiyo": "Tachibana Ginchiyo",
    "benkei":             "Musashibo Benkei",
}


def _load_data() -> dict:
    if CHAR_PLAYLISTS_JSON.exists():
        return json.loads(CHAR_PLAYLISTS_JSON.read_text(encoding="utf-8"))
    return {}


def _save_data(data: dict):
    CHAR_PLAYLISTS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _create_playlist(youtube, display_name: str) -> str:
    """キャラクター専用プレイリストを YouTube に作成して ID を返す。"""
    title = f"{display_name.upper()} | Samurai Chronicles"
    description = f"All Samurai Chronicles episodes featuring {display_name}"
    resp = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": "public"},
        },
    ).execute()
    playlist_id = resp["id"]
    print(f"  🎬 プレイリスト作成: {title}")
    print(f"     https://www.youtube.com/playlist?list={playlist_id}")
    return playlist_id


def _add_to_playlist(youtube, playlist_id: str, video_id: str):
    """動画をプレイリストに追加する。"""
    youtube.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        },
    ).execute()
    time.sleep(0.5)  # API レート制限対策


def update_playlists(youtube, episode_id: str, video_id: str, ep: dict):
    """
    アップロード後に呼び出す。エピソードのキャラクターを処理してプレイリストを更新。

    Args:
        youtube:    認証済み YouTube API クライアント
        episode_id: "ep006" 形式
        video_id:   アップロードした本編動画の YouTube ID
        ep:         エピソード JSON の dict
    """
    chars = set()
    for scene in ep.get("scenes", []):
        char = scene.get("character_ref")
        if char:
            chars.add(char)

    if not chars:
        print("  キャラクター登場なし（プレイリスト処理スキップ）")
        return

    data = _load_data()
    updated = False

    for char in sorted(chars):
        display_name = CHAR_DISPLAY_NAMES.get(
            char, char.replace("_", " ").title()
        )

        # 初期化
        if char not in data:
            data[char] = {
                "display_name": display_name,
                "playlist_id": None,
                "episodes": [],
            }

        char_data = data[char]

        # 同エピソードの重複登録を防ぐ
        if any(e["episode_id"] == episode_id for e in char_data["episodes"]):
            print(f"  {display_name}: {episode_id} は登録済み（スキップ）")
            continue

        # 今回のエピソードを追記
        char_data["episodes"].append(
            {"episode_id": episode_id, "video_id": video_id}
        )
        updated = True
        appearances = len(char_data["episodes"])

        if appearances == 1:
            print(f"  {display_name}: 初登場（記録のみ）")

        elif appearances == 2:
            # プレイリスト作成 → 出演済み全エピソードを追加
            playlist_id = _create_playlist(youtube, display_name)
            char_data["playlist_id"] = playlist_id
            added = 0
            for entry in char_data["episodes"]:
                if entry["video_id"]:
                    _add_to_playlist(youtube, playlist_id, entry["video_id"])
                    added += 1
                else:
                    print(f"     ⚠️  {entry['episode_id']}: video_id 未登録のためスキップ")
            print(f"     ✓ {added}本を追加")

        else:
            # 既存プレイリストに追加
            playlist_id = char_data["playlist_id"]
            if playlist_id:
                _add_to_playlist(youtube, playlist_id, video_id)
                print(f"  {display_name}: プレイリストに追加 ({appearances}回目)")
            else:
                # playlist_id が未登録（過去のアップロード漏れ）→ 今から作成してバックフィル
                print(f"  {display_name}: playlist_id 未登録 → プレイリストを新規作成してバックフィル")
                playlist_id = _create_playlist(youtube, display_name)
                char_data["playlist_id"] = playlist_id
                added = 0
                for entry in char_data["episodes"]:
                    if entry["video_id"]:
                        _add_to_playlist(youtube, playlist_id, entry["video_id"])
                        added += 1
                    else:
                        print(f"     ⚠️  {entry['episode_id']}: video_id 未登録のためスキップ")
                print(f"     ✓ {added}本を追加（バックフィル完了）")

    if updated:
        _save_data(data)
        print(f"  ✓ character_playlists.json 更新済み")


def cli():
    parser = argparse.ArgumentParser(
        description="キャラクタープレイリスト管理（単体実行用）"
    )
    parser.add_argument("--episode", required=True, help="エピソードID（例: ep006）")
    parser.add_argument("--video-id", required=True, help="YouTube 動画ID")
    args = parser.parse_args()

    # 認証は sc_sns_up.py と同じ方法で取得
    from sc_sns_up import get_youtube_client
    ep_json = BASE_DIR / "episodes" / f"{args.episode}.json"
    if not ep_json.exists():
        print(f"❌ エピソードJSONが見つかりません: {ep_json}")
        sys.exit(1)
    ep = json.loads(ep_json.read_text(encoding="utf-8"))
    youtube = get_youtube_client()

    print(f"\n{'━'*60}")
    print(f"  {args.episode} — プレイリスト処理")
    print(f"{'━'*60}\n")
    update_playlists(youtube, args.episode, args.video_id, ep)
    print(f"\n{'━'*60}\n")


if __name__ == "__main__":
    cli()
