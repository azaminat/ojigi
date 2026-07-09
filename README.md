# ojigi 🙇

**録音を置くだけで、日英バイリンガル議事録 + コストレシート。**

Zoom AI Services の3つのAPI（Scribe / Summarizer / Translator）を総動員して、
録音ファイル1つから「要約・決定事項・アクションアイテム・全文」の日英議事録を生成し、
実行のたびに **かかったコストをレシートとして表示** するCLIツールです。

```
uv run ojigi minutes meeting.m4a --slack
```

さらに、3つのAPIを繰り返し通して「情報がどこでどう劣化するか」を可視化する
**AI伝言ゲーム**モード（`ojigi telephone`）を検証機能として同梱しています。

出力:
- `output/meeting_minutes.md` — 日英バイリンガル議事録
- Slack通知（要約・決定事項・アクションアイテム）
- ターミナルにコストレシート（Scribe ¥x + Summarizer ¥y + Translator ¥z = 合計 ¥N）
- `output/usage_ledger.jsonl` — 全API呼び出しのusage実測ログ

## セットアップ（3ステップ）

```powershell
# 1. 依存関係
uv sync

# 2. 認証情報（Zoom Build プラットフォームの API keys）
copy .env.example .env   # ZOOM_API_KEY / ZOOM_API_SECRET を設定

# 3. 実行
uv run ojigi minutes path\to\meeting.m4a
```

> **Note**: Scribe API は音声を「URL」で受け取ります。ローカルファイルを渡す場合は
> `.env` に `S3_BUCKET` を設定してください（署名付きURLで一時的に渡します）。
> 公開URL上の音声ならそのまま指定できます。

### `ojigi minutes` のオプション

| オプション | 説明 |
|---|---|
| `--slack` | Slack Incoming Webhook に要約を通知 |
| `--full-translate` | 全文も英訳する（デフォルトは要約のみ英訳＝コスト最適化） |
| `--mode fast\|batch` | Scribeのモード（現状 fast のみ） |
| `--output-dir` | 議事録の出力先（デフォルト: output/） |

## AI伝言ゲーム（`ojigi telephone`）

3つのAPIを繰り返し通し、情報がどこでどう劣化/収束するかを可視化する検証モード。

```
uv run ojigi telephone examples/telephone_seed.md --mode roundtrip --generations 12 --trials 3 --facts examples/telephone_facts.json
```

`examples/` に検証記事で使った種テキスト（決定事項・固有名詞・数値の罠入り模擬会議）と
サバイバル判定用ファクト定義を同梱しています。記事の実測データ（3実験×3試行の全世代JSON・
グラフ・集計表）は `article-data/` にあります。

| モード | 1世代の処理 | 観測できること |
|---|---|---|
| `roundtrip` | ja→en→ja（Translator往復） | 翻訳の揺り戻し・収束 |
| `summary` | 要約(前世代)（Summarizer連鎖） | 要約の不動点収束・情報の取捨 |
| `full` | TTS(Polly)→Scribe→翻訳往復 | 音声化も含む総合劣化・誤変換 |

| オプション | 説明 |
|---|---|
| `--mode` / `-m` | roundtrip \| summary \| full |
| `--generations` / `-g` | 世代数（既定 10） |
| `--trials` / `-t` | 試行回数＝分散バンド用（既定 3） |
| `--facts` | サバイバル率判定用のファクトJSON |
| `--with-summary` | full時に毎世代で要約を挟む |
| `--no-semantic` | 意味類似度をスキップ（高速） |

> **Note**: `full` モードは Amazon Polly で音声を合成します（`.env` の `AWS_PROFILE` /
> `AWS_REGION` を使用）。CER・意味類似度の算出には dev 依存（jiwer / sentence-transformers）が必要です。

## テスト

```powershell
uv run pytest
```

## License

MIT
