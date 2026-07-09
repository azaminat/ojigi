"""コストレシート — usage の記録と料金換算。

デフォルト単価は公式ページ・公開情報の公称値（USD）。実測（Zoom Buildのクレジット
消費との突合）で確定したら pricing.json で上書きする。公称と実測の差自体が検証ネタ。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from rich.table import Table

from .models import UsageRecord

LEDGER_PATH = Path("output/usage_ledger.jsonl")

# 公称単価（USD）。Scribe: 音声1分あたり / Summarizer・Translator: 100万文字あたり
# 出典: zoom.com製品ページほか（81_aidocs/claude/api_spec.md 参照）
DEFAULT_PRICING: dict[str, float] = {
    "scribe_fast_usd_per_audio_minute": 0.0033,
    "summarizer_usd_per_1m_chars": 0.40,
    "translator_usd_per_1m_chars": 7.50,
    "usd_jpy_rate": 150.0,
}


def load_pricing(path: Path | None = None) -> dict[str, float]:
    pricing = dict(DEFAULT_PRICING)
    pricing_file = path or Path("pricing.json")
    if pricing_file.exists():
        pricing.update(json.loads(pricing_file.read_text(encoding="utf-8")))
    return pricing


def append_to_ledger(record: UsageRecord, ledger_path: Path = LEDGER_PATH) -> None:
    """全API呼び出しの usage を JSONL に追記する（コスト実測の一次データ）。"""
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


@dataclass
class CostLine:
    api: str
    quantity_label: str  # 例: "音声 5.2分" "入力 3,420文字"
    usd: float
    yen: float


def estimate_cost(records: list[UsageRecord], pricing: dict[str, float]) -> list[CostLine]:
    rate = pricing["usd_jpy_rate"]
    lines: list[CostLine] = []

    scribe = [r for r in records if r.api == "scribe"]
    if scribe:
        minutes = sum(r.audio_seconds for r in scribe) / 60
        usd = minutes * pricing["scribe_fast_usd_per_audio_minute"]
        lines.append(CostLine("Scribe", f"音声 {minutes:.1f}分", usd, usd * rate))

    for api, key, label in [
        ("summarizer", "summarizer_usd_per_1m_chars", "Summarizer"),
        ("translator", "translator_usd_per_1m_chars", "Translator"),
    ]:
        recs = [r for r in records if r.api == api]
        if recs:
            chars = sum(r.input_chars for r in recs)
            usd = chars / 1_000_000 * pricing[key]
            lines.append(CostLine(label, f"入力 {chars:,}文字", usd, usd * rate))
    return lines


def build_receipt_table(lines: list[CostLine]) -> Table:
    """rich のコストレシート表を組み立てる（CLI実行の最後に表示）。"""
    table = Table(title="💰 コストレシート（公称単価ベース）", show_footer=True)
    total_usd = sum(line.usd for line in lines)
    total_yen = sum(line.yen for line in lines)
    table.add_column("API", footer="合計")
    table.add_column("使用量")
    table.add_column("USD", footer=f"${total_usd:.4f}", justify="right")
    table.add_column("円換算", footer=f"¥{total_yen:.2f}", justify="right")
    for line in lines:
        table.add_row(line.api, line.quantity_label, f"${line.usd:.4f}", f"¥{line.yen:.2f}")
    return table
