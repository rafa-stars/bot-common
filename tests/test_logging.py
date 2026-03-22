"""setup_logging の単体テスト。"""

import logging

from bot_common.logging import setup_logging


class TestSetupLogging:
    """setup_logging の基本動作。"""

    def test_default_info_level(self):
        setup_logging()
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_verbose_debug_level(self):
        setup_logging(verbose=True)
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_noisy_libs_suppressed(self):
        setup_logging(noisy_libs=["httpx", "urllib3"])
        assert logging.getLogger("httpx").level == logging.CRITICAL
        assert logging.getLogger("urllib3").level == logging.CRITICAL

    def test_noisy_libs_none(self):
        """noisy_libs=None でエラーにならないこと。"""
        setup_logging(noisy_libs=None)  # Should not raise

    def test_format_has_expected_parts(self):
        """ハンドラのフォーマットに必要な要素が含まれること。"""
        setup_logging()
        root = logging.getLogger()
        assert root.handlers, "root logger should have handlers after setup"
        formatter = root.handlers[0].formatter
        assert formatter is not None
        fmt = formatter._fmt
        assert "%(asctime)s" in fmt
        assert "[%(levelname)s]" in fmt
        assert "%(name)s" in fmt
