"""ojigi のデータモデル定義。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UsageRecord(BaseModel):
    """API呼び出し1回分の使用量レコード。usage_ledger.jsonl に追記される。"""

    api: str  # "scribe" | "summarizer" | "translator"
    endpoint: str
    timestamp: datetime
    duration_sec: float = 0.0  # API呼び出しの所要時間
    input_chars: int = 0
    output_chars: int = 0
    audio_seconds: float = 0.0  # Scribe用: 処理した音声の長さ
    raw_usage: dict[str, Any] = Field(default_factory=dict)  # レスポンスのusageをそのまま保存


class TranscriptSegment(BaseModel):
    speaker: str | None = None
    start: float | None = None
    end: float | None = None
    text: str


class Transcript(BaseModel):
    text: str
    language: str = "ja"
    segments: list[TranscriptSegment] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class ActionItem(BaseModel):
    description: str
    assignee: str | None = None
    due: str | None = None


class Summary(BaseModel):
    overview: str = ""
    key_points: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class BilingualText(BaseModel):
    ja: str
    en: str = ""


class MinutesResult(BaseModel):
    """パイプライン全体の成果物。render.py がこれをMarkdown/Slackに整形する。"""

    source_file: str
    created_at: datetime
    transcript: Transcript
    summary: Summary
    summary_en: Summary | None = None  # 英訳された要約
    full_translation: str | None = None  # --full-translate 時のみ
    usage_records: list[UsageRecord] = Field(default_factory=list)
