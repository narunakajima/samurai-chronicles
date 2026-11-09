"""
sc_gemini_model.py — Gemini（テキスト/マルチモーダル判定用 Flash 系）のモデル名の集約と自動フォールバック

2026-11-09（指示 2026-11-09-025）: モデル名は今後も変わりうるため、1か所に集約する。
- 候補リスト CANDIDATES は、実在を確認できた固定IDだけを優先順に並べる。-latest 系エイリアスは入れない。
- 呼び出しが「モデル不存在」（404 / NOT_FOUND / is not found for API version）で失敗した場合に限り、
  次の候補で再試行する。クォータ超過（429）・認証エラー（401/403）では切り替えない。
- 切り替えが起きたら、切り替え前後のモデル名を標準出力と logs/gemini_model_fallback.log に記録する。
- フォールバックは各スクリプトのQA判定より前段（モデル解決 / generate_content ラッパー内部）で完結する。

対象外: TTS専用モデル（gemini-3.8-flash-tts）と画像生成モデル（gemini-nano-banana-*）。

使い方:
  import sc_gemini_model as gm
  response = gm.generate_content(client, contents, config=...)   # 呼び出し時フォールバック付き
  model = gm.resolve_model(client)                               # 事前解決（存在確認）。QA前に呼ぶ
  gm.run_with_fallback(lambda model: ...)                        # REST 等、独自の呼び出し向け
"""

from datetime import datetime
from pathlib import Path

# 優先順。実在確認済みのものだけを入れる（確認手順は handoff/results/2026-11-09-025.md）。
CANDIDATES = [
    "gemini-3.8-flash",  # 第一候補（2026-11-09 実呼び出しで検証済み）
    "gemini-3.7-flash",  # 第二候補（2026-11-09 実呼び出しで検証済み。BGM QAの判定が返る）
    # gemini-3.6-flash は実在するが、BGM QAのJSON出力が崩れた（2026-11-09）ため候補に入れない
]

LOG_PATH = Path(__file__).parent / "logs" / "gemini_model_fallback.log"

# プロセス内で一度決めた現在の候補位置
_state = {"index": 0}


class ModelUnavailable(RuntimeError):
    """候補リストの全モデルが存在しない。"""


def is_model_not_found(exc: Exception) -> bool:
    """「モデル不存在」エラーかどうか。クォータ超過・認証エラーなどは False。"""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    status = str(getattr(exc, "status", "") or "")
    text = str(exc)
    if code in (401, 403, 429) or any(k in text for k in ("RESOURCE_EXHAUSTED", "PERMISSION_DENIED",
                                                         "UNAUTHENTICATED", "API key not valid")):
        return False
    if code == 404 or status == "NOT_FOUND":
        return True
    if "404" in text and "NOT_FOUND" in text:
        return True
    return "is not found for API version" in text


def current_model() -> str:
    return CANDIDATES[_state["index"]]


def _record_fallback(old: str, new: str, reason: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} Geminiモデル切り替え: {old} → {new}（理由: {reason[:160]}）"
    print(f"⚠️  {line}", flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        print(f"⚠️  フォールバックログの書き込みに失敗: {e}", flush=True)


def run_with_fallback(fn):
    """fn(model_name) を現在の候補で呼ぶ。モデル不存在のときだけ次の候補へ進めて再試行する。"""
    while True:
        model = current_model()
        try:
            return fn(model)
        except Exception as e:
            if not is_model_not_found(e):
                raise
            if _state["index"] + 1 >= len(CANDIDATES):
                raise ModelUnavailable(
                    f"候補リストの全モデルが存在しません: {CANDIDATES}（最後のエラー: {e}）") from e
            _state["index"] += 1
            _record_fallback(model, current_model(), str(e))


def resolve_model(client) -> str:
    """モデル情報の取得（課金なし）で存在を確認し、存在する最初の候補を返す。
    QA判定の前段で呼ぶことで、モデル不存在がQAの例外処理に飲まれないようにする。"""
    def _probe(model):
        client.models.get(model=model)
        return model
    return run_with_fallback(_probe)


def generate_content(client, contents, config=None):
    """client.models.generate_content のモデル不存在フォールバック付きラッパー。"""
    def _call(model):
        if config is None:
            return client.models.generate_content(model=model, contents=contents)
        return client.models.generate_content(model=model, contents=contents, config=config)
    return run_with_fallback(_call)
