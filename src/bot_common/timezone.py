"""Timezone helpers for JST-based Bot operations.

GitHub Actions runs in UTC. These helpers ensure consistent JST handling
across all Bot projects.

Usage:
    from bot_common.timezone import JST, today_jst, now_jst, utcnow, ensure_aware
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
"""日本標準時 (UTC+9)。全モジュールはこの定数を import して使用すること。"""


def now_jst() -> datetime:
    """現在時刻を JST aware datetime で返す。"""
    return datetime.now(tz=JST)


def today_jst() -> date:
    """今日の日付を JST 基準で返す。GitHub Actions UTC 環境でも安全。"""
    return now_jst().date()


def utcnow() -> datetime:
    """現在時刻を UTC aware datetime で返す。

    Note:
        kabu-bot のように naive datetime が必要な場合は、
        呼び出し側で ``utcnow().replace(tzinfo=None)`` を使用すること。
    """
    return datetime.now(tz=timezone.utc)


def ensure_aware(
    dt: datetime,
    tz: ZoneInfo | timezone | None = None,
) -> datetime:
    """naive datetime を aware に変換する。既に aware ならそのまま返す。

    SQLite は tzinfo を保持しないため、DB から読み込んだ datetime は
    naive になることがある。このヘルパーで統一的に変換する。

    Args:
        dt: 変換対象の datetime。
        tz: 付与するタイムゾーン。省略時は JST。

    Warning:
        デフォルトは JST。UTC を期待する場合は ``tz=timezone.utc`` を明示すること。

    Returns:
        timezone-aware な datetime。
    """
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=tz or JST)
