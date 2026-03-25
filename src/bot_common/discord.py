"""Discord Webhook 送信ユーティリティ。

全Botプロジェクト共通の基底送信関数。
- シンプルなテキストメッセージ送信
- 単一/複数 embed 送信
- 429 Rate-Limit 時の自動リトライ（1回）

使い方:
    from bot_common.discord import send_discord_message, send_discord_embed

    ok = send_discord_message(webhook_url, "テスト通知")
    ok = send_discord_embed(webhook_url, {"title": "...", "color": 0x2ECC71})
"""

from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)


def send_discord_message(webhook_url: str, content: str) -> bool:
    """Discord Webhook にテキストメッセージを送信する。

    Args:
        webhook_url: Discord Webhook URL。空文字の場合は何もしない。
        content: 送信するテキスト。

    Returns:
        True on success, False on failure or skipped.
    """
    if not webhook_url:
        logger.warning("Discord webhook URL not set, skipping notification")
        return False

    payload = {"content": content}
    return _post(webhook_url, payload)


def send_discord_embed(webhook_url: str, embed: dict) -> bool:
    """Discord Webhook に単一の embed を送信する。

    Args:
        webhook_url: Discord Webhook URL。
        embed: Discord embed オブジェクト。

    Returns:
        True on success, False on failure.
    """
    if not webhook_url:
        logger.warning("Discord webhook URL not set, skipping embed")
        return False

    payload = {"embeds": [embed]}
    return _post(webhook_url, payload)


def send_discord_embeds(
    webhook_url: str,
    embeds: list[dict],
    delay_seconds: float = 0.0,
) -> bool:
    """Discord Webhook に複数の embed を順に送信する。

    Args:
        webhook_url: Discord Webhook URL。
        embeds: embed オブジェクトのリスト。各 embed を個別リクエストで送信。
        delay_seconds: embed 間の待機時間（秒）。レート制限回避に使用。

    Returns:
        全て成功した場合 True、1件でも失敗した場合 False。
    """
    if not webhook_url:
        logger.warning("Discord webhook URL not set, skipping embeds")
        return False

    success = True
    for i, embed in enumerate(embeds):
        ok = send_discord_embed(webhook_url, embed)
        if not ok:
            success = False
        if delay_seconds > 0 and i < len(embeds) - 1:
            time.sleep(delay_seconds)
    return success


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _post(webhook_url: str, payload: dict) -> bool:
    """POST リクエストを送信し、429 時は1回リトライする。"""
    try:
        resp = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 204:
            return True
        if resp.status_code == 429:
            retry_after = _get_retry_after(resp)
            logger.warning("Discord rate limited, waiting %ds", retry_after)
            time.sleep(retry_after)
            resp = requests.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if resp.status_code == 204:
                return True
        logger.warning("Discord send failed: %d %s", resp.status_code, resp.text[:200])
        return False
    except Exception as e:
        logger.error("Discord send error: %s", e)
        return False


def _get_retry_after(resp: requests.Response) -> int:
    """429 レスポンスから retry_after 秒数を取得する（デフォルト5秒）。"""
    try:
        return int(resp.json().get("retry_after", 5))
    except Exception:
        return 5
