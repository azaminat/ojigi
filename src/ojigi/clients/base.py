"""API共通クライアント: リトライ・エラー整形・usageフック。

全API呼び出しの usage を UsageRecord として記録し、コストレシートの一次データにする。
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import httpx

from ..auth import TokenProvider
from ..cost import append_to_ledger
from ..models import UsageRecord
from ..settings import Settings


class ZoomApiError(RuntimeError):
    def __init__(self, status_code: int, body: str):
        super().__init__(f"Zoom API error {status_code}: {body[:500]}")
        self.status_code = status_code
        self.body = body


class BaseClient:
    api_name = "base"  # サブクラスで上書き

    _MAX_RETRIES = 3
    _RETRYABLE_STATUS = {429, 500, 502, 503, 504}

    def __init__(self, settings: Settings, token_provider: TokenProvider):
        self._settings = settings
        self._tokens = token_provider
        self._http = httpx.Client(base_url=settings.zoom_api_base, timeout=120)
        self.usage_records: list[UsageRecord] = []

    def close(self) -> None:
        self._http.close()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._tokens.get_token()}"}

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """指数バックオフ付きリクエスト。成功したら usage を記録する。"""
        started = time.time()
        last_error: ZoomApiError | None = None
        for attempt in range(self._MAX_RETRIES + 1):
            resp = self._http.request(method, path, headers=self._headers(), **kwargs)
            if resp.status_code < 400:
                data: dict[str, Any] = resp.json() if resp.content else {}
                self._record_usage(path, data, time.time() - started)
                return data
            last_error = ZoomApiError(resp.status_code, resp.text)
            if resp.status_code not in self._RETRYABLE_STATUS or attempt == self._MAX_RETRIES:
                raise last_error
            time.sleep(2**attempt)
        raise last_error  # 論理上到達しない

    def _record_usage(self, endpoint: str, data: dict[str, Any], duration: float) -> None:
        usage = data.get("usage") or {}
        record = UsageRecord(
            api=self.api_name,
            endpoint=endpoint,
            timestamp=datetime.now(),
            duration_sec=round(duration, 3),
            raw_usage=usage if isinstance(usage, dict) else {"value": usage},
            **self._extract_quantities(data, usage),
        )
        self.usage_records.append(record)
        append_to_ledger(record)

    def _extract_quantities(self, data: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
        """input_chars / audio_seconds 等を usage から抽出する（スパイク実測 2026-07-03）。

        unit_type で単位が変わる: Scribe は "seconds"（音声秒数）、
        Summarizer/Translator は "characters"（文字数）。
        """
        quantities: dict[str, Any] = {}
        unit_type = usage.get("unit_type")
        input_units = usage.get("input_units")
        output_units = usage.get("output_units")
        if unit_type == "seconds":
            if isinstance(input_units, (int, float)):
                quantities["audio_seconds"] = float(input_units)
        elif unit_type == "characters":
            if isinstance(input_units, (int, float)):
                quantities["input_chars"] = int(input_units)
            if isinstance(output_units, (int, float)):
                quantities["output_chars"] = int(output_units)
        elif isinstance(data.get("duration_sec"), (int, float)):
            quantities["audio_seconds"] = float(data["duration_sec"])
        return quantities
