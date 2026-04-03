"""BAN avoidance engine for SNS posting (platform-agnostic).

Multi-layer safety checks to prevent account suspension:
1. Posting hours restriction
2. Deep night block (1:00-6:00 JST absolute)
3. Daily post limit (with optional warmup)
4. Minimum post interval
5. Pattern rotation (consecutive same-pattern block)
6. AI phrase detection
7. Engagement health monitoring

Each check can be individually toggled via enable_* flags in BanAvoidanceConfig.
dry_run mode logs violations without blocking.
"""

from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Protocol, runtime_checkable

from bot_common.timezone import JST

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols & Data classes
# ---------------------------------------------------------------------------


@dataclass
class PostRecord:
    """Minimal post record for BAN avoidance checks.

    Adapters convert platform-specific DB models to this struct.
    """

    posted_at: datetime
    pattern: str = ""
    content: str = ""


@runtime_checkable
class PostHistoryProvider(Protocol):
    """Single-method interface for retrieving recent post history."""

    def recent_posts(self, platform: str, n: int) -> list[PostRecord]:
        """Return the last *n* posted records for *platform*, newest first."""
        ...


@dataclass
class BanAvoidanceConfig:
    """Per-platform BAN avoidance settings.

    All values are validated at load time via validate().
    """

    platform: str = "x"
    posting_start_hour: int = 5
    posting_end_hour: int = 23
    max_daily_posts: int = 6
    min_post_interval_minutes: int = 45
    dry_run: bool = False

    # Feature toggles (str: "true" / "false" / "dry_run")
    enable_warmup: str = "false"
    enable_pattern_rotation: str = "false"
    enable_ai_detection: str = "false"
    enable_engagement_health: str = "false"

    def validate(self) -> None:
        """Raise ValueError if any setting is out of range."""
        if not (0 <= self.posting_start_hour <= 23):
            raise ValueError(f"posting_start_hour must be 0-23, got {self.posting_start_hour}")
        if not (1 <= self.posting_end_hour <= 25):
            raise ValueError(f"posting_end_hour must be 1-25, got {self.posting_end_hour}")
        if self.posting_start_hour >= self.posting_end_hour:
            raise ValueError(
                f"posting_start_hour ({self.posting_start_hour}) "
                f"must be < posting_end_hour ({self.posting_end_hour})"
            )
        if not (1 <= self.max_daily_posts <= 50):
            raise ValueError(f"max_daily_posts must be 1-50, got {self.max_daily_posts}")
        if not (10 <= self.min_post_interval_minutes <= 1440):
            raise ValueError(
                f"min_post_interval_minutes must be 10-1440, got {self.min_post_interval_minutes}"
            )
        valid_toggles = {"true", "false", "dry_run"}
        for toggle_name in (
            "enable_warmup",
            "enable_pattern_rotation",
            "enable_ai_detection",
            "enable_engagement_health",
        ):
            val = getattr(self, toggle_name)
            if val not in valid_toggles:
                raise ValueError(f"{toggle_name} must be one of {valid_toggles}, got '{val}'")


@dataclass
class PublishResult:
    """Result of a guarded publish attempt."""

    success: bool
    blocked: bool = False
    reason: str | None = None
    dry_run_warnings: list[str] = field(default_factory=list)
    result: Any = None  # publish_fn return value


# ---------------------------------------------------------------------------
# Warmup schedule
# ---------------------------------------------------------------------------

_WARMUP_SCHEDULE = [
    (0, 2),    # Day 0-6:  max 2 posts/day
    (7, 4),    # Day 7-13: max 4
    (14, 6),   # Day 14-20: max 6
    (21, 8),   # Day 21-27: max 8
    (28, 10),  # Day 28+:  full capacity
]


# ---------------------------------------------------------------------------
# BanAvoidanceEngine
# ---------------------------------------------------------------------------


class BanAvoidanceEngine:
    """Platform-aware BAN avoidance engine.

    Args:
        config: Per-platform settings.
        history: Provider for recent post history.
        clock: Callable returning current JST datetime. Defaults to now_jst().
        ai_detector: Optional callable(text) -> list[str] for AI phrase detection.
    """

    def __init__(
        self,
        config: BanAvoidanceConfig,
        history: PostHistoryProvider,
        clock: Callable[[], datetime] | None = None,
        ai_detector: Callable[[str], list[str]] | None = None,
    ) -> None:
        config.validate()
        self._config = config
        self._history = history
        self._clock = clock or _default_clock
        self._ai_detector = ai_detector

    @property
    def config(self) -> BanAvoidanceConfig:
        """Expose config for testing / inspection."""
        return self._config

    # ================================================================
    # Public API
    # ================================================================

    def can_post_now(self, content: str = "", pattern: str = "") -> tuple[bool, str]:
        """Check all enabled layers. Returns (allowed, reason).

        Args:
            content: Post text (for AI detection check).
            pattern: Post pattern name (for pattern rotation check).

        Returns:
            (True, "ok") if all checks pass.
            (False, reason) if any hard check fails.
            In dry_run mode, soft checks log warnings but don't block.
        """
        dry_run = self._config.dry_run
        warnings: list[str] = []

        # --- Hard checks (always enforced) ---
        for check in [
            self._check_night_hours,
            self._check_posting_hours,
            self._check_daily_limit,
            self._check_interval,
        ]:
            allowed, reason = check()
            if not allowed:
                if dry_run:
                    logger.warning("[dry_run] BAN avoidance would block: %s", reason)
                    warnings.append(reason)
                else:
                    logger.info("BAN avoidance BLOCKED [%s]: %s", self._config.platform, reason)
                    return False, reason

        # --- Soft checks (toggled per feature) ---
        soft_checks: list[tuple[str, Callable[[], tuple[bool, str]]]] = []

        if self._is_enabled("enable_pattern_rotation") and pattern:
            soft_checks.append((
                "enable_pattern_rotation",
                lambda: self._check_pattern_rotation(pattern),
            ))

        if self._is_enabled("enable_ai_detection") and content and self._ai_detector:
            soft_checks.append((
                "enable_ai_detection",
                lambda: self._check_ai_detection(content),
            ))

        if self._is_enabled("enable_engagement_health"):
            soft_checks.append((
                "enable_engagement_health",
                self._check_engagement_health,
            ))

        for toggle_name, check in soft_checks:
            allowed, reason = check()
            if not allowed:
                toggle_val = getattr(self._config, toggle_name)
                if toggle_val == "dry_run" or dry_run:
                    logger.warning("[dry_run] %s: %s", toggle_name, reason)
                    warnings.append(reason)
                else:
                    logger.info("BAN avoidance BLOCKED [%s]: %s", self._config.platform, reason)
                    return False, reason

        if warnings:
            logger.info(
                "BAN avoidance passed with %d dry_run warnings [%s]",
                len(warnings), self._config.platform,
            )

        return True, "ok"

    # ================================================================
    # Internal checks
    # ================================================================

    def _check_posting_hours(self) -> tuple[bool, str]:
        """Block outside configured posting hours."""
        hour = self._clock().hour
        start = self._config.posting_start_hour
        end = self._config.posting_end_hour
        if end <= 24:
            if not (start <= hour < end):
                return False, f"Outside posting hours ({start}:00-{end}:00 JST, now {hour}:00)"
        else:
            # Midnight wrap (e.g. end=25 means 01:00 next day)
            if not (hour >= start or hour < (end - 24)):
                return False, f"Outside posting hours ({start}:00-{end}:00 JST, now {hour}:00)"
        return True, "ok"

    def _check_night_hours(self) -> tuple[bool, str]:
        """Hard block during 1:00-6:00 JST regardless of settings."""
        hour = self._clock().hour
        if 1 <= hour < 6:
            return False, f"Deep night hours (1-6 JST), hour={hour}"
        return True, "ok"

    def _check_daily_limit(self) -> tuple[bool, str]:
        """Check today's post count against limit (with optional warmup)."""
        limit = self._get_daily_limit()
        today_posts = self._count_posts_today()
        if today_posts >= limit:
            return False, f"Daily limit reached ({today_posts}/{limit})"
        return True, "ok"

    def _check_interval(self) -> tuple[bool, str]:
        """Ensure minimum interval since last post."""
        min_minutes = self._config.min_post_interval_minutes
        last_at = self._last_posted_at()
        if last_at is None:
            return True, "ok"

        now = self._clock()
        # Ensure timezone-aware comparison
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=JST)

        elapsed = (now - last_at).total_seconds() / 60
        if elapsed < min_minutes:
            return False, f"Too soon since last post ({elapsed:.0f}m < {min_minutes}m)"
        return True, "ok"

    def _check_pattern_rotation(self, new_pattern: str) -> tuple[bool, str]:
        """Block if last 3 posts share the same pattern."""
        recent = self._history.recent_posts(self._config.platform, 3)
        patterns = [r.pattern for r in recent if r.pattern]
        if patterns.count(new_pattern) >= 2:
            return False, f"Pattern rotation: '{new_pattern}' appeared {patterns.count(new_pattern)} times in last 3"
        return True, "ok"

    def _check_ai_detection(self, content: str) -> tuple[bool, str]:
        """Block if AI-generated phrases are detected."""
        if not self._ai_detector:
            return True, "ok"
        found = self._ai_detector(content)
        if found:
            return False, f"AI phrases detected: {found[:3]}"
        return True, "ok"

    def _check_engagement_health(self) -> tuple[bool, str]:
        """Placeholder for engagement health monitoring.

        Phase 3 implementation: compare recent vs older engagement metrics.
        Currently always passes (data collection phase).
        """
        return True, "ok"

    # ================================================================
    # Helpers
    # ================================================================

    def _get_daily_limit(self) -> int:
        """Determine today's post limit considering warmup."""
        base = self._config.max_daily_posts

        if self._is_enabled("enable_warmup"):
            warmup_base = self._warmup_limit()
            base = min(base, warmup_base)

        now = self._clock()

        # Weekend reduction (20-30%)
        if now.weekday() in (5, 6):
            reduction = random.uniform(0.7, 0.8)
            base = max(1, int(base * reduction))

        # Random rest day (~1 in 7, seeded by date for daily consistency)
        day_seed = now.toordinal()
        rng = random.Random(day_seed)
        if rng.random() < 1 / 7:
            base = max(1, base // 2)
            logger.info("Rest day: post limit halved to %d [%s]", base, self._config.platform)

        return base

    def _warmup_limit(self) -> int:
        """Base daily limit from warmup schedule."""
        days = self._get_warmup_day()
        limit = _WARMUP_SCHEDULE[0][1]
        for threshold_day, max_posts in _WARMUP_SCHEDULE:
            if days >= threshold_day:
                limit = max_posts
        return limit

    def _get_warmup_day(self) -> int:
        """Days since account start date (from env var)."""
        start_str = os.getenv("ACCOUNT_START_DATE", "")
        if not start_str:
            return 30  # assume mature account
        try:
            start = datetime.fromisoformat(start_str).date()
            return (self._clock().date() - start).days
        except ValueError:
            logger.warning("Invalid ACCOUNT_START_DATE: %s", start_str)
            return 30

    def _count_posts_today(self) -> int:
        """Count posts made today for this platform."""
        today = self._clock().date()
        recent = self._history.recent_posts(self._config.platform, 50)
        return sum(
            1 for r in recent
            if r.posted_at is not None and r.posted_at.date() == today
        )

    def _last_posted_at(self) -> datetime | None:
        """Timestamp of the most recent post."""
        recent = self._history.recent_posts(self._config.platform, 1)
        if not recent:
            return None
        return recent[0].posted_at

    def _is_enabled(self, toggle_name: str) -> bool:
        """Check if a feature toggle is enabled (true or dry_run)."""
        val = getattr(self._config, toggle_name, "false")
        return val in ("true", "dry_run")


# ---------------------------------------------------------------------------
# Default clock
# ---------------------------------------------------------------------------


def _default_clock() -> datetime:
    """Default clock returning current JST time."""
    return datetime.now(tz=JST)
