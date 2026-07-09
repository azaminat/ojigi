"""Zoom AI Services 向け JWT(HS256) の生成と有効期限管理。"""

from __future__ import annotations

import time

import jwt

from .settings import Settings


class TokenProvider:
    """有効期限内はキャッシュしたトークンを返す。"""

    # 期限切れ間際のトークンでリクエストしないための余裕幅
    _SKEW_SECONDS = 30

    def __init__(self, settings: Settings):
        self._settings = settings
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        now = time.time()
        if self._token is None or now >= self._expires_at - self._SKEW_SECONDS:
            self._token = self._generate(now)
            self._expires_at = now + self._settings.jwt_ttl_seconds
        return self._token

    def _generate(self, now: float) -> str:
        payload = {
            "iss": self._settings.zoom_api_key,
            "iat": int(now) - 30,  # クロックずれ対策（公式ドキュメントの推奨）
            "exp": int(now + self._settings.jwt_ttl_seconds),
        }
        return jwt.encode(payload, self._settings.zoom_api_secret, algorithm="HS256")
