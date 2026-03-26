"""Tests for the caching logic."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from main import _cache_key


class TestCacheKey:
    def test_same_text_same_key(self):
        assert _cache_key("hello world") == _cache_key("hello world")

    def test_case_insensitive(self):
        assert _cache_key("Hello World") == _cache_key("hello world")

    def test_whitespace_normalized(self):
        assert _cache_key("hello   world") == _cache_key("hello world")
        assert _cache_key("  hello world  ") == _cache_key("hello world")

    def test_different_text_different_key(self):
        assert _cache_key("hello") != _cache_key("world")

    def test_key_is_16_chars(self):
        assert len(_cache_key("any text")) == 16

    def test_key_is_hex(self):
        key = _cache_key("test")
        assert all(c in "0123456789abcdef" for c in key)
