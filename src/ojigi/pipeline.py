"""音声 → Scribe(文字起こし) → Summarizer(要約) → Translator(英訳) のオーケストレーション。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .auth import TokenProvider
from .clients.scribe import ScribeClient
from .clients.summarizer import SummarizerClient
from .clients.translator import TranslatorClient
from .models import ActionItem, MinutesResult, Summary, UsageRecord
from .settings import Settings


def run_pipeline(
    audio_path: Path,
    settings: Settings,
    mode: str = "fast",
    full_translate: bool = False,
    progress=None,
) -> MinutesResult:
    """議事録生成のE2Eパイプライン。progress は step名を受け取るコールバック(任意)。"""

    def notify(step: str) -> None:
        if progress:
            progress(step)

    tokens = TokenProvider(settings)
    scribe = ScribeClient(settings, tokens)
    summarizer = SummarizerClient(settings, tokens)
    translator = TranslatorClient(settings, tokens)
    usage: list[UsageRecord] = []

    try:
        notify("Scribe: 文字起こし中…")
        transcript = scribe.transcribe(audio_path, mode=mode)

        notify("Summarizer: 要約・アクションアイテム抽出中…")
        summary = summarizer.summarize(transcript)

        notify("Translator: 要約を英訳中…")
        summary_en = _translate_summary(translator, summary)

        full_translation = None
        if full_translate:
            notify("Translator: 全文を英訳中…")
            full_translation = translator.translate(transcript.text, source="ja", target="en")

        usage = scribe.usage_records + summarizer.usage_records + translator.usage_records
        return MinutesResult(
            source_file=audio_path.name,
            created_at=datetime.now(),
            transcript=transcript,
            summary=summary,
            summary_en=summary_en,
            full_translation=full_translation,
            usage_records=usage,
        )
    finally:
        scribe.close()
        summarizer.close()
        translator.close()


def _translate_summary(translator: TranslatorClient, summary: Summary) -> Summary:
    """要約の各要素を英訳する。1リクエストにまとめてコストと往復を抑える。"""
    action_texts = [item.description for item in summary.action_items]
    texts = [summary.overview, *summary.key_points, *summary.decisions, *action_texts]
    non_empty_indices = [i for i, t in enumerate(texts) if t.strip()]
    if not non_empty_indices:
        return Summary()

    translated = translator.translate_batch([texts[i] for i in non_empty_indices], "ja", "en")
    result = [""] * len(texts)
    for idx, text in zip(non_empty_indices, translated):
        result[idx] = text

    n_points = len(summary.key_points)
    n_decisions = len(summary.decisions)
    return Summary(
        overview=result[0],
        key_points=result[1 : 1 + n_points],
        decisions=result[1 + n_points : 1 + n_points + n_decisions],
        action_items=[
            ActionItem(description=text, assignee=item.assignee, due=item.due)
            for text, item in zip(result[1 + n_points + n_decisions :], summary.action_items)
        ],
    )
