"""timezone の単体テスト + 消費者テスト（kabu-bot互換）。"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from bot_common.timezone import JST, ensure_aware, now_jst, today_jst, utcnow


class TestTimezoneBasics:
    """基本的な動作確認。"""

    def test_jst_is_zoneinfo(self):
        assert isinstance(JST, ZoneInfo)
        assert str(JST) == "Asia/Tokyo"

    def test_now_jst_is_aware(self):
        dt = now_jst()
        assert dt.tzinfo is not None
        assert dt.tzinfo == JST

    def test_today_jst_returns_date(self):
        result = today_jst()
        assert isinstance(result, date)

    def test_utcnow_is_aware(self):
        dt = utcnow()
        assert dt.tzinfo is not None
        assert dt.tzinfo == timezone.utc

    def test_utcnow_close_to_now(self):
        dt = utcnow()
        now = datetime.now(tz=timezone.utc)
        assert abs((now - dt).total_seconds()) < 2


class TestEnsureAware:
    """ensure_aware のテスト。"""

    def test_naive_defaults_to_jst(self):
        naive = datetime(2026, 1, 1, 12, 0, 0)
        result = ensure_aware(naive)
        assert result.tzinfo == JST
        assert result.hour == 12

    def test_naive_with_explicit_tz(self):
        naive = datetime(2026, 1, 1, 12, 0, 0)
        result = ensure_aware(naive, tz=timezone.utc)
        assert result.tzinfo == timezone.utc

    def test_already_aware_unchanged(self):
        aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = ensure_aware(aware, tz=JST)
        assert result.tzinfo == timezone.utc  # 元のtzが維持される


class TestKabuBotCompat:
    """kabu-bot 互換テスト: naive化ラッパー経由の動作検証。"""

    def test_utcnow_naive_wrapper(self):
        """kabu-bot が使う utcnow().replace(tzinfo=None) パターン。"""
        naive_utc = utcnow().replace(tzinfo=None)
        assert naive_utc.tzinfo is None
        # UTC基準の時刻なので、JST（+9h）とは異なるはず
        jst_now = now_jst()
        # naive_utcとjst_nowの差が8-10時間の範囲内であることを確認
        # （直接比較はできないので、hourの差で概算チェック）
        diff_hours = (jst_now.hour - naive_utc.hour) % 24
        assert diff_hours in (8, 9, 10)  # 夏時間なしで常に9

    def test_ensure_aware_roundtrip(self):
        """DB保存→読み込み→ensure_aware のラウンドトリップ。"""
        # 保存時: aware → naive
        original = now_jst()
        stored = original.replace(tzinfo=None)  # DB保存でnaiveに

        # 読み込み時: naive → ensure_aware
        restored = ensure_aware(stored, tz=JST)
        assert restored.tzinfo == JST
        assert restored.hour == original.hour
        assert restored.minute == original.minute
