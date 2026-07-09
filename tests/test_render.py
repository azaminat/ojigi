from datetime import datetime

from ojigi.models import ActionItem, MinutesResult, Summary, Transcript, TranscriptSegment
from ojigi.render import to_markdown, to_slack_blocks


def _result(**kw) -> MinutesResult:
    defaults = dict(
        source_file="meeting.m4a",
        created_at=datetime(2026, 7, 2, 10, 0, 0),
        transcript=Transcript(text="こんにちは。テスト会議です。"),
        summary=Summary(
            overview="テスト会議の要約",
            decisions=["リリースは7月13日に決定"],
            action_items=[ActionItem(description="資料作成", assignee="田中", due="7/5")],
        ),
    )
    defaults.update(kw)
    return MinutesResult(**defaults)


def test_markdown_contains_japanese_sections():
    md = to_markdown(_result())
    assert "## 🇯🇵 日本語" in md
    assert "リリースは7月13日に決定" in md
    assert "- [ ] 資料作成（担当: 田中）（期限: 7/5）" in md
    assert "こんにちは。テスト会議です。" in md


def test_markdown_includes_english_when_translated():
    md = to_markdown(_result(summary_en=Summary(overview="Summary of test meeting")))
    assert "## 🇺🇸 English" in md
    assert "Summary of test meeting" in md


def test_markdown_renders_segments_with_speaker():
    transcript = Transcript(
        text="", segments=[TranscriptSegment(speaker="Speaker 1", text="おはようございます")]
    )
    md = to_markdown(_result(transcript=transcript))
    assert "**Speaker 1**: おはようございます" in md


def test_slack_blocks_structure():
    blocks = to_slack_blocks(_result())
    assert blocks[0]["type"] == "header"
    texts = [b["text"]["text"] for b in blocks if b["type"] == "section"]
    assert any("決定事項" in t for t in texts)
    assert any("アクションアイテム" in t for t in texts)
