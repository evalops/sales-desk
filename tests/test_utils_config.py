import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils import get_bool_setting


def test_get_bool_setting_from_config_path():
    cfg = {"settings": {"feature": {"enabled": True}}}
    val = get_bool_setting(cfg, ["settings", "feature", "enabled"], None, False)
    assert val is True


def test_get_bool_setting_env_override_truthy(monkeypatch):
    cfg = {"settings": {"feature": {"enabled": False}}}
    monkeypatch.setenv("FEATURE_ENABLED", "yes")
    val = get_bool_setting(cfg, ["settings", "feature", "enabled"], "FEATURE_ENABLED", False)
    assert val is True


def test_get_bool_setting_default_when_missing(monkeypatch):
    cfg = {"settings": {}}
    monkeypatch.delenv("MISSING_ENV", raising=False)
    val = get_bool_setting(cfg, ["settings", "missing"], "MISSING_ENV", True)
    assert val is True

