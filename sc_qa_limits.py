"""team/qa_limits.json（再生成・再試行の上限の正本）を読む小さなヘルパー。

読めない・キーが無いときは、渡された既定値を使う（スクリプトが止まらないように）。
"""
import json
from pathlib import Path

_PATH = Path(__file__).parent / "team" / "qa_limits.json"


def qa_limit(key: str, default: int) -> int:
    try:
        v = json.loads(_PATH.read_text(encoding="utf-8")).get(key, default)
        return int(v) if int(v) >= 1 else default
    except Exception:  # noqa: BLE001
        return default
