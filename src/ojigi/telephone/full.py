"""実験C: フル伝言ゲーム。

1世代の処理: text → TTS(Polly) → Scribe(文字起こし) → [要約(任意)] → 翻訳往復(ja→en→ja)
→ 次世代テキスト。Zoom 3API全部＋TTSを通す総合劣化系。誤変換ハイライトはここから採取する。

`--with-summary` で毎世代に要約を挟める（既定はオフ。要約は不動点収束＝実験Bで別途検証済のため、
Cでは音声化＋翻訳の複合劣化を主に観測する）。
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from ..auth import TokenProvider
from ..clients.scribe import ScribeClient
from ..clients.summarizer import SummarizerClient
from ..clients.translator import TranslatorClient
from ..models import UsageRecord
from ..settings import Settings
from . import metrics as M
from . import tts
from .loop import ExperimentResult, Progress, Trial


def _seq_full(
    seed: str,
    scribe: ScribeClient,
    translator: TranslatorClient,
    summarizer: SummarizerClient | None,
    settings: Settings,
    generations: int,
    tmp_dir: Path,
    notify: Progress,
) -> tuple[list[str], list[dict[str, Any]]]:
    texts, inter = [seed], [{}]
    prev = seed
    for g in range(1, generations + 1):
        notify(f"[full] gen {g}/{generations}: TTS")
        mp3 = tts.synthesize(prev, settings, tmp_dir)
        try:
            notify(f"[full] gen {g}/{generations}: Scribe")
            asr = scribe.transcribe(mp3).text
        finally:
            mp3.unlink(missing_ok=True)

        cur = asr
        if summarizer is not None:
            notify(f"[full] gen {g}/{generations}: 要約")
            cur = summarizer.summarize_text(cur, task="summary") or asr

        notify(f"[full] gen {g}/{generations}: 翻訳往復 ja→en→ja")
        en = translator.translate(cur, source="ja", target="en")
        ja = translator.translate(en, source="en", target="ja")

        texts.append(ja)
        inter.append({"asr": asr, "en": en})
        prev = ja
    return texts, inter


def run_full_experiment(
    seed_text: str,
    settings: Settings,
    *,
    generations: int = 8,
    trials: int = 3,
    factset: M.FactSet | None = None,
    with_semantic: bool = True,
    with_summary: bool = False,
    progress: Progress | None = None,
) -> ExperimentResult:
    notify: Progress = progress or (lambda _s: None)
    tokens = TokenProvider(settings)
    result_trials: list[Trial] = []

    for t in range(1, trials + 1):
        notify(f"=== trial {t}/{trials} (mode=full) ===")
        scribe = ScribeClient(settings, tokens)
        translator = TranslatorClient(settings, tokens)
        summarizer = SummarizerClient(settings, tokens) if with_summary else None
        tmp_dir = Path(tempfile.mkdtemp(prefix="ojigi_telephone_"))
        try:
            texts, inter = _seq_full(
                seed_text, scribe, translator, summarizer, settings, generations, tmp_dir, notify
            )
            gens: list[M.GenerationMetrics] = []
            for i, txt in enumerate(texts):
                prev = texts[i - 1] if i > 0 else None
                gens.append(
                    M.evaluate_generation(
                        i, txt, seed_text, factset, prev_text=prev, with_semantic=with_semantic
                    )
                )
            usage: list[UsageRecord] = list(scribe.usage_records) + list(translator.usage_records)
            if summarizer is not None:
                usage += list(summarizer.usage_records)
            result_trials.append(
                Trial(trial=t, generations=gens, usage_records=usage, intermediates=inter)
            )
        finally:
            scribe.close()
            translator.close()
            if summarizer is not None:
                summarizer.close()
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return ExperimentResult(
        mode="full", seed_text=seed_text, generations=generations, trials=result_trials
    )
