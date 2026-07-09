"""Summarizer API（要約・アクションアイテム抽出）クライアント。"""

from __future__ import annotations

import re
from typing import Any

from ..models import ActionItem, Summary, Transcript
from .base import BaseClient

_FAST_INPUT_LIMIT_BYTES = 96 * 1024  # Fast モードの入力上限


class SummarizerClient(BaseClient):
    api_name = "summarizer"

    def summarize(self, transcript: Transcript, language: str = "ja-JP") -> Summary:
        text = self._to_speaker_text(transcript)
        if len(text.encode("utf-8")) > _FAST_INPUT_LIMIT_BYTES:
            raise ValueError(
                f"入力が Fast モードの上限 96KB を超えています（{len(text.encode('utf-8'))} bytes）。"
                "音声を分割するか Batch モードを検討してください。"
            )
        data = self._request(
            "POST",
            "/aiservices/summarizer/summarize",
            json={
                "input": {"text": text},
                "config": {
                    "summary_type": "conversation",
                    "task": "full_summary",
                    "language": language,
                    "output_format": "json",
                },
            },
        )
        return self._parse(data)

    def summarize_text(self, text: str, task: str = "summary", language: str = "ja-JP") -> str:
        """任意テキストを要約し、result のテキスト1本を返す（伝言ゲーム連鎖用）。
        usage は BaseClient が ledger に記録する。"""
        data = self._request(
            "POST",
            "/aiservices/summarizer/summarize",
            json={
                "input": {"text": text},
                "config": {
                    "summary_type": "conversation",
                    "task": task,
                    "language": language,
                    "output_format": "json",
                },
            },
        )
        result = data.get("result") or {}
        for key in ("summary_text", "summary", "text", "full_summary", "recap"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _to_speaker_text(transcript: Transcript) -> str:
        """Summarizer は話者情報を "Speaker A: 発言" 形式の文字列で受け取る。"""
        if transcript.segments and any(seg.speaker for seg in transcript.segments):
            return "\n".join(
                f"{seg.speaker or 'Speaker'}: {seg.text}" for seg in transcript.segments if seg.text
            )
        return transcript.text

    @classmethod
    def _parse(cls, data: dict[str, Any]) -> Summary:
        """full_summary は「# Recap / # Summary / # Action Items」のMarkdown文字列1本で返る
        （スパイク実測 2026-07-03）。セクションを分解して構造化する。"""
        result = data.get("result") or {}

        text = ""
        for key in ("full_summary", "summary_text", "summary", "text", "recap"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                text = value.strip()
                break

        sections = cls._split_sections(text)
        overview = sections.get("recap") or sections.get("summary") or text
        key_points = (
            cls._summary_to_points(sections.get("summary", "")) if sections.get("recap") else []
        )
        action_items = cls._parse_action_items(sections.get("action items", ""))

        return Summary(overview=overview, key_points=key_points, action_items=action_items, raw=data)

    @staticmethod
    def _split_sections(text: str) -> dict[str, str]:
        """"# 見出し" 単位で分割する。見出しが無ければ空dict。"""
        sections: dict[str, str] = {}
        current: str | None = None
        buf: list[str] = []
        for line in text.splitlines():
            m = re.match(r"^#\s+(.+)$", line.strip())
            if m:
                if current:
                    sections[current] = "\n".join(buf).strip()
                current = m.group(1).strip().lower()
                buf = []
            else:
                buf.append(line)
        if current:
            sections[current] = "\n".join(buf).strip()
        return sections

    @staticmethod
    def _summary_to_points(section: str) -> list[str]:
        """"## トピック見出し\\n本文" の繰り返しを「**見出し** 本文」の箇条書きに変換する。"""
        points: list[str] = []
        title: str | None = None
        body: list[str] = []

        def flush() -> None:
            if title or body:
                head = f"**{title}** " if title else ""
                points.append(head + " ".join(body))

        for line in section.splitlines():
            line = line.strip()
            m = re.match(r"^#+\s+(.+)$", line)
            if m:
                flush()
                title, body = m.group(1), []
            elif line:
                body.append(line)
        flush()
        return points

    @staticmethod
    def _parse_action_items(text: str) -> list[ActionItem]:
        """"**担当者**\\n- 内容" 形式（スパイク実測）をパースする。期限は内容文に含まれる。
        話者分離が使えない日本語では担当者が "Unknown" になることがあるため None に落とす。"""
        items: list[ActionItem] = []
        assignee: str | None = None
        for line in text.splitlines():
            line = line.strip()
            m = re.match(r"^\*\*(.+?)\*\*$", line)
            if m:
                assignee = m.group(1)
                if assignee.lower() in ("unknown", "不明"):
                    assignee = None
            elif re.match(r"^[-*・]", line):
                items.append(
                    ActionItem(description=re.sub(r"^[-*・]\s*", "", line), assignee=assignee)
                )
        return items
