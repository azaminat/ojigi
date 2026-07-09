"""AI伝言ゲーム（telephone game）: Scribe/Summarizer/Translator を繰り返し通し、
情報がどこでどう劣化/収束するかを可視化する検証機能。

- 実験A: 翻訳往復（ja↔en, Translator単体） … 劣化・収束の観測
- 実験B: 要約連鎖（Summarizer単体） … 不動点に収束＝頑健性のコントロール群
- 実験C: フル伝言（音声→Scribe→要約→翻訳往復→TTS→音声…） … 総合劣化・誤変換採取

重い依存（sentence-transformers 等）は metrics 内で遅延importし、コアCLIを汚さない。
"""
