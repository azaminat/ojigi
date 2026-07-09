"""環境変数（.env）からの設定読み込み。"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Zoom Build プラットフォームの API keys（Marketplace の Client ID/Secret ではない）
    zoom_api_key: str = ""
    zoom_api_secret: str = ""
    zoom_api_base: str = "https://api.zoom.us/v2"
    jwt_ttl_seconds: int = 3600  # 公式推奨の最長1時間

    slack_webhook_url: str = ""

    # Scribe は音声をURLで受け取るため、ローカルファイルはS3経由で渡す
    s3_bucket: str = ""
    s3_prefix: str = "ojigi-uploads/"
    aws_profile: str = "default"
    aws_region: str = "ap-northeast-1"  # S3バケット・Polly(伝言ゲームのTTS)のリージョン
    presign_ttl_seconds: int = 900

    # 伝言ゲーム実験C用 TTS（Amazon Polly）
    polly_voice: str = "Takumi"  # ja-JP neural 対応。女性は Kazuha
    polly_engine: str = "neural"

    usd_jpy_rate: float = 150.0  # コストレシートの円換算レート


def get_settings() -> Settings:
    return Settings()
