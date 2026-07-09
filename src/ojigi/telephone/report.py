"""伝言ゲームの結果を人間向け（記事素材）に整形する。

- 世代進化テーブル: 各世代のテキスト抜粋を並べ、劣化の様子を見せる
- キーワードトレース: 特定の固有名詞/数値が世代ごとにどう変異したか（誤変換ハイライトの核）
- サバイバル年表: どのファクトが何世代目で消えたか

ExperimentResult もしくはその to_dict() 済みJSON（playgroundで保存したもの）から動く。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def _as_dict(result: Any) -> dict[str, Any]:
    return result if isinstance(result, dict) else result.to_dict()


def text_evolution(result: Any, trial: int = 0, max_chars: int = 60) -> list[tuple[int, str]]:
    """(世代, テキスト抜粋) のリスト。劣化の様子を一覧化する。"""
    data = _as_dict(result)
    gens = data["trials"][trial]["generations"]
    out: list[tuple[int, str]] = []
    for g in gens:
        text = (g["text"] or "").replace("\n", " ")
        out.append((g["generation"], text[:max_chars] + ("…" if len(text) > max_chars else "")))
    return out


def _snippet(text: str, keyword: str, window: int = 12) -> str | None:
    """text 中の keyword 周辺を切り出す（NFKC正規化して探索）。見つからなければ None。"""
    norm = unicodedata.normalize("NFKC", text)
    kw = unicodedata.normalize("NFKC", keyword)
    idx = norm.casefold().find(kw.casefold())
    if idx < 0:
        return None
    start, end = max(0, idx - window), min(len(norm), idx + len(kw) + window)
    return ("…" if start > 0 else "") + norm[start:end] + ("…" if end < len(norm) else "")


def keyword_trace(
    result: Any, keywords: list[str], trial: int = 0, include_intermediate: bool = True
) -> list[dict[str, Any]]:
    """世代ごとに keywords のいずれかを含む周辺テキストを抽出（誤変換ハイライト用）。

    full モードでは intermediates の asr（文字起こし直後）/ en（英訳）も追跡し、
    「音声化で化けた」「英訳で化けた」のどちらかを可視化する。
    """
    data = _as_dict(result)
    tr = data["trials"][trial]
    gens = tr["generations"]
    inters = tr.get("intermediates") or [{}] * len(gens)
    rows: list[dict[str, Any]] = []
    for i, g in enumerate(gens):
        text = g["text"] or ""
        snip = next((s for kw in keywords if (s := _snippet(text, kw))), None)
        row: dict[str, Any] = {"generation": g["generation"], "text": snip or "（消失）"}
        if include_intermediate and i < len(inters):
            inter = inters[i]
            if inter.get("asr"):
                row["asr"] = next((s for kw in keywords if (s := _snippet(inter["asr"], kw))), "（消失）")
            if inter.get("en"):
                row["en"] = next((s for kw in keywords if (s := _snippet(inter["en"], kw))), "-")
        rows.append(row)
    return rows


def survival_timeline(result: Any, trial: int = 0) -> dict[str, int]:
    """各ファクトが最初に消えた世代を返す（{fact_id: 世代}）。一度も消えなかったものは含まれない。"""
    data = _as_dict(result)
    gens = data["trials"][trial]["generations"]
    first_death: dict[str, int] = {}
    for g in gens:
        for fid in g.get("dead_fact_ids") or []:
            first_death.setdefault(fid, g["generation"])
    return first_death


def to_markdown(result: Any, trial: int = 0, trace_keywords: list[str] | None = None) -> str:
    """記事貼り付け用のMarkdownを生成する。"""
    data = _as_dict(result)
    mode = data.get("mode", "?")
    lines = [f"### 伝言ゲーム結果（mode={mode}, trial={trial}）", "", "#### 世代進化", "", "| 世代 | テキスト |", "|---|---|"]
    for gen, text in text_evolution(result, trial):
        lines.append(f"| {gen} | {text} |")

    if trace_keywords:
        lines += ["", f"#### 誤変換トレース（{' / '.join(trace_keywords)}）", "", "| 世代 | 文字起こし | 英訳 | 往復後 |", "|---|---|---|---|"]
        for row in keyword_trace(result, trace_keywords, trial):
            lines.append(
                f"| {row['generation']} | {row.get('asr', '-')} | {row.get('en', '-')} | {row['text']} |"
            )

    tl = survival_timeline(result, trial)
    if tl:
        lines += ["", "#### 消失したファクト（初出世代）", ""]
        for fid, gen in sorted(tl.items(), key=lambda kv: kv[1]):
            lines.append(f"- `{fid}`: 第{gen}世代で消失")
    return "\n".join(lines)
