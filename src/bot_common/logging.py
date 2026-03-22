"""Unified logging setup for all Bot projects.

Usage:
    from bot_common.logging import setup_logging
    setup_logging(verbose=True, noisy_libs=["httpx", "urllib3"])
"""

from __future__ import annotations

import logging
import sys


def setup_logging(
    verbose: bool = False,
    noisy_libs: list[str] | None = None,
) -> None:
    """ログ設定を初期化する。

    Args:
        verbose: True で DEBUG レベル、False で INFO レベル。
        noisy_libs: CRITICAL に抑制する外部ライブラリ名リスト。
            例: ["httpx", "urllib3", "yfinance"]
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=level,
        stream=sys.stderr,
        force=True,
    )

    if noisy_libs:
        for lib in noisy_libs:
            logging.getLogger(lib).setLevel(logging.CRITICAL)
