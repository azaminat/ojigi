"""伝言ゲーム（telephone）のメトリクス・レポート・種読み込みのテスト。

意味類似度（sentence-transformers）は重いため with_semantic=False で回避し、
CER・サバイバル判定・レポート整形・seed抽出のロジックを検証する。
"""

import json

from ojigi.telephone.loop import load_seed
from ojigi.telephone.metrics import FactSet, cer, evaluate_generation, normalize_for_cer
from ojigi.telephone import report

FACTS = {
    "decisions": [
        {"id": "D1", "label": "リリース7月13日", "keywords": ["7月13日", "July 13"]},
    ],
    "action_items": [
        {"id": "A1", "label": "田中: 負荷テスト", "keywords": ["負荷テスト", "load test", "1,200"]},
    ],
    "proper_nouns": [
        {"id": "P1", "label": "大福", "keywords": ["大福", "ダイフク", "Daifuku"]},
    ],
    "numbers": [
        {"id": "N1", "label": "月3万円", "keywords": ["3万円", "30,000"]},
    ],
}


def _factset(tmp_path) -> FactSet:
    p = tmp_path / "facts.json"
    p.write_text(json.dumps(FACTS, ensure_ascii=False), encoding="utf-8")
    return FactSet.from_json(p)


# --- CER ---------------------------------------------------------------


def test_normalize_strips_punct_and_normalizes_width():
    assert normalize_for_cer("７月13日、確定。") == "7月13日確定"


def test_cer_identical_is_zero():
    assert cer("会議は7月13日", "会議は7月13日") == 0.0


def test_cer_detects_difference():
    assert cer("会議は7月13日", "会議は8月20日") > 0.0


def test_cer_empty_reference():
    assert cer("", "") == 0.0
    assert cer("", "なにか") == 1.0


# --- FactSet / サバイバル ------------------------------------------------


def test_factset_loads_all_categories(tmp_path):
    fs = _factset(tmp_path)
    assert len(fs.facts) == 4
    assert {f.category for f in fs.facts} == {"decisions", "action_items", "proper_nouns", "numbers"}


def test_survival_full(tmp_path):
    fs = _factset(tmp_path)
    text = "7月13日にリリース。田中が負荷テスト(1,200ユーザー)。大福プロジェクト。月3万円承認。"
    s = fs.survival(text)
    assert s.alive_count == 4
    assert s.rate == 1.0
    assert s.dead_facts() == []


def test_survival_partial_and_katakana(tmp_path):
    fs = _factset(tmp_path)
    # 大福→カタカナ「ダイフク」でも生存扱い。田中の負荷テストは欠落。
    text = "ダイフクの件。7月13日リリース。予算は30,000円。"
    s = fs.survival(text)
    alive = {f.id for f in fs.facts if s.alive[f.id]}
    assert alive == {"D1", "P1", "N1"}
    assert [f.id for f in s.dead_facts()] == ["A1"]
    assert s.rate == 0.75


def test_survival_number_comma_normalization(tmp_path):
    fs = _factset(tmp_path)
    # "1200"（カンマなし）でも keyword "1,200" にマッチする
    s = fs.survival("負荷テストは1200ユーザーで実施")
    assert s.alive["A1"] is True


def test_by_category(tmp_path):
    fs = _factset(tmp_path)
    s = fs.survival("7月13日のみ言及")
    cats = s.by_category()
    assert cats["decisions"] == {"alive": 1, "total": 1}
    assert cats["proper_nouns"] == {"alive": 0, "total": 1}


# --- evaluate_generation ------------------------------------------------


def test_evaluate_generation_vs_seed_and_prev(tmp_path):
    fs = _factset(tmp_path)
    seed = "7月13日にリリース。田中が負荷テスト。大福。月3万円。"
    m = evaluate_generation(1, seed, seed, fs, prev_text=seed, with_semantic=False)
    assert m.cer_vs_seed == 0.0
    assert m.cer_vs_prev == 0.0
    assert m.survival_rate == 1.0
    assert m.semantic_vs_seed is None  # with_semantic=False


def test_evaluate_generation_degraded(tmp_path):
    fs = _factset(tmp_path)
    seed = "7月13日にリリース。田中が負荷テスト。大福。月3万円。"
    m = evaluate_generation(2, "会議をしました", seed, fs, with_semantic=False)
    assert m.cer_vs_seed > 0.5
    assert m.survival_rate == 0.0
    assert set(m.dead_fact_ids) == {"D1", "A1", "P1", "N1"}


# --- report -------------------------------------------------------------


def _fake_result() -> dict:
    return {
        "mode": "full",
        "generations": 2,
        "trials": [
            {
                "trial": 1,
                "generations": [
                    {"generation": 0, "text": "大福プロジェクトの定例", "dead_fact_ids": []},
                    {"generation": 1, "text": "O Fukuプロジェクト", "dead_fact_ids": ["P1"]},
                    {"generation": 2, "text": "会議です", "dead_fact_ids": ["P1", "D1"]},
                ],
                "intermediates": [{}, {"asr": "ダイフクの定例", "en": "Daifuku project"}, {}],
            }
        ],
    }


def test_text_evolution():
    rows = report.text_evolution(_fake_result())
    assert rows[0][0] == 0
    assert "大福" in rows[0][1]


def test_keyword_trace_finds_and_reports_loss():
    rows = report.keyword_trace(_fake_result(), ["大福", "ダイフク", "Daifuku"])
    assert rows[0]["text"] != "（消失）"  # gen0 に大福あり
    assert rows[1].get("asr") and "ダイフク" in rows[1]["asr"]  # 文字起こしにはダイフクが残る
    assert rows[2]["text"] == "（消失）"  # gen2 で消失


def test_survival_timeline():
    tl = report.survival_timeline(_fake_result())
    assert tl["P1"] == 1
    assert tl["D1"] == 2


# --- load_seed ----------------------------------------------------------


def test_load_seed_extracts_speaker_lines(tmp_path):
    p = tmp_path / "seed.md"
    p.write_text(
        "# タイトル\n\n説明文\n\n---\n\nspeaker_1: こんにちは。\nspeaker_2: どうも。\n",
        encoding="utf-8",
    )
    seed = load_seed(p)
    assert seed == "speaker_1: こんにちは。\nspeaker_2: どうも。"


def test_load_seed_fallback_after_hr(tmp_path):
    p = tmp_path / "seed.md"
    p.write_text("説明\n\n---\n\n本文テキストです。", encoding="utf-8")
    assert load_seed(p) == "本文テキストです。"
