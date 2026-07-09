"""ローカル音声ファイルを Scribe が取得できるURLに変換する。

Scribe Fast API は音声を「URL指定」でしか受け取らないため、ローカルファイルは
S3 にアップロードして署名付きURL（短TTL）を発行し、文字起こし完了後に削除する。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .settings import Settings

_CONTENT_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "video/mp4",
}


@dataclass
class FetchableAudio:
    url: str
    cleanup: Callable[[], None] = field(default=lambda: None)


def to_fetchable_url(audio: str | Path, settings: Settings) -> FetchableAudio:
    """http(s) URL はそのまま返し、ローカルパスは S3 経由で署名付きURLにする。"""
    if isinstance(audio, str) and audio.startswith(("http://", "https://")):
        return FetchableAudio(url=audio)

    path = Path(audio)
    suffix = path.suffix.lower()
    if suffix not in _CONTENT_TYPES:
        raise ValueError(f"未対応の音声形式です: {suffix}（対応: {', '.join(_CONTENT_TYPES)}）")
    if not settings.s3_bucket:
        raise ValueError(
            "ローカルファイルを渡すには S3_BUCKET の設定が必要です（Scribe APIは音声をURLで受け取るため）。"
            "公開URL上の音声を直接指定することもできます。"
        )

    import boto3  # 遅延import: URL直接指定のユーザーにはboto3不要

    session = boto3.Session(profile_name=settings.aws_profile or None)
    s3 = session.client("s3")
    # 署名付きURLは拡張子で形式判定される（拡張子なしURLは415になる）ためファイル名を保持
    key = f"{settings.s3_prefix}{uuid.uuid4().hex}/{path.name}"
    s3.upload_file(
        str(path), settings.s3_bucket, key, ExtraArgs={"ContentType": _CONTENT_TYPES[suffix]}
    )
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=settings.presign_ttl_seconds,
    )
    # 会議音声は機微情報のため、文字起こし後にS3から削除する
    return FetchableAudio(
        url=url, cleanup=lambda: s3.delete_object(Bucket=settings.s3_bucket, Key=key)
    )
