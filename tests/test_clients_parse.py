"""APIレスポンスのパースロジック（実通信なし）のテスト。"""

from ojigi.clients.scribe import ScribeClient
from ojigi.clients.summarizer import SummarizerClient
from ojigi.clients.translator import TranslatorClient
from ojigi.models import Transcript, TranscriptSegment


def test_scribe_parse_prefers_text_display():
    data = {
        "request_id": "req_1",
        "duration_sec": 27.4,
        "result": {
            "text_display": "こんにちは。テストです。",
            "text_lexical": "こんにちは テスト です",
            "segments": [
                {"start": 0.0, "end": 3.2, "text": "こんにちは。", "speaker": "speaker_1"},
                {"start": 3.2, "end": 5.0, "text": "テストです。", "speaker": "speaker_2"},
            ],
        },
    }
    t = ScribeClient._parse(data, "ja-JP")
    assert t.text == "こんにちは。テストです。"
    assert len(t.segments) == 2
    assert t.segments[0].speaker == "speaker_1"


def test_scribe_parse_falls_back_to_segments():
    data = {"result": {"segments": [{"text": "あ"}, {"text": "い"}]}}
    t = ScribeClient._parse(data, "ja-JP")
    assert t.text == "あ\nい"


def test_summarizer_parse_fallback_keys():
    for key in ("full_summary", "summary_text", "text"):
        s = SummarizerClient._parse({"result": {key: "要約本文"}})
        assert s.overview == "要約本文", key


def test_summarizer_parse_full_summary_sections():
    """スパイク実測（2026-07-03）の full_summary 実構造を再現。"""
    md = (
        "# Recap\n本日の会議では、リリース日は7月13日に確定した。\n\n"
        "# Summary\n## 新機能リリース\n詳細本文。\n\n"
        "# Action Items\n**Unknown**\n- リリースノートのドラフトを7月5日までに作成する\n\n"
        "**田中**\n- 負荷テストをステージング環境で7月8日までに実施する"
    )
    s = SummarizerClient._parse({"result": {"full_summary": md}})
    assert s.overview == "本日の会議では、リリース日は7月13日に確定した。"
    assert s.key_points == ["**新機能リリース** 詳細本文。"]
    assert len(s.action_items) == 2
    assert s.action_items[0].assignee is None  # "Unknown" は None に落とす
    assert s.action_items[0].description == "リリースノートのドラフトを7月5日までに作成する"
    assert s.action_items[1].assignee == "田中"


def test_summarizer_parse_plain_text_without_sections():
    s = SummarizerClient._parse({"result": {"summary_text": "見出しなしの要約文。"}})
    assert s.overview == "見出しなしの要約文。"
    assert s.action_items == []


def test_summarizer_speaker_text_format():
    transcript = Transcript(
        text="",
        segments=[
            TranscriptSegment(speaker="speaker_1", text="おはよう"),
            TranscriptSegment(speaker="speaker_2", text="こんにちは"),
        ],
    )
    text = SummarizerClient._to_speaker_text(transcript)
    assert text == "speaker_1: おはよう\nspeaker_2: こんにちは"


def test_translator_split_respects_limit():
    text = "\n".join(["あ" * 1500] * 5)  # 7500字強
    chunks = TranslatorClient._split(text, 4000)
    assert all(len(c) <= 4000 for c in chunks)
    assert "".join(chunks).replace("\n", "") == "あ" * 7500


def test_translator_split_short_text_single_chunk():
    assert TranslatorClient._split("短いテキスト", 4000) == ["短いテキスト"]


def test_translator_split_oversized_paragraph():
    chunks = TranslatorClient._split("x" * 9000, 4000)
    assert [len(c) for c in chunks] == [4000, 4000, 1000]
