"""ojigi CLI。

- `ojigi minutes <audio>`   録音を置くだけで日英バイリンガル議事録+コストレシート
- `ojigi telephone <seed>`  AI伝言ゲーム: 3APIを繰り返し通し情報劣化を可視化（検証機能）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

# Windowsのレガシーコンソール(cp932)でも絵文字入り出力が落ちないようにする
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from .cost import build_receipt_table, estimate_cost, load_pricing
from .pipeline import run_pipeline
from .render import to_markdown, to_slack_blocks
from .settings import get_settings
from .slack import post_to_slack

app = typer.Typer(add_completion=False, help="Zoom AI Services を使う議事録CLI + 伝言ゲーム検証")
console = Console()


@app.command()
def minutes(
    audio_file: Path = typer.Argument(..., exists=True, readable=True, help="録音ファイル(m4a/mp3/wav等)"),
    slack: bool = typer.Option(False, "--slack", help="Slackに要約を通知する"),
    full_translate: bool = typer.Option(False, "--full-translate", help="全文も英訳する(コスト増)"),
    mode: str = typer.Option("fast", "--mode", help="Scribeのモード: fast | batch"),
    output_dir: Path = typer.Option(Path("output"), "--output-dir", help="議事録の出力先"),
) -> None:
    """録音 → 日英議事録 + Slack通知 + コストレシート。"""
    settings = get_settings()
    if not settings.zoom_api_key or not settings.zoom_api_secret:
        console.print("[red]ZOOM_API_KEY / ZOOM_API_SECRET が未設定です。.env を確認してください。[/red]")
        raise typer.Exit(1)

    with console.status("[bold green]処理中…") as status:
        result = run_pipeline(
            audio_file,
            settings,
            mode=mode,
            full_translate=full_translate,
            progress=lambda step: status.update(f"[bold green]{step}"),
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{audio_file.stem}_minutes.md"
    md_path.write_text(to_markdown(result), encoding="utf-8")
    console.print(f"✅ 議事録を出力しました: [bold]{md_path}[/bold]")

    if slack:
        if not settings.slack_webhook_url:
            console.print("[yellow]SLACK_WEBHOOK_URL が未設定のためSlack通知をスキップしました。[/yellow]")
        else:
            post_to_slack(settings.slack_webhook_url, to_slack_blocks(result))
            console.print("✅ Slackに通知しました")

    lines = estimate_cost(result.usage_records, load_pricing())
    console.print(build_receipt_table(lines))


@app.command()
def telephone(
    seed_file: Path = typer.Argument(..., exists=True, readable=True, help="種テキスト(.md/.txt)"),
    mode: str = typer.Option("roundtrip", "--mode", "-m", help="roundtrip(翻訳往復) | summary(要約連鎖) | full(フル伝言)"),
    generations: int = typer.Option(10, "--generations", "-g", help="世代数"),
    trials: int = typer.Option(3, "--trials", "-t", help="試行回数(分散バンド用)"),
    facts_file: Path | None = typer.Option(None, "--facts", exists=True, help="サバイバル率判定用ファクトJSON"),
    with_summary: bool = typer.Option(False, "--with-summary", help="full時に毎世代で要約を挟む"),
    no_semantic: bool = typer.Option(False, "--no-semantic", help="意味類似度をスキップ(高速)"),
    output_dir: Path = typer.Option(Path("output"), "--output-dir", help="結果JSONの出力先"),
) -> None:
    """AI伝言ゲーム: 3APIを繰り返し通し、情報がどこでどう劣化/収束するかを可視化する。"""
    from .telephone.loop import load_seed, run_experiment
    from .telephone.metrics import FactSet

    if mode not in ("roundtrip", "summary", "full"):
        console.print(f"[red]未対応のmode: {mode}（roundtrip | summary | full）[/red]")
        raise typer.Exit(1)

    settings = get_settings()
    if not settings.zoom_api_key or not settings.zoom_api_secret:
        console.print("[red]ZOOM_API_KEY / ZOOM_API_SECRET が未設定です。.env を確認してください。[/red]")
        raise typer.Exit(1)

    seed_text = load_seed(seed_file)
    factset = FactSet.from_json(facts_file) if facts_file else None
    console.print(
        f"🎙️ 伝言ゲーム開始 mode=[bold]{mode}[/bold] 世代={generations} 試行={trials} "
        f"seed={len(seed_text)}字" + (f" facts={len(factset.facts)}件" if factset else "")
    )

    with console.status("[bold green]実行中…") as status:
        result = run_experiment(
            mode,
            seed_text,
            settings,
            generations=generations,
            trials=trials,
            factset=factset,
            with_semantic=not no_semantic,
            with_summary=with_summary,
            progress=lambda step: status.update(f"[bold green]{step}"),
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"telephone_{mode}.json"
    json_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    console.print(f"✅ 結果を出力しました: [bold]{json_path}[/bold]")

    _print_aggregate(result.aggregate(), has_facts=factset is not None, has_semantic=not no_semantic)

    all_usage = [u for t in result.trials for u in t.usage_records]
    lines = estimate_cost(all_usage, load_pricing())
    console.print(build_receipt_table(lines))


def _print_aggregate(rows: list[dict], *, has_facts: bool, has_semantic: bool) -> None:
    table = Table(title="世代別 劣化メトリクス（試行平均）")
    table.add_column("世代", justify="right")
    table.add_column("文字数", justify="right")
    table.add_column("CER(vs種)", justify="right")
    table.add_column("CER(vs前世代)", justify="right")
    if has_semantic:
        table.add_column("意味類似(vs種)", justify="right")
    if has_facts:
        table.add_column("生存率", justify="right")

    def fmt(v: float | None, pct: bool = False) -> str:
        if v is None:
            return "-"
        return f"{v:.1%}" if pct else f"{v:.3f}"

    for r in rows:
        cells = [
            str(r["generation"]),
            f"{r['chars_mean']:.0f}" if r.get("chars_mean") is not None else "-",
            fmt(r.get("cer_vs_seed_mean")),
            fmt(r.get("cer_vs_prev_mean")),
        ]
        if has_semantic:
            cells.append(fmt(r.get("semantic_vs_seed_mean")))
        if has_facts:
            cells.append(fmt(r.get("survival_rate_mean"), pct=True))
        table.add_row(*cells)
    console.print(table)


if __name__ == "__main__":
    app()
