"""Slack Incoming Webhook への通知。"""

from __future__ import annotations

import httpx


def post_to_slack(webhook_url: str, blocks: list[dict], text: str = "議事録が生成されました") -> None:
    resp = httpx.post(webhook_url, json={"text": text, "blocks": blocks}, timeout=30)
    resp.raise_for_status()
