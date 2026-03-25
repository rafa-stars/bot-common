"""Tests for bot_common.discord."""

from unittest.mock import MagicMock, patch

import pytest

from bot_common.discord import (
    send_discord_embed,
    send_discord_embeds,
    send_discord_message,
)


def _mock_response(status_code: int, json_body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.text = ""
    return resp


class TestSendDiscordMessage:
    def test_empty_url_returns_false(self):
        assert send_discord_message("", "hello") is False

    def test_success_204(self):
        with patch("bot_common.discord.requests.post", return_value=_mock_response(204)):
            assert send_discord_message("https://example.com/hook", "hello") is True

    def test_failure_non_204(self):
        with patch("bot_common.discord.requests.post", return_value=_mock_response(500)):
            assert send_discord_message("https://example.com/hook", "hello") is False

    def test_rate_limit_retry_success(self):
        responses = [_mock_response(429, {"retry_after": 0}), _mock_response(204)]
        with patch("bot_common.discord.requests.post", side_effect=responses):
            with patch("bot_common.discord.time.sleep"):
                assert send_discord_message("https://example.com/hook", "hello") is True

    def test_rate_limit_retry_failure(self):
        responses = [_mock_response(429, {"retry_after": 0}), _mock_response(500)]
        with patch("bot_common.discord.requests.post", side_effect=responses):
            with patch("bot_common.discord.time.sleep"):
                assert send_discord_message("https://example.com/hook", "hello") is False

    def test_exception_returns_false(self):
        with patch("bot_common.discord.requests.post", side_effect=Exception("timeout")):
            assert send_discord_message("https://example.com/hook", "hello") is False


class TestSendDiscordEmbed:
    def test_empty_url_returns_false(self):
        assert send_discord_embed("", {"title": "t"}) is False

    def test_success(self):
        with patch("bot_common.discord.requests.post", return_value=_mock_response(204)):
            assert send_discord_embed("https://example.com/hook", {"title": "t"}) is True


class TestSendDiscordEmbeds:
    def test_empty_url_returns_false(self):
        assert send_discord_embeds("", [{"title": "t"}]) is False

    def test_all_success(self):
        with patch("bot_common.discord.requests.post", return_value=_mock_response(204)):
            result = send_discord_embeds("https://example.com/hook", [{"a": 1}, {"b": 2}])
        assert result is True

    def test_partial_failure_returns_false(self):
        responses = [_mock_response(204), _mock_response(500)]
        with patch("bot_common.discord.requests.post", side_effect=responses):
            result = send_discord_embeds("https://example.com/hook", [{"a": 1}, {"b": 2}])
        assert result is False

    def test_delay_between_embeds(self):
        with patch("bot_common.discord.requests.post", return_value=_mock_response(204)):
            with patch("bot_common.discord.time.sleep") as mock_sleep:
                send_discord_embeds(
                    "https://example.com/hook",
                    [{"a": 1}, {"b": 2}],
                    delay_seconds=1.5,
                )
        mock_sleep.assert_called_once_with(1.5)
