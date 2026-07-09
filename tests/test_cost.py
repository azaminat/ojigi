from datetime import datetime

from ojigi.cost import CostLine, build_receipt_table, estimate_cost
from ojigi.models import UsageRecord

PRICING = {
    "scribe_fast_usd_per_audio_minute": 0.0033,
    "summarizer_usd_per_1m_chars": 0.40,
    "translator_usd_per_1m_chars": 7.50,
    "usd_jpy_rate": 150.0,
}


def _rec(api: str, **kw) -> UsageRecord:
    return UsageRecord(api=api, endpoint="/test", timestamp=datetime(2026, 7, 2, 12, 0, 0), **kw)


def test_estimate_cost_scribe_per_minute():
    lines = estimate_cost([_rec("scribe", audio_seconds=600)], PRICING)  # 10分
    assert lines[0].api == "Scribe"
    assert abs(lines[0].usd - 0.033) < 1e-9
    assert abs(lines[0].yen - 4.95) < 1e-9


def test_estimate_cost_chars_based():
    lines = estimate_cost(
        [_rec("summarizer", input_chars=100_000), _rec("translator", input_chars=10_000)], PRICING
    )
    by_api = {line.api: line for line in lines}
    assert abs(by_api["Summarizer"].usd - 0.04) < 1e-9
    assert abs(by_api["Translator"].usd - 0.075) < 1e-9


def test_estimate_cost_aggregates_multiple_calls():
    lines = estimate_cost(
        [_rec("translator", input_chars=1000), _rec("translator", input_chars=2000)], PRICING
    )
    assert "3,000文字" in lines[0].quantity_label
    assert abs(lines[0].usd - 3000 / 1_000_000 * 7.50) < 1e-9


def test_receipt_table_builds_with_total():
    table = build_receipt_table(
        [CostLine("Scribe", "音声 10.0分", 0.033, 4.95), CostLine("Translator", "入力 1,000文字", 0.0075, 1.125)]
    )
    assert table.row_count == 2
    assert "¥6.08" in table.columns[3].footer
