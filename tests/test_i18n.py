"""
测试 utils/i18n.py
"""

import pytest

from utils.i18n import I18N


class TestI18NClassMethod:
    def test_get_zh_text(self):
        assert I18N.get("zh", "window_title") == "串口监视器"

    def test_get_en_text(self):
        assert I18N.get("en", "window_title") == "Serial Monitor"

    def test_get_with_format_args(self):
        assert I18N.get("zh", "connected", "COM1") == "已连接到 COM1"

    def test_get_unknown_language_falls_back_zh(self):
        assert I18N.get("fr", "window_title") == "串口监视器"

    def test_get_unknown_key_returns_key(self):
        assert I18N.get("zh", "nonexistent_key") == "nonexistent_key"


class TestI18NInstance:
    def test_instance_default_language(self):
        i18n = I18N()
        assert i18n.language == "zh"

    def test_instance_t_zh(self):
        i18n = I18N("zh")
        assert i18n.t("send") == "发送"

    def test_instance_t_en(self):
        i18n = I18N("en")
        assert i18n.t("send") == "Send"

    def test_instance_t_with_args(self):
        i18n = I18N("en")
        assert i18n.t("connected", "/dev/ttyUSB0") == "Connected to /dev/ttyUSB0"

    def test_toggle_zh_to_en(self):
        i18n = I18N("zh")
        assert i18n.toggle() == "en"
        assert i18n.language == "en"

    def test_toggle_en_to_zh(self):
        i18n = I18N("en")
        assert i18n.toggle() == "zh"
        assert i18n.language == "zh"

    def test_texts_has_both_languages(self):
        assert "zh" in I18N.TEXTS
        assert "en" in I18N.TEXTS

    def test_texts_keys_match(self):
        zh_keys = set(I18N.TEXTS["zh"].keys())
        en_keys = set(I18N.TEXTS["en"].keys())
        assert zh_keys == en_keys
