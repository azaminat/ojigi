"""テキスト→音声（Amazon Polly）。伝言ゲーム実験C（フル伝言）で毎世代の音声を合成する。

Zoom AI Services 3APIの外側のスキャフォールド（"伝言役の口"）。boto3は既存依存で、
S3バケット・AWSプロファイルも構築済みのため追加セットアップ不要。
"""

from __future__ import annotations

import uuid
from pathlib import Path

from ..settings import Settings

# Polly synthesize_speech の課金対象テキスト上限（1リクエスト3,000字）。伝言ゲームの
# 各世代テキストは通常これ未満だが、安全のため超過時は分割せず先頭を切って警告する。
_POLLY_TEXT_LIMIT = 3000


def synthesize(text: str, settings: Settings, out_dir: str | Path) -> Path:
    """text を ja-JP 音声(mp3)に合成し、out_dir に保存してパスを返す。"""
    import boto3  # 遅延import

    if len(text) > _POLLY_TEXT_LIMIT:
        text = text[:_POLLY_TEXT_LIMIT]

    session = boto3.Session(
        profile_name=settings.aws_profile or None,
        region_name=settings.aws_region or None,
    )
    polly = session.client("polly")
    resp = polly.synthesize_speech(
        Text=text,
        OutputFormat="mp3",
        VoiceId=settings.polly_voice,
        Engine=settings.polly_engine,
        LanguageCode="ja-JP",
    )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"tts_{uuid.uuid4().hex}.mp3"
    with path.open("wb") as f:
        f.write(resp["AudioStream"].read())
    return path
