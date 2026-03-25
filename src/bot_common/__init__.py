"""bot-common: Shared utilities for Bot projects."""

from bot_common.discord import send_discord_embed, send_discord_embeds, send_discord_message
from bot_common.json_parser import extract_json_array, extract_json_object
from bot_common.logging import setup_logging
from bot_common.timezone import JST, ensure_aware, now_jst, today_jst, utcnow

__all__ = [
    "JST",
    "ensure_aware",
    "extract_json_array",
    "extract_json_object",
    "now_jst",
    "send_discord_embed",
    "send_discord_embeds",
    "send_discord_message",
    "setup_logging",
    "today_jst",
    "utcnow",
]
