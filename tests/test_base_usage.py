"""usage抽出ロジック（unit_type分岐）のテスト。実測レスポンス構造に基づく。"""

from ojigi.clients.base import BaseClient


def _extract(data, usage):
    return BaseClient._extract_quantities(BaseClient.__new__(BaseClient), data, usage)


def test_scribe_seconds_usage():
    # Scribe実測: {"input_units": 47.704, "output_units": 0, "unit_type": "seconds"}
    q = _extract({"duration_sec": 47.704}, {"input_units": 47.704, "output_units": 0, "unit_type": "seconds"})
    assert q == {"audio_seconds": 47.704}


def test_characters_usage():
    # Summarizer/Translator実測: {"input_units": 335, "output_units": 441, "unit_type": "characters"}
    q = _extract({}, {"input_units": 335, "output_units": 441, "unit_type": "characters"})
    assert q == {"input_chars": 335, "output_chars": 441}


def test_fallback_to_duration_sec_when_no_usage():
    q = _extract({"duration_sec": 10.5}, {})
    assert q == {"audio_seconds": 10.5}
