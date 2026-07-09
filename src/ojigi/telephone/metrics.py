"""伝言ゲームの劣化指標。

3つの観点で世代間の情報劣化を定量化する:
  1. CER（文字誤り率）      … 第0世代との字面のズレ。jiwer + NFKC正規化
  2. 意味類似度             … 多言語文埋め込みのcos類似。「字面は変わったが意味は保持」を捉える
  3. 決定サバイバル率        … ground_truth の決定/アクション/固有名詞/数値が何世代まで生存するか

重い依存（jiwer, sentence-transformers）は関数内で遅延importし、
本体CLI（議事録生成）には影響させない。
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# CER（文字誤り率）
# ---------------------------------------------------------------------------

# run_cer.py と同じ正規化方針（句読点・空白除去、全角半角統一）。記事の再現性のため一致させる。
_CER_STRIP = re.compile(r"[、。,\.！!？\?・「」（）\(\)\s]")


def normalize_for_cer(text: str) -> str:
    return _CER_STRIP.sub("", unicodedata.normalize("NFKC", text))


def cer(reference: str, hypothesis: str) -> float:
    """第0世代 reference に対する hypothesis のCER（0=完全一致）。"""
    import jiwer  # 遅延import

    ref, hyp = normalize_for_cer(reference), normalize_for_cer(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return float(jiwer.cer(ref, hyp))


# ---------------------------------------------------------------------------
# 意味類似度（多言語文埋め込み cos 類似）
# ---------------------------------------------------------------------------

_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_model: Any = None


def _get_model() -> Any:
    """モデルはプロセス内で1度だけロードしてキャッシュする（初回のみDL）。"""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer  # 遅延import
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "意味類似度には sentence-transformers が必要です。"
                "`uv sync` で dev 依存を導入してください。"
            ) from e
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def semantic_similarity(text_a: str, text_b: str) -> float:
    """2テキストの意味的近さ（cos類似, -1〜1。通常0〜1）。日英跨ぎも可。"""
    from sentence_transformers import util  # 遅延import

    model = _get_model()
    emb = model.encode([text_a, text_b], convert_to_tensor=True, normalize_embeddings=True)
    return float(util.cos_sim(emb[0], emb[1]).item())


# ---------------------------------------------------------------------------
# 決定サバイバル率（ground_truth ファクトの生存判定）
# ---------------------------------------------------------------------------

# 照合用の畳み込み: NFKC → 小文字化 → 空白とカンマ除去（"1,200"→"1200", "July 13"→"july13"）
_FOLD_STRIP = re.compile(r"[\s,]")


def _fold(text: str) -> str:
    return _FOLD_STRIP.sub("", unicodedata.normalize("NFKC", text).casefold())


@dataclass
class Fact:
    id: str
    label: str
    category: str
    keywords: list[str]

    def is_alive(self, folded_haystack: str) -> bool:
        """keywords のいずれかが（畳み込み後）本文に出現すれば生存とみなす。"""
        return any(_fold(kw) in folded_haystack for kw in self.keywords if kw)


@dataclass
class FactSet:
    facts: list[Fact]

    @classmethod
    def from_json(cls, path: str | Path) -> FactSet:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        facts: list[Fact] = []
        for category in ("decisions", "action_items", "proper_nouns", "numbers"):
            for item in data.get(category, []):
                facts.append(
                    Fact(
                        id=item["id"],
                        label=item["label"],
                        category=category,
                        keywords=list(item.get("keywords", [])),
                    )
                )
        return cls(facts=facts)

    def survival(self, text: str) -> "SurvivalResult":
        folded = _fold(text)
        alive = {f.id: f.is_alive(folded) for f in self.facts}
        return SurvivalResult(facts=self.facts, alive=alive)


@dataclass
class SurvivalResult:
    facts: list[Fact]
    alive: dict[str, bool]

    @property
    def total(self) -> int:
        return len(self.facts)

    @property
    def alive_count(self) -> int:
        return sum(1 for v in self.alive.values() if v)

    @property
    def rate(self) -> float:
        return self.alive_count / self.total if self.total else 1.0

    def by_category(self) -> dict[str, dict[str, int]]:
        """カテゴリ別 {alive, total}。"""
        out: dict[str, dict[str, int]] = {}
        for f in self.facts:
            bucket = out.setdefault(f.category, {"alive": 0, "total": 0})
            bucket["total"] += 1
            if self.alive[f.id]:
                bucket["alive"] += 1
        return out

    def dead_facts(self) -> list[Fact]:
        return [f for f in self.facts if not self.alive[f.id]]


# ---------------------------------------------------------------------------
# 1世代分のメトリクスまとめ
# ---------------------------------------------------------------------------


@dataclass
class GenerationMetrics:
    generation: int
    text: str
    chars: int = 0
    cer_vs_seed: float | None = None
    semantic_vs_seed: float | None = None
    cer_vs_prev: float | None = None  # 前世代との差（0に近づく＝収束）
    semantic_vs_prev: float | None = None
    survival_rate: float | None = None
    survival_alive: int | None = None
    survival_total: int | None = None
    survival_by_category: dict[str, dict[str, int]] = field(default_factory=dict)
    dead_fact_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "chars": self.chars,
            "cer_vs_seed": self.cer_vs_seed,
            "semantic_vs_seed": self.semantic_vs_seed,
            "cer_vs_prev": self.cer_vs_prev,
            "semantic_vs_prev": self.semantic_vs_prev,
            "survival_rate": self.survival_rate,
            "survival_alive": self.survival_alive,
            "survival_total": self.survival_total,
            "survival_by_category": self.survival_by_category,
            "dead_fact_ids": self.dead_fact_ids,
            "text": self.text,
        }


def evaluate_generation(
    generation: int,
    text: str,
    seed_text: str,
    factset: FactSet | None = None,
    *,
    prev_text: str | None = None,
    with_semantic: bool = True,
) -> GenerationMetrics:
    """1世代のテキストを seed（および任意で前世代）と照合してメトリクス化する。"""
    m = GenerationMetrics(generation=generation, text=text, chars=len(text))
    m.cer_vs_seed = cer(seed_text, text)
    if prev_text is not None:
        m.cer_vs_prev = cer(prev_text, text)
    if with_semantic:
        m.semantic_vs_seed = semantic_similarity(seed_text, text)
        if prev_text is not None:
            m.semantic_vs_prev = semantic_similarity(prev_text, text)
    if factset is not None:
        s = factset.survival(text)
        m.survival_rate = s.rate
        m.survival_alive = s.alive_count
        m.survival_total = s.total
        m.survival_by_category = s.by_category()
        m.dead_fact_ids = [f.id for f in s.dead_facts()]
    return m
