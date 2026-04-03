"""bot-common: Shared utilities for Bot projects."""

from bot_common.ai_detection import (
    BUILTIN_COMMON_PHRASES,
    detect_ai_phrases,
    load_phrases_from_toml,
)
from bot_common.ban_avoidance import (
    BanAvoidanceConfig,
    BanAvoidanceEngine,
    PostHistoryProvider,
    PostRecord,
    PublishResult,
)
from bot_common.discord import send_discord_embed, send_discord_embeds, send_discord_message
from bot_common.json_parser import extract_json_array, extract_json_object
from bot_common.logging import setup_logging
from bot_common.similarity import SimilarityChecker
from bot_common.timezone import JST, ensure_aware, now_jst, today_jst, utcnow

__all__ = [
    # AI detection
    "BUILTIN_COMMON_PHRASES",
    "detect_ai_phrases",
    "load_phrases_from_toml",
    # BAN avoidance
    "BanAvoidanceConfig",
    "BanAvoidanceEngine",
    "PostHistoryProvider",
    "PostRecord",
    "PublishResult",
    # Discord
    "send_discord_embed",
    "send_discord_embeds",
    "send_discord_message",
    # Similarity
    "SimilarityChecker",
    # JSON
    "extract_json_array",
    "extract_json_object",
    # Logging
    "setup_logging",
    # Timezone
    "JST",
    "ensure_aware",
    "now_jst",
    "today_jst",
    "utcnow",
]
