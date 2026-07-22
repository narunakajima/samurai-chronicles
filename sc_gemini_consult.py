#!/usr/bin/env python3
"""
sc_gemini_consult.py — Gemini との1ターン対話（履歴ファイルで継続）

使い方:
  # Turn 1（新規セッション）
  python3 sc_gemini_consult.py --message "課題テキスト"

  # Turn 2以降（履歴を引き継ぎ）
  python3 sc_gemini_consult.py --message "コメント" --history-file /tmp/sc_consult_history.json

オプション:
  --message        送信するメッセージ（必須）
  --history-file   前ターンの会話履歴JSONファイル
  --save-history   履歴の保存先（デフォルト: /tmp/sc_consult_history.json）
  --model          Geminiモデル（デフォルト: gemini-2.5-flash）
  --system         システムプロンプト（任意）
"""

import argparse
import json
import os
import sys
from pathlib import Path

from google import genai
from google.genai import types

API_KEY = os.environ.get("GEMINI_API_KEY_SC") or os.environ.get("GEMINI_API_KEY", "")
DEFAULT_HISTORY = Path("/tmp/sc_consult_history.json")
DEFAULT_MODEL = "models/gemini-3.6-flash"


def load_history(path: Path) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_history(path: Path, history: list):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Gemini 対話コンサルティング")
    parser.add_argument("--message", required=True, help="送信するメッセージ")
    parser.add_argument("--history-file", type=Path, default=None,
                        help="前ターンの会話履歴JSONファイル")
    parser.add_argument("--save-history", type=Path, default=DEFAULT_HISTORY,
                        help=f"履歴保存先（デフォルト: {DEFAULT_HISTORY}）")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Geminiモデル（デフォルト: {DEFAULT_MODEL}）")
    parser.add_argument("--system", default="",
                        help="システムプロンプト（任意）")
    args = parser.parse_args()

    if not API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません", file=sys.stderr)
        sys.exit(1)

    # 前ターンの履歴を読み込む
    history = []
    if args.history_file and args.history_file.exists():
        history = load_history(args.history_file)

    # 今ターンのメッセージを追加
    contents = history + [{"role": "user", "parts": [{"text": args.message}]}]

    client = genai.Client(api_key=API_KEY)

    config = types.GenerateContentConfig()
    if args.system:
        config = types.GenerateContentConfig(
            system_instruction=args.system,
        )

    response = client.models.generate_content(
        model=args.model,
        contents=contents,
        config=config,
    )
    reply = response.text

    # 履歴を更新して保存（次ターンで --history-file に渡す）
    updated = contents + [{"role": "model", "parts": [{"text": reply}]}]
    save_history(args.save_history, updated)

    print(reply)


if __name__ == "__main__":
    main()
