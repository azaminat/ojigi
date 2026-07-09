"""伝言ゲームの世代オーケストレータ。

モード:
  - roundtrip (実験A): ja→en→ja を繰り返す（Translator単体）。劣化・収束を観測
  - summary   (実験B): 要約(前世代) を繰り返す（Summarizer単体）。不動点収束＝頑健性のコントロール群
  - full      (実験C): 音声→Scribe→(要約)→翻訳往復→TTS→… 別モジュール(full.py)で実装予定

各世代は metrics.evaluate_generation で seed/前世代と照合。usage は BaseClient が
usage_ledger.jsonl に自動記録し、trial ごとに集計する。--trials で複数回まわし分散を出す。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from ..auth import TokenProvider
from ..clients.summarizer import SummarizerClient
from ..clients.translator import TranslatorClient
from ..models import UsageRecord
from ..settings import Settings
from . import metrics as M

Progress = Callable[[str], None]


def load_seed(path: str | Path) -> str:
    """種テキスト(.md)から会話本体（speaker_ 行）だけを抽出する。"""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    convo = [ln for ln in lines if ln.strip().startswith("speaker_")]
    if convo:
        return "\n".join(convo)
    # speaker_ 行が無ければ最初の "---" 以降を本体とみなす
    text = "\n".join(lines)
    parts = re.split(r"^---\s*$", text, maxsplit=1, flags=re.MULTILINE)
    return (parts[-1] if len(parts) > 1 else text).strip()


# ---------------------------------------------------------------------------
# 結果コンテナ
# ---------------------------------------------------------------------------


@dataclass
class Trial:
    trial: int
    generations: list[M.GenerationMetrics]
    usage_records: list[UsageRecord] = field(default_factory=list)
    intermediates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial": self.trial,
            "generations": [g.to_dict() for g in self.generations],
            "intermediates": self.intermediates,
            "usage": [u.model_dump(mode="json") for u in self.usage_records],
        }


@dataclass
class ExperimentResult:
    mode: str
    seed_text: str
    generations: int
    trials: list[Trial]

    def aggregate(self) -> list[dict[str, Any]]:
        """世代ごとにトライアル横断の mean/min/max を出す（分散バンド用）。"""
        rows: list[dict[str, Any]] = []
        for gen in range(self.generations + 1):
            cells = [t.generations[gen] for t in self.trials if gen < len(t.generations)]
            if not cells:
                continue
            rows.append(
                {
                    "generation": gen,
                    "n": len(cells),
                    **self._stat("cer_vs_seed", cells),
                    **self._stat("semantic_vs_seed", cells),
                    **self._stat("cer_vs_prev", cells),
                    **self._stat("survival_rate", cells),
                    **self._stat("chars", cells),
                }
            )
        return rows

    @staticmethod
    def _stat(attr: str, cells: list[M.GenerationMetrics]) -> dict[str, Any]:
        vals = [getattr(c, attr) for c in cells if getattr(c, attr) is not None]
        if not vals:
            return {f"{attr}_mean": None, f"{attr}_min": None, f"{attr}_max": None}
        return {
            f"{attr}_mean": mean(vals),
            f"{attr}_min": min(vals),
            f"{attr}_max": max(vals),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "generations": self.generations,
            "trials": [t.to_dict() for t in self.trials],
            "aggregate": self.aggregate(),
        }


# ---------------------------------------------------------------------------
# 世代列の生成（テキストのみ。評価は後段で一括）
# ---------------------------------------------------------------------------


def _seq_roundtrip(
    seed: str, translator: TranslatorClient, generations: int, notify: Progress
) -> tuple[list[str], list[dict[str, Any]]]:
    texts, inter = [seed], [{}]
    prev = seed
    for g in range(1, generations + 1):
        notify(f"[roundtrip] gen {g}/{generations}: ja→en")
        en = translator.translate(prev, source="ja", target="en")
        notify(f"[roundtrip] gen {g}/{generations}: en→ja")
        ja = translator.translate(en, source="en", target="ja")
        texts.append(ja)
        inter.append({"en": en})
        prev = ja
    return texts, inter


def _seq_summary(
    seed: str, summarizer: SummarizerClient, generations: int, notify: Progress
) -> tuple[list[str], list[dict[str, Any]]]:
    texts, inter = [seed], [{}]
    prev = seed
    for g in range(1, generations + 1):
        notify(f"[summary] gen {g}/{generations}: 要約")
        s = summarizer.summarize_text(prev, task="summary")
        texts.append(s)
        inter.append({})
        prev = s
        if not s:
            break
    return texts, inter


# ---------------------------------------------------------------------------
# 実験実行
# ---------------------------------------------------------------------------


def run_experiment(
    mode: str,
    seed_text: str,
    settings: Settings,
    *,
    generations: int = 10,
    trials: int = 3,
    factset: M.FactSet | None = None,
    with_semantic: bool = True,
    with_summary: bool = False,
    progress: Progress | None = None,
) -> ExperimentResult:
    if mode == "full":
        from .full import run_full_experiment  # 遅延import（循環回避・TTS依存の分離）

        return run_full_experiment(
            seed_text,
            settings,
            generations=generations,
            trials=trials,
            factset=factset,
            with_semantic=with_semantic,
            with_summary=with_summary,
            progress=progress,
        )

    notify: Progress = progress or (lambda _s: None)
    tokens = TokenProvider(settings)
    result_trials: list[Trial] = []

    for t in range(1, trials + 1):
        notify(f"=== trial {t}/{trials} (mode={mode}) ===")
        if mode == "roundtrip":
            client: Any = TranslatorClient(settings, tokens)
            texts, inter = _seq_roundtrip(seed_text, client, generations, notify)
        elif mode == "summary":
            client = SummarizerClient(settings, tokens)
            texts, inter = _seq_summary(seed_text, client, generations, notify)
        else:
            raise ValueError(f"未対応モード: {mode!r}（full は full.py で実装）")

        try:
            gens: list[M.GenerationMetrics] = []
            for i, txt in enumerate(texts):
                prev = texts[i - 1] if i > 0 else None
                gens.append(
                    M.evaluate_generation(
                        i, txt, seed_text, factset, prev_text=prev, with_semantic=with_semantic
                    )
                )
            result_trials.append(
                Trial(
                    trial=t,
                    generations=gens,
                    usage_records=list(client.usage_records),
                    intermediates=inter,
                )
            )
        finally:
            client.close()

    return ExperimentResult(
        mode=mode, seed_text=seed_text, generations=generations, trials=result_trials
    )
