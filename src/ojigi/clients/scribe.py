"""Scribe API（文字起こし）クライアント。"""

from __future__ import annotations

from pathlib import Path

from ..models import Transcript, TranscriptSegment
from ..settings import Settings
from ..uploader import to_fetchable_url
from .base import BaseClient


class ScribeClient(BaseClient):
    api_name = "scribe"

    def transcribe(self, audio: str | Path, mode: str = "fast", language: str = "ja-JP") -> Transcript:
        if mode != "fast":
            raise NotImplementedError(
                "batch モードは S3 入出力前提のジョブAPIです。現状は fast のみ対応（Fast上限: 100MB/2時間）。"
            )
        fetchable = to_fetchable_url(audio, self._settings)
        try:
            data = self._request(
                "POST",
                "/aiservices/scribe/transcribe",
                json={
                    "file": fetchable.url,
                    "config": {
                        "language": language,
                        "timestamps": True,
                        # 話者分離は ja-JP 非対応（400 INVALID_INPUT になる。2026-07-03実測）
                        "diarization": language.startswith("en"),
                        "segmentation_mode": "auto",
                        "output_format": "json",
                    },
                },
            )
        finally:
            fetchable.cleanup()
        return self._parse(data, language)

    @staticmethod
    def _parse(data: dict, language: str) -> Transcript:
        result = data.get("result") or {}
        segments = [
            TranscriptSegment(
                speaker=seg.get("speaker"),
                start=seg.get("start"),
                end=seg.get("end"),
                text=seg.get("text", ""),
            )
            for seg in result.get("segments") or []
        ]
        text = result.get("text_display") or result.get("text_lexical") or ""
        if not text and segments:
            text = "\n".join(seg.text for seg in segments)
        return Transcript(text=text, language=language, segments=segments, raw=data)
